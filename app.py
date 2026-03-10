"""Nido — Rental Apartment Finder.

Flask web app that orchestrates the full pipeline:
1. Chatbot intake (conversational preferences)
2. LLM extraction (chat → structured criteria)
3. Review form (pre-filled, editable)
4. Listing acquisition (scrapers + APIs)
5. Deduplication
6. Hard filtering
7. Distance calculation
8. LLM analysis (red flags + scoring + judge)
9. Outreach message drafting
10. Email alert
"""

import io
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
from flask import Flask, render_template, request, redirect, url_for, jsonify, session

import config
from config import (
    FLASK_SECRET_KEY, NEIGHBORHOODS, DEFAULT_RED_FLAGS, ANTHROPIC_API_KEY,
)

# Import scrapers
from scrapers.craigslist import CraigslistScraper
from scrapers.zillow import ZillowScraper
from scrapers.apartments_com import ApartmentsComScraper
from scrapers.hotpads import HotpadsScraper
from scrapers.redfin import RedfinScraper
from scrapers.trulia import TruliaScraper
from scrapers.rent_com import RentComScraper
from scrapers.zumper import ZumperScraper
from scrapers.padmapper import PadMapperScraper
from scrapers.api_sources import RentCastScraper, RealtyMoleScraper

# Import pipeline
from pipeline.dedup import deduplicate, mark_as_seen
from pipeline.filters import apply_hard_filters
from pipeline.distance import calculate_distances
from pipeline.llm_analysis import run_analysis, judge_rankings
from pipeline.outreach import draft_outreach_messages
from pipeline.email_sender import send_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Claude client for chat
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# All available scrapers
ALL_SCRAPERS = [
    CraigslistScraper(),
    ZillowScraper(),
    ApartmentsComScraper(),
    HotpadsScraper(),
    RedfinScraper(),
    TruliaScraper(),
    RentComScraper(),
    ZumperScraper(),
    PadMapperScraper(),
    RentCastScraper(),
    RealtyMoleScraper(),
]

# Available neighborhoods as a formatted string for the system prompt
NEIGHBORHOODS_STR = ", ".join(NEIGHBORHOODS.get("San Francisco", []))

CHAT_SYSTEM_PROMPT = f"""You are Nido, a friendly rental apartment search assistant for San Francisco. You help people find apartments by having a brief, warm conversation.

Your job:
1. Understand what they're looking for: budget, neighborhoods, bedrooms/bathrooms, parking, laundry, and any other preferences or dealbreakers.
2. Be conversational and natural — like texting a knowledgeable friend. Don't list questions as a checklist.
3. Infer reasonable defaults from context. If they say "1-bed" you don't need to ask about bathrooms (assume 1).
4. Keep it to 2-3 exchanges max. After each response, assess if you have enough to start a search. You need at minimum: a rough budget and general area/neighborhood preference.
5. Ask about what's genuinely missing — don't re-ask about things they've already covered.
6. Available SF neighborhoods: {NEIGHBORHOODS_STR}

When you have enough information, end your message with the EXACT marker: [READY]
This marker tells the system to extract criteria and show the review form. Include a brief transition like "Got it — I've put together your search criteria. Take a look and tweak anything before I start searching." followed by [READY].

IMPORTANT: Do NOT include [READY] until you have at least a budget range and some location preferences. After 2-3 exchanges you should have enough — wrap it up."""

