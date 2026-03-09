"""LLM analysis stages: red flag detection, scoring, and judge validation."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from config import ANTHROPIC_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)


def _get_client():
    if not ANTHROPIC_API_KEY:
        logger.error("[LLM] ANTHROPIC_API_KEY not set. Cannot perform LLM analysis.")
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _call_llm(client, prompt, system="You are a rental apartment analyst."):
    """Make a single LLM call and return parsed JSON or raw text."""
    try:
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text

        # Try to extract JSON from response
        text_stripped = text.strip()
        if text_stripped.startswith("```json"):
            text_stripped = text_stripped[7:]
        if text_stripped.startswith("```"):
            text_stripped = text_stripped[3:]
        if text_stripped.endswith("```"):
            text_stripped = text_stripped[:-3]
        text_stripped = text_stripped.strip()

        try:
            return json.loads(text_stripped)
        except json.JSONDecodeError:
            return {"raw_response": text}
    except Exception as e:
        logger.error(f"[LLM] API call failed: {e}")
        return {"error": str(e)}


def analyze_red_flags(listing, client):
    """LLM Call #1: Detect red flags in a listing."""
    description = listing.get("description", "No description available.")
    address = listing.get("address", "Unknown")
    price = listing.get("price", "Unknown")
    beds = listing.get("bedrooms", "Unknown")
    baths = listing.get("bathrooms", "Unknown")

    prompt = f"""You are a rental apartment analyst. Read the following listing description and identify any red flags or potential downsides a renter should know about.

Look for: ground floor unit, alley/rear entrance, lack of natural light, basement, street noise, small/cramped layout, no laundry in the building, parking issues, hidden fees, short lease terms, signs of a scam listing, or anything else concerning.

Listing Details:
- Address: {address}
- Price: ${price}/month
- Bedrooms: {beds}, Bathrooms: {baths}
- Description: {description}

Return a structured JSON with:
- red_flags: list of objects, each with "issue" (string) and "severity" ("low", "medium", or "high")
- summary: one sentence overall assessment

Return ONLY valid JSON, no other text."""

    return _call_llm(client, prompt)


def score_listing(listing, user_preferences, client):
    """LLM Call #2: Score and rank a listing against user preferences."""
    description = listing.get("description", "No description available.")
    address = listing.get("address", "Unknown")
    price = listing.get("price", "Unknown")
    beds = listing.get("bedrooms", "Unknown")
    baths = listing.get("bathrooms", "Unknown")
    nearest_shuttle = listing.get("nearest_shuttle", "N/A")
    shuttle_duration = listing.get("nearest_shuttle_duration", "N/A")
    transit_info = listing.get("transit_info", "N/A")
    red_flags = listing.get("red_flag_analysis", {})

    prefs_text = json.dumps(user_preferences, indent=2)

    prompt = f"""You are a rental apartment advisor. Score this listing from 1-100 based on how well it matches the user's preferences.

User's Preferences:
{prefs_text}

Listing Details:
- Address: {address}
- Price: ${price}/month
- Bedrooms: {beds}, Bathrooms: {baths}
- Description: {description}
- Nearest shuttle stop: {nearest_shuttle} ({shuttle_duration} walk)
- Nearest transit: {transit_info}
- Red flag analysis: {json.dumps(red_flags)}

Return structured JSON with:
- score: integer 1-100
- score_breakdown: object with category scores (0-20 each) for "location", "price_value", "amenities", "red_flag_penalty", "commute_convenience"
- explanation: 2-3 sentences explaining the score

Return ONLY valid JSON, no other text."""

    return _call_llm(client, prompt, system="You are a rental apartment advisor.")


