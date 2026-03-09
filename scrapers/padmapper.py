"""PadMapper scraper."""

import json
import logging
import requests

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_BOUNDS = {
    "San Francisco": {
        "min_lat": 37.7049, "max_lat": 37.8124,
        "min_lng": -122.5148, "max_lng": -122.3570,
    },
}


class PadMapperScraper(BaseScraper):
    SOURCE_NAME = "PadMapper"

    def scrape(self, city, max_rent, min_beds, min_baths):
        bounds = CITY_BOUNDS.get(city)
        if not bounds:
            logger.warning(f"[PadMapper] No bounds configured for {city}")
            return self._scrape_html(city, max_rent, min_beds, min_baths)

        url = "https://www.padmapper.com/api/t/1/pages/listables"

        payload = {
            "limit": 50,
            "min_price": 0,
            "max_price": int(max_rent) if max_rent else 10000,
            "min_bed": int(min_beds) if min_beds else 0,
            "min_bath": int(min_baths) if min_baths else 0,
            "box": [
                bounds["min_lat"], bounds["min_lng"],
                bounds["max_lat"], bounds["max_lng"],
            ],
        }

        headers = self._get_headers()
        headers["Content-Type"] = "application/json"
        headers["Referer"] = "https://www.padmapper.com/"

        listings = []

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[PadMapper] API failed: {e}")
            return self._scrape_html(city, max_rent, min_beds, min_baths)

        items = data if isinstance(data, list) else data.get("listables", [])
        for item in items[:50]:
            try:
                price = item.get("price") or item.get("min_price")
                address = item.get("address", "")
                beds = item.get("bedrooms") or item.get("beds")
                baths = item.get("bathrooms") or item.get("baths")

                listing_url = item.get("url", "")
                if listing_url and not listing_url.startswith("http"):
                    listing_url = "https://www.padmapper.com" + listing_url

                listings.append({
                    "title": address or f"Listing in {city}",
                    "address": address,
                    "price": price,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "description": item.get("description", ""),
                    "url": listing_url,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[PadMapper] Error parsing item: {e}")

        return listings

    def _scrape_html(self, city, max_rent, min_beds, min_baths):
        """Fallback HTML scraping."""
        from bs4 import BeautifulSoup
        import re

        slug = city.lower().replace(" ", "-")
        url = f"https://www.padmapper.com/apartments/{slug}-ca"

        listings = []
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("[class*='ListItem']") or soup.select("a[href*='/apartment/']")
            for card in cards[:50]:
                link = card if card.name == "a" else card.select_one("a")
                if not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.padmapper.com" + href

                text = card.get_text(strip=True)
                price = None
                m = re.search(r"\$[\d,]+", text)
                if m:
                    try:
                        price = float(m.group().replace("$", "").replace(",", ""))
                    except ValueError:
                        pass

                listings.append({
                    "title": text[:100],
                    "address": "",
                    "price": price,
                    "bedrooms": None,
                    "bathrooms": None,
                    "description": text[:200],
                    "url": href,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
        except Exception as e:
            logger.error(f"[PadMapper] HTML scrape also failed: {e}")

        return listings