EXTRACTION_PROMPT = """Extract structured apartment search criteria from this conversation. Return ONLY valid JSON matching this exact schema — no markdown, no explanation:

{{
  "city": "San Francisco",
  "max_rent": <number>,
  "min_beds": <number, default 1>,
  "min_baths": <number, default 1>,
  "parking": <list of strings from: "Garage", "Covered", "Carport", "Driveway", "Street", "Off-street", "No preference">,
  "laundry": <list of strings from: "In-unit", "In-building/shared", "Hookups only", "Laundromat nearby", "No preference">,
  "neighborhoods": <list of neighborhood names>,
  "transit_proximity": <"important" or "not_important">,
  "natural_lighting": <"important" or "not_important">,
  "floor_preference": <"upper" or "no_preference">,
  "entrance_preference": <"avoid_alley" or "no_preference">,
  "other_preferences": <string with any extra preferences>,
  "red_flags": <list of strings from the default flags that are relevant>,
  "custom_red_flags": <string, comma-separated custom flags or empty>,
  "email": <string or empty>
}}

Available SF neighborhoods: {neighborhoods}

Default red flags (include all unless user specifically said they don't care about some):
{red_flags}

Rules:
- Infer reasonable defaults for anything not explicitly mentioned
- If parking not mentioned, use ["No preference"]
- If laundry not mentioned, use ["No preference"]
- If no specific neighborhoods mentioned, include popular ones like Mission, Noe Valley, Hayes Valley, Castro, Inner Sunset, etc.
- Budget: use the max they mentioned. If they said "around $3k", use 3000. If "under $3500", use 3500.
- Be generous with neighborhood selection — include any that seem plausible from the conversation

Conversation:
{conversation}"""


@app.route("/")
def index():
    """Render the chatbot intake page."""
    return render_template("chat.html")


@app.route("/api/neighborhoods")
def get_neighborhoods():
    """Return neighborhood list for a given city (AJAX endpoint)."""
    city = request.args.get("city", "San Francisco")
    return jsonify(NEIGHBORHOODS.get(city, []))


@app.route("/api/chat", methods=["POST"])
def chat():
    """Handle a chatbot message exchange. Returns assistant response or extraction."""
    data = request.get_json()
    messages = data.get("messages", [])

    # Build messages for Claude (skip the first assistant greeting — it's in system prompt)
    claude_messages = []
    for msg in messages:
        if msg["role"] in ("user", "assistant"):
            claude_messages.append({"role": msg["role"], "content": msg["content"]})

    # Skip the initial assistant greeting in messages to Claude since it's implied by system prompt
    if claude_messages and claude_messages[0]["role"] == "assistant":
        claude_messages = claude_messages[1:]

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            system=CHAT_SYSTEM_PROMPT,
            messages=claude_messages,
        )
        assistant_text = response.content[0].text

        # Check if conversation is done
        if "[READY]" in assistant_text:
            clean_text = assistant_text.replace("[READY]", "").strip()

            # Run extraction
            extraction = extract_criteria(messages + [{"role": "assistant", "content": clean_text}])

            return jsonify({
                "done": True,
                "message": clean_text,
                "extraction": extraction,
            })
        else:
            return jsonify({
                "done": False,
                "message": assistant_text,
            })

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return jsonify({
            "done": False,
            "message": "Sorry, I had trouble processing that. Could you try again?",
        }), 500


def extract_criteria(messages):
    """Use Claude to extract structured search criteria from conversation history."""
    conversation_text = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Nido'}: {m['content']}"
        for m in messages
    )

    neighborhoods_str = ", ".join(NEIGHBORHOODS.get("San Francisco", []))
    red_flags_str = "\n".join(f"- {f}" for f in DEFAULT_RED_FLAGS)

    prompt = EXTRACTION_PROMPT.format(
        neighborhoods=neighborhoods_str,
        red_flags=red_flags_str,
        conversation=conversation_text,
    )

    try:
        response = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        return json.loads(raw)
    except Exception as e:
        logger.error(f"Extraction error: {e}")
        # Return sensible defaults
        return {
            "city": "San Francisco",
            "max_rent": 3500,
            "min_beds": 1,
            "min_baths": 1,
            "parking": ["No preference"],
            "laundry": ["No preference"],
            "neighborhoods": ["Mission", "Noe Valley", "Hayes Valley", "Castro", "Inner Sunset"],
            "transit_proximity": "important",
            "natural_lighting": "important",
            "floor_preference": "no_preference",
            "entrance_preference": "no_preference",
            "other_preferences": "",
            "red_flags": list(DEFAULT_RED_FLAGS),
            "custom_red_flags": "",
            "email": "",
        }


