"""API-based rental listing sources: RentCast, RealtyMole, etc."""

import logging
import requests

from scrapers.base_scraper import BaseScraper
from config import RENTCAST_API_KEY

logger = logging.getLogger(__name__)


class RentCastScraper(BaseScraper):
    """RentCast API integration.

    Sign up at https://www.rentcast.io/api to get an API key.
    Free tier allows 50 requests/month.
    Set RENTCAST_API_KEY environment variable.
    """

    SOURCE_NAME = "RentCast"

    def scrape(self, city, max_rent, min_beds, min_baths):
        if not RENTCAST_API_KEY:
            logger.warning("[RentCast] No API key set (RENTCAST_API_KEY). Skipping.")
            return []

        url = "https://api.rentcast.io/v1/listings/rental/long-term"
        params = {
            "city": city,
            "state": "CA",
            "status": "Active",
            "limit": 50,
        }
        if max_rent:
            params["maxPrice"] = int(max_rent)
        if min_beds:
            params["bedrooms"] = int(min_beds)
        if min_baths:
            params["bathrooms"] = int(min_baths)

        headers = {
            "Accept": "application/json",
            "X-Api-Key": RENTCAST_API_KEY,
        }

        listings = []

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[RentCast] API request failed: {e}")
            return []

        items = data if isinstance(data, list) else data.get("listings", [])
        for item in items:
            try:
                address_parts = [
                    item.get("addressLine1", ""),
                    item.get("city", ""),
                    item.get("state", ""),
                    item.get("zipCode", ""),
                ]
                address = ", ".join(p for p in address_parts if p)

                listings.append({
                    "title": address,
                    "address": address,
                    "price": item.get("price"),
                    "bedrooms": item.get("bedrooms"),
                    "bathrooms": item.get("bathrooms"),
                    "description": item.get("description", address),
                    "url": item.get("listingUrl", ""),
                    "photo_urls": item.get("photos", [])[:5],
                    "date_posted": item.get("listedDate"),
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[RentCast] Error parsing item: {e}")

        return listings


class RealtyMoleScraper(BaseScraper):
    """RealtyMole API integration.

    Uses RapidAPI. Sign up at https://rapidapi.com/realtymole/api/realty-mole-property-api
    Free tier allows 50 requests/month.
    """

    SOURCE_NAME = "RealtyMole"
    RAPIDAPI_KEY_ENV = "RAPIDAPI_KEY"

    def scrape(self, city, max_rent, min_beds, min_baths):
        import os
        api_key = os.environ.get(self.RAPIDAPI_KEY_ENV, "")
        if not api_key:
            logger.warning(f"[RealtyMole] No API key set ({self.RAPIDAPI_KEY_ENV}). Skipping.")
            return []

        url = "https://realty-mole-property-api.p.rapidapi.com/rentalListings"
        params = {
            "city": city,
            "state": "CA",
            "limit": 50,
        }
        if max_rent:
            params["maxPrice"] = int(max_rent)
        if min_beds:
            params["bedrooms"] = int(min_beds)
        if min_baths:
            params["bathrooms"] = int(min_baths)

        headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": "realty-mole-property-api.p.rapidapi.com",
        }

        listings = []

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[RealtyMole] API request failed: {e}")
            return []

        items = data if isinstance(data, list) else []
        for item in items:
            try:
                address = item.get("formattedAddress", "") or item.get("addressLine1", "")

                listings.append({
                    "title": address,
                    "address": address,
                    "price": item.get("price"),
                    "bedrooms": item.get("bedrooms"),
                    "bathrooms": item.get("bathrooms"),
                    "description": item.get("description", address),
                    "url": item.get("listingUrl", ""),
                    "photo_urls": item.get("photos", [])[:5],
                    "date_posted": item.get("listedDate"),
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[RealtyMole] Error parsing item: {e}")

        return listings
