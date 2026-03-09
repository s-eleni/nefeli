"""Zumper scraper."""

import json
import logging
import requests

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_COORDS = {
    "San Francisco": {"lat": 37.7749, "lng": -122.4194},
    "New York": {"lat": 40.7128, "lng": -74.0060},
    "Los Angeles": {"lat": 34.0522, "lng": -118.2437},
}


class ZumperScraper(BaseScraper):
    SOURCE_NAME = "Zumper"

    def scrape(self, city, max_rent, min_beds, min_baths):
        coords = CITY_COORDS.get(city, CITY_COORDS["San Francisco"])

        # Try Zumper's API endpoint
        url = "https://www.zumper.com/api/t/1/pages/listables"

        payload = {
            "baths": {"min": int(min_baths) if min_baths else None},
            "beds": {"min": int(min_beds) if min_beds else None},
            "budget": {"max": int(max_rent) if max_rent else None},
            "box": [
                coords["lat"] - 0.05, coords["lng"] - 0.05,
                coords["lat"] + 0.05, coords["lng"] + 0.05,
            ],
            "limit": 50,
        }

        headers = self._get_headers()
        headers["Content-Type"] = "application/json"
        headers["Referer"] = "https://www.zumper.com/"

        listings = []

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"[Zumper] API request failed: {e}")
            return self._scrape_html(city, max_rent, min_beds, min_baths)

        items = data if isinstance(data, list) else data.get("listables", [])
        for item in items[:50]:
            try:
                price = item.get("price") or item.get("min_price")
                address = item.get("address", "")
                beds = item.get("bedrooms") or item.get("beds")
                baths = item.get("bathrooms") or item.get("baths")
                url = item.get("url", "")
                if url and not url.startswith("http"):
                    url = "https://www.zumper.com" + url

                photos = []
                if item.get("photos"):
                    for p in item["photos"][:5]:
                        if isinstance(p, dict):
                            photos.append(p.get("url", ""))
                        elif isinstance(p, str):
                            photos.append(p)

                listings.append({
                    "title": address or f"{beds}BR/{baths}BA in {city}",
                    "address": address,
                    "price": price,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "description": item.get("description", address),
                    "url": url,
                    "photo_urls": photos,
                    "date_posted": item.get("posted_date"),
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Zumper] Error parsing item: {e}")

        return listings

    def _scrape_html(self, city, max_rent, min_beds, min_baths):
        """Fallback HTML scraping."""
        from bs4 import BeautifulSoup
        import re

        slug = city.lower().replace(" ", "-")
        url = f"https://www.zumper.com/apartments-for-rent/{slug}-ca"

        listings = []
        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select("[class*='ListingCard']") or soup.select("a[href*='/apartment/']")
            for card in cards[:50]:
                link = card if card.name == "a" else card.select_one("a")
                if not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.zumper.com" + href

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
            logger.error(f"[Zumper] HTML scrape also failed: {e}")

        return listings
