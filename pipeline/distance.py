"""Google Maps distance calculation to shuttle stops and transit."""

import logging

import googlemaps

from config import GOOGLE_MAPS_API_KEY, load_shuttle_stops

logger = logging.getLogger(__name__)


def calculate_distances(listings):
    """Calculate walking distance from each listing to all shuttle stops.

    Updates each listing dict in-place with:
        - nearest_shuttle: name of nearest shuttle stop
        - nearest_shuttle_distance: walking distance text
        - nearest_shuttle_duration: walking duration text
        - shuttle_distances: list of all shuttle stop distances
        - transit_info: nearest public transit info

    Returns the updated listings list.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.warning("[Distance] GOOGLE_MAPS_API_KEY not set. Skipping distance calculation.")
        for listing in listings:
            listing["nearest_shuttle"] = "N/A (API key not set)"
            listing["nearest_shuttle_distance"] = "N/A"
            listing["nearest_shuttle_duration"] = "N/A"
            listing["shuttle_distances"] = []
            listing["transit_info"] = "N/A"
        return listings

    try:
        gmaps = googlemaps.Client(key=GOOGLE_MAPS_API_KEY)
    except Exception as e:
        logger.error(f"[Distance] Failed to initialize Google Maps client: {e}")
        for listing in listings:
            listing["nearest_shuttle"] = "Error"
            listing["nearest_shuttle_distance"] = "N/A"
            listing["nearest_shuttle_duration"] = "N/A"
            listing["shuttle_distances"] = []
            listing["transit_info"] = "N/A"
        return listings

    shuttle_stops = load_shuttle_stops()
    shuttle_destinations = [stop["address"] for stop in shuttle_stops]

    for listing in listings:
        address = listing.get("address", "")
        if not address:
            listing["nearest_shuttle"] = "No address"
            listing["nearest_shuttle_distance"] = "N/A"
            listing["nearest_shuttle_duration"] = "N/A"
            listing["shuttle_distances"] = []
            listing["transit_info"] = "N/A"
            continue

        try:
            # Batch request: one origin, all shuttle stops as destinations
            result = gmaps.distance_matrix(
                origins=[address],
                destinations=shuttle_destinations,
                mode="walking",
            )

            elements = result.get("rows", [{}])[0].get("elements", [])
            shuttle_dists = []
            min_duration_seconds = float("inf")
            nearest_idx = 0

            for i, element in enumerate(elements):
                if element.get("status") == "OK":
                    dist_text = element["distance"]["text"]
                    dur_text = element["duration"]["text"]
                    dur_seconds = element["duration"]["value"]

                    shuttle_dists.append({
                        "stop_name": shuttle_stops[i]["name"],
                        "distance": dist_text,
                        "duration": dur_text,
                        "duration_seconds": dur_seconds,
                    })

                    if dur_seconds < min_duration_seconds:
                        min_duration_seconds = dur_seconds
                        nearest_idx = i
                else:
                    shuttle_dists.append({
                        "stop_name": shuttle_stops[i]["name"],
                        "distance": "N/A",
                        "duration": "N/A",
                        "duration_seconds": float("inf"),
                    })

            listing["shuttle_distances"] = shuttle_dists

            if shuttle_dists and min_duration_seconds < float("inf"):
                nearest = shuttle_dists[nearest_idx]
                listing["nearest_shuttle"] = nearest["stop_name"]
                listing["nearest_shuttle_distance"] = nearest["distance"]
                listing["nearest_shuttle_duration"] = nearest["duration"]
            else:
                listing["nearest_shuttle"] = "Could not calculate"
                listing["nearest_shuttle_distance"] = "N/A"
                listing["nearest_shuttle_duration"] = "N/A"

            # Also get transit info (nearest BART/Muni)
            try:
                transit_result = gmaps.places_nearby(
                    location=address,
                    radius=1000,
                    type="transit_station",
                )
                if transit_result.get("results"):
                    nearest_transit = transit_result["results"][0]
                    listing["transit_info"] = nearest_transit.get("name", "Transit station nearby")
                else:
                    listing["transit_info"] = "No transit stations found within 1km"
            except Exception as e:
                logger.debug(f"[Distance] Transit lookup failed for {address}: {e}")
                listing["transit_info"] = "N/A"

            logger.debug(f"[Distance] {address}: nearest shuttle = {listing['nearest_shuttle']} ({listing['nearest_shuttle_duration']})")

        except Exception as e:
            logger.error(f"[Distance] Error calculating distance for {address}: {e}")
            listing["nearest_shuttle"] = "Error"
            listing["nearest_shuttle_distance"] = "N/A"
            listing["nearest_shuttle_duration"] = "N/A"
            listing["shuttle_distances"] = []
            listing["transit_info"] = "N/A"

    return listings
