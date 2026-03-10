"""Hard filtering logic for rental listings."""

import logging
import re

logger = logging.getLogger(__name__)

# Keywords for matching parking and laundry from description text
PARKING_KEYWORDS = {
    "Garage": ["garage", "attached garage", "detached garage"],
    "Covered": ["covered parking", "covered spot"],
    "Carport": ["carport"],
    "Driveway": ["driveway"],
    "Street": ["street parking"],
    "Off-street": ["off-street", "off street", "dedicated parking", "parking spot", "parking space"],
}

LAUNDRY_KEYWORDS = {
    "In-unit": ["in-unit", "in unit", "washer/dryer in unit", "w/d in unit", "washer dryer included",
                 "in-unit laundry", "washer and dryer"],
    "In-building/shared": ["shared laundry", "on-site laundry", "laundry room", "laundry on site",
                           "in-building", "common laundry", "laundry facility"],
    "Hookups only": ["hookup", "hook-up", "hook up", "w/d hookup"],
    "Laundromat nearby": ["laundromat", "laundry nearby"],
}


def apply_hard_filters(listings, filters):
    """Apply hard filters to listings and return those that pass.

    Args:
        listings: List of listing dicts
        filters: Dict with keys: max_rent, min_beds, min_baths,
                 parking (list), laundry (list), neighborhoods (list)

    Returns:
        Tuple of (passed_listings, filter_stats)
    """
    max_rent = filters.get("max_rent")
    min_beds = filters.get("min_beds")
    min_baths = filters.get("min_baths")
    parking_prefs = filters.get("parking", [])
    laundry_prefs = filters.get("laundry", [])
    neighborhoods = [n.lower() for n in filters.get("neighborhoods", [])]

    passed = []
    stats = {
        "total_input": len(listings),
        "filtered_price": 0,
        "filtered_beds": 0,
        "filtered_baths": 0,
        "filtered_parking": 0,
        "filtered_laundry": 0,
        "passed": 0,
    }

    for listing in listings:
        description = (listing.get("description") or "").lower()
        address = (listing.get("address") or "").lower()

        # Price filter
        price = listing.get("price")
        if max_rent and price is not None and price > float(max_rent):
            stats["filtered_price"] += 1
            continue

        # Bedroom filter
        beds = listing.get("bedrooms")
        if min_beds and beds is not None and beds < int(min_beds):
            stats["filtered_beds"] += 1
            continue

        # Bathroom filter
        baths = listing.get("bathrooms")
        if min_baths and baths is not None and baths < float(min_baths):
            stats["filtered_baths"] += 1
            continue

        # Parking filter — only reject if description mentions a parking type
        # that doesn't match preferences. If parking isn't mentioned, let it through.
        if parking_prefs and "No preference" not in parking_prefs:
            if description:
                # Check if description mentions ANY parking keyword at all
                mentions_parking = False
                for all_kws in PARKING_KEYWORDS.values():
                    for kw in all_kws:
                        if kw in description:
                            mentions_parking = True
                            break
                    if mentions_parking:
                        break

                if mentions_parking:
                    # Parking is mentioned — check if it matches a preferred type
                    parking_match = False
                    for pref in parking_prefs:
                        keywords = PARKING_KEYWORDS.get(pref, [pref.lower()])
                        for kw in keywords:
                            if kw in description:
                                parking_match = True
                                break
                        if parking_match:
                            break
                    if not parking_match:
                        stats["filtered_parking"] += 1
                        continue
                # If parking not mentioned at all, let it through (unknown)

        # Laundry filter — same logic: only reject if a non-matching type is mentioned
        if laundry_prefs and "No preference" not in laundry_prefs:
            if description:
                mentions_laundry = False
                for all_kws in LAUNDRY_KEYWORDS.values():
                    for kw in all_kws:
                        if kw in description:
                            mentions_laundry = True
                            break
                    if mentions_laundry:
                        break

                if mentions_laundry:
                    laundry_match = False
                    for pref in laundry_prefs:
                        keywords = LAUNDRY_KEYWORDS.get(pref, [pref.lower()])
                        for kw in keywords:
                            if kw in description:
                                laundry_match = True
                                break
                        if laundry_match:
                            break
                    if not laundry_match:
                        stats["filtered_laundry"] += 1
                        continue

        passed.append(listing)

    stats["passed"] = len(passed)

    logger.info(f"[Filter] Input: {stats['total_input']}, Passed: {stats['passed']}")
    logger.info(f"[Filter] Filtered by price: {stats['filtered_price']}")
    logger.info(f"[Filter] Filtered by beds: {stats['filtered_beds']}")
    logger.info(f"[Filter] Filtered by baths: {stats['filtered_baths']}")
    logger.info(f"[Filter] Filtered by parking: {stats['filtered_parking']}")
    logger.info(f"[Filter] Filtered by laundry: {stats['filtered_laundry']}")

    return passed, stats