def run_analysis(listings, user_preferences):
    """Run red flag detection and scoring for all listings in parallel.

    Args:
        listings: List of listing dicts (post-filtering, with distance data)
        user_preferences: Dict of user's soft preferences

    Returns:
        List of listings with analysis results added
    """
    client = _get_client()
    if not client:
        logger.warning("[LLM] No API client available. Returning listings without LLM analysis.")
        for listing in listings:
            listing["red_flag_analysis"] = {"red_flags": [], "summary": "Analysis unavailable"}
            listing["score"] = 50
            listing["score_breakdown"] = {}
            listing["explanation"] = "LLM analysis unavailable (no API key)"
        return listings

    logger.info(f"[LLM] Analyzing {len(listings)} listings...")

    # Phase 1: Red flag detection (parallel)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i, listing in enumerate(listings):
            future = executor.submit(analyze_red_flags, listing, client)
            futures[future] = i

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                listings[idx]["red_flag_analysis"] = result
            except Exception as e:
                logger.error(f"[LLM] Red flag analysis failed for listing {idx}: {e}")
                listings[idx]["red_flag_analysis"] = {"red_flags": [], "summary": "Analysis failed"}

    logger.info("[LLM] Red flag analysis complete. Starting scoring...")

    # Phase 2: Scoring (parallel, after red flags are done)
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i, listing in enumerate(listings):
            future = executor.submit(score_listing, listing, user_preferences, client)
            futures[future] = i

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                listings[idx]["score"] = result.get("score", 50)
                listings[idx]["score_breakdown"] = result.get("score_breakdown", {})
                listings[idx]["explanation"] = result.get("explanation", "")
            except Exception as e:
                logger.error(f"[LLM] Scoring failed for listing {idx}: {e}")
                listings[idx]["score"] = 50
                listings[idx]["score_breakdown"] = {}
                listings[idx]["explanation"] = "Scoring failed"

    # Sort by score descending
    listings.sort(key=lambda x: x.get("score", 0), reverse=True)
    logger.info("[LLM] Scoring complete. Listings ranked.")

    return listings


def judge_rankings(listings, user_preferences):
    """LLM-as-Judge: validate the ranking against user criteria.

    Args:
        listings: Ranked list of listing dicts
        user_preferences: Dict of user's preferences

    Returns:
        Validated and potentially re-ranked list
    """
    client = _get_client()
    if not client:
        logger.warning("[LLM] No API client. Skipping judge validation.")
        return listings

    if not listings:
        return listings

    # Prepare summary of ranked listings for the judge
    ranked_summary = []
    for i, listing in enumerate(listings[:20]):  # Only send top 20 to judge
        ranked_summary.append({
            "rank": i + 1,
            "address": listing.get("address", "Unknown"),
            "price": listing.get("price"),
            "bedrooms": listing.get("bedrooms"),
            "bathrooms": listing.get("bathrooms"),
            "score": listing.get("score", 50),
            "explanation": listing.get("explanation", ""),
            "red_flags": listing.get("red_flag_analysis", {}).get("red_flags", []),
            "nearest_shuttle": listing.get("nearest_shuttle", "N/A"),
            "shuttle_duration": listing.get("nearest_shuttle_duration", "N/A"),
        })

    prefs_text = json.dumps(user_preferences, indent=2)
    rankings_text = json.dumps(ranked_summary, indent=2)

    prompt = f"""You are a quality assurance judge for a rental listing ranking system. Review the following ranked list of apartments and the user's original criteria.

Check for: scoring inconsistencies, red flags that should have lowered a score more, preferences that were ignored, or rankings that don't make logical sense.

User's Criteria:
{prefs_text}

Current Ranked List:
{rankings_text}

Return JSON with:
- validated: true if rankings look reasonable, false if major issues found
- adjustments: list of objects with "rank" (int), "new_score" (int), and "reasoning" (string) for any changes
- notes: string with overall assessment of ranking quality

Return ONLY valid JSON, no other text."""

    logger.info("[LLM] Running judge validation...")
    result = _call_llm(client, prompt, system="You are a quality assurance judge for a rental listing ranking system.")

    if isinstance(result, dict) and "adjustments" in result:
        adjustments = result.get("adjustments", [])
        if adjustments:
            logger.info(f"[LLM] Judge made {len(adjustments)} score adjustments")
            for adj in adjustments:
                rank = adj.get("rank", 0) - 1  # Convert to 0-indexed
                if 0 <= rank < len(listings):
                    old_score = listings[rank].get("score", 50)
                    new_score = adj.get("new_score", old_score)
                    listings[rank]["score"] = new_score
                    listings[rank]["judge_adjustment"] = adj.get("reasoning", "")
                    logger.info(f"[LLM] Adjusted rank {rank+1}: {old_score} -> {new_score}")

            # Re-sort after adjustments
            listings.sort(key=lambda x: x.get("score", 0), reverse=True)

        notes = result.get("notes", "")
        if notes:
            logger.info(f"[LLM] Judge notes: {notes}")
    else:
        logger.warning("[LLM] Judge returned unexpected format, keeping original rankings")

    return listings
