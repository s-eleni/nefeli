"""Nefeli — Rental Apartment Monitoring Agent.

Flask web app that orchestrates the full pipeline:
1. User preferences form
2. Listing acquisition (scrapers + APIs)
3. Deduplication
4. Hard filtering
5. Distance calculation
6. LLM analysis (red flags + scoring + judge)
7. Outreach message drafting
8. Email alert
"""

import io
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, render_template, request, redirect, url_for

import config
from config import FLASK_SECRET_KEY, NEIGHBORHOODS, DEFAULT_RED_FLAGS

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
from pipeline.dedup import deduplicate
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


@app.route("/")
def index():
    """Render the preferences form."""
    return render_template(
        "index.html",
        neighborhoods_json=json.dumps(NEIGHBORHOODS),
        default_red_flags=DEFAULT_RED_FLAGS,
    )


@app.route("/api/neighborhoods")
def get_neighborhoods():
    """Return neighborhood list for a given city (AJAX endpoint)."""
    city = request.args.get("city", "San Francisco")
    return json.dumps(NEIGHBORHOODS.get(city, []))


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
        logger.info("NEFELI RENTAL AGENT — PIPELINE STARTING")
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

        if not filtered_listings:
            logger.warning("No listings passed hard filters!")
            # Return results page with no listings
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
