"""LLM-powered outreach message drafting for top listings."""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic

from config import ANTHROPIC_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)


def draft_outreach_messages(listings, user_preferences, top_n=5):
    """Draft personalized outreach messages for the top N listings.

    Args:
        listings: Ranked list of listing dicts
        user_preferences: Dict of user preferences
        top_n: Number of top listings to draft messages for

    Returns:
        Updated listings with 'outreach_message' field added to top N
    """
    if not ANTHROPIC_API_KEY:
        logger.warning("[Outreach] No API key. Skipping outreach drafting.")
        for listing in listings[:top_n]:
            listing["outreach_message"] = "(Outreach drafting unavailable — no API key)"
        return listings

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    top_listings = listings[:top_n]

    prefs_text = json.dumps(user_preferences, indent=2)

    def draft_single(listing):
        address = listing.get("address", "the listing")
        price = listing.get("price", "N/A")
        beds = listing.get("bedrooms", "N/A")
        baths = listing.get("bathrooms", "N/A")
        description = listing.get("description", "")[:500]
        explanation = listing.get("explanation", "")

        prompt = f"""Draft a brief, professional, and friendly email to the property manager or listing agent for this apartment. The renter is interested in scheduling a viewing.

Personalize the message by referencing specific things from the listing that appeal to the renter (based on their preferences). Keep it to 3-4 sentences. Be warm but not overly casual. Include a placeholder for the renter's name and phone number.

Listing Details:
- Address: {address}
- Price: ${price}/month
- Bedrooms: {beds}, Bathrooms: {baths}
- Description: {description}
- Why it scored well: {explanation}

Renter's Preferences:
{prefs_text}

Write ONLY the email body text, no subject line or metadata."""

        try:
            response = client.messages.create(
                model=LLM_MODEL,
                max_tokens=500,
                system="You are a helpful assistant that drafts professional apartment inquiry emails.",
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"[Outreach] Failed to draft message for {address}: {e}")
            return f"(Failed to generate outreach message: {e})"

    logger.info(f"[Outreach] Drafting messages for top {len(top_listings)} listings...")

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for i, listing in enumerate(top_listings):
            future = executor.submit(draft_single, listing)
            futures[future] = i

        for future in as_completed(futures):
            idx = futures[future]
            try:
                message = future.result()
                listings[idx]["outreach_message"] = message
            except Exception as e:
                logger.error(f"[Outreach] Error: {e}")
                listings[idx]["outreach_message"] = "(Error generating message)"

    logger.info("[Outreach] Message drafting complete.")
    return listings