@app.route("/review", methods=["POST"])
def review():
    """Show the pre-filled review form with extracted criteria."""
    extraction_raw = request.form.get("extraction", "{}")
    try:
        data = json.loads(extraction_raw)
    except json.JSONDecodeError:
        data = {}

    # Ensure all keys exist with defaults
    defaults = {
        "city": "San Francisco",
        "max_rent": 3500,
        "min_beds": 1,
        "min_baths": 1,
        "parking": ["No preference"],
        "laundry": ["No preference"],
        "neighborhoods": [],
        "transit_proximity": "important",
        "natural_lighting": "important",
        "floor_preference": "no_preference",
        "entrance_preference": "no_preference",
        "other_preferences": "",
        "red_flags": list(DEFAULT_RED_FLAGS),
        "custom_red_flags": "",
        "email": "",
    }
    for key, val in defaults.items():
        data.setdefault(key, val)

    city = data.get("city", "San Francisco")
    neighborhoods = NEIGHBORHOODS.get(city, [])

    return render_template(
        "review.html",
        data=data,
        neighborhoods=neighborhoods,
        default_red_flags=DEFAULT_RED_FLAGS,
    )


@app.route("/run", methods=["POST"])
def run_pipeline():
    """Execute the full rental search pipeline."""

    # Capture log output for display
    log_capture = io.StringIO()
    log_handler = logging.StreamHandler(log_capture)
    log_handler.setLevel(logging.INFO)
    log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger().addHandler(log_handler)

    try:
        # Parse form data
        city = request.form.get("city", "San Francisco")
        max_rent = request.form.get("max_rent", "3500")
        min_beds = request.form.get("min_beds", "1")
        min_baths = request.form.get("min_baths", "1")
        parking = request.form.getlist("parking")
        laundry = request.form.getlist("laundry")
        neighborhoods = request.form.getlist("neighborhoods")
        transit_pref = request.form.get("transit_preference", "important")
        lighting = request.form.get("lighting", "important")
        floor_pref = request.form.get("floor_preference", "upper")
        entrance_pref = request.form.get("entrance_preference", "avoid_alley")
        other_prefs = request.form.get("other_preferences", "")
        red_flags = request.form.getlist("red_flags")
        custom_red_flags = request.form.get("custom_red_flags", "")
        email = request.form.get("email", "")

        if custom_red_flags:
            red_flags.extend([f.strip() for f in custom_red_flags.split(",") if f.strip()])

        logger.info("=" * 60)
        logger.info("NIDO RENTAL AGENT — PIPELINE STARTING")
        logger.info("=" * 60)
        logger.info(f"City: {city}, Max Rent: ${max_rent}, Beds: {min_beds}+, Baths: {min_baths}+")
        logger.info(f"Parking: {parking}, Laundry: {laundry}")
        logger.info(f"Preferred neighborhoods: {len(neighborhoods)} selected")

        # Build user preferences dict for LLM
        user_preferences = {
            "city": city,
            "max_rent": max_rent,
            "min_bedrooms": min_beds,
            "min_bathrooms": min_baths,
            "preferred_neighborhoods": neighborhoods,
            "transit_proximity": transit_pref,
            "natural_lighting": lighting,
            "floor_preference": floor_pref,
            "entrance_preference": entrance_pref,
            "other_preferences": other_prefs,
            "red_flags_to_watch": red_flags,
            "parking_preferences": parking,
            "laundry_preferences": laundry,
        }

        # Build hard filter dict
        hard_filters = {
            "max_rent": float(max_rent) if max_rent else None,
            "min_beds": int(min_beds) if min_beds else None,
            "min_baths": float(min_baths) if min_baths else None,
            "parking": parking,
            "laundry": laundry,
            "neighborhoods": neighborhoods,
        }

        # ---- STEP 1: Listing Acquisition (parallel scraping) ----
        logger.info("-" * 40)
        logger.info("STEP 1: Listing Acquisition")
        logger.info("-" * 40)

        all_listings = []

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}
            for scraper in ALL_SCRAPERS:
                future = executor.submit(
                    scraper.safe_scrape, city, max_rent, min_beds, min_baths
                )
                futures[future] = scraper.SOURCE_NAME

            for future in as_completed(futures):
                source = futures[future]
                try:
                    listings = future.result()
                    if listings:
                        all_listings.extend(listings)
                        logger.info(f"  {source}: {len(listings)} listings")
                    else:
                        logger.info(f"  {source}: 0 listings")
                except Exception as e:
                    logger.error(f"  {source}: failed — {e}")

        logger.info(f"Total raw listings: {len(all_listings)}")

        # ---- STEP 2: Deduplication ----
        logger.info("-" * 40)
        logger.info("STEP 2: Deduplication")
        logger.info("-" * 40)

        unique_listings = deduplicate(all_listings)

        # ---- STEP 3: Hard Filtering ----
        logger.info("-" * 40)
        logger.info("STEP 3: Hard Filtering")
        logger.info("-" * 40)

        filtered_listings, filter_stats = apply_hard_filters(unique_listings, hard_filters)

        # Mark filtered listings as seen so they aren't re-processed on future runs
        mark_as_seen(filtered_listings)

        if not filtered_listings:
            logger.warning("No listings passed hard filters!")
            logging.getLogger().removeHandler(log_handler)
            return render_template(
                "results.html",
                listings=[],
                stats=filter_stats,
                top_score="N/A",
                email_sent=False,
                email_status="No listings found matching your criteria.",
                pipeline_log=log_capture.getvalue(),
            )

        # ---- STEP 4: Distance Calculation ----
        logger.info("-" * 40)
        logger.info("STEP 4: Distance Calculation")
        logger.info("-" * 40)

        filtered_listings = calculate_distances(filtered_listings)

        # ---- STEP 5: LLM Analysis (Red Flags + Scoring) ----
        logger.info("-" * 40)
        logger.info("STEP 5: LLM Analysis")
        logger.info("-" * 40)

        analyzed_listings = run_analysis(filtered_listings, user_preferences)

        # ---- STEP 6: LLM-as-Judge Validation ----
        logger.info("-" * 40)
        logger.info("STEP 6: Judge Validation")
        logger.info("-" * 40)

        validated_listings = judge_rankings(analyzed_listings, user_preferences)

        # ---- STEP 7: Outreach Message Drafting ----
        logger.info("-" * 40)
        logger.info("STEP 7: Outreach Drafting")
        logger.info("-" * 40)

        final_listings = draft_outreach_messages(validated_listings, user_preferences)

        # ---- STEP 8: Email Alert ----
        logger.info("-" * 40)
        logger.info("STEP 8: Email Alert")
        logger.info("-" * 40)

        email_sent, email_status = send_email(email, final_listings, filter_stats)

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)

        top_score = final_listings[0].get("score", "N/A") if final_listings else "N/A"

        logging.getLogger().removeHandler(log_handler)

        return render_template(
            "results.html",
            listings=final_listings,
            stats=filter_stats,
            top_score=top_score,
            email_sent=email_sent,
            email_status=email_status,
            pipeline_log=log_capture.getvalue(),
        )

    except Exception as e:
        logger.error(f"Pipeline error: {e}", exc_info=True)
        logging.getLogger().removeHandler(log_handler)
        return render_template(
            "results.html",
            listings=[],
            stats={"total_input": 0, "passed": 0},
            top_score="N/A",
            email_sent=False,
            email_status=f"Pipeline error: {e}",
            pipeline_log=log_capture.getvalue(),
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=config.FLASK_DEBUG)
