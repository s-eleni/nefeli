"""Zillow Rentals scraper."""

import json
import logging
import re
import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_SLUGS = {
    "San Francisco": "san-francisco-ca",
    "New York": "new-york-ny",
    "Los Angeles": "los-angeles-ca",
    "Chicago": "chicago-il",
    "Seattle": "seattle-wa",
}


class ZillowScraper(BaseScraper):
    SOURCE_NAME = "Zillow"

    def scrape(self, city, max_rent, min_beds, min_baths):
        slug = CITY_SLUGS.get(city, city.lower().replace(" ", "-") + "-ca")
        url = f"https://www.zillow.com/{slug}/rentals/"

        params = {
            "searchQueryState": json.dumps({
                "pagination": {},
                "isMapVisible": False,
                "filterState": {
                    "price": {"max": int(max_rent)},
                    "beds": {"min": int(min_beds)},
                    "baths": {"min": int(min_baths)},
                    "fr": {"value": True},
                    "fsba": {"value": False},
                    "fsbo": {"value": False},
                    "nc": {"value": False},
                    "cmsn": {"value": False},
                    "auc": {"value": False},
                    "fore": {"value": False},
                },
            })
        }

        headers = self._get_headers()
        headers["Referer"] = "https://www.zillow.com/"

        listings = []

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Zillow] Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Zillow embeds listing data in a script tag
        scripts = soup.find_all("script", type="application/json")
        for script in scripts:
            try:
                data = json.loads(script.string)
                results = self._extract_results(data)
                if results:
                    for r in results[:50]:
                        listing = self._parse_result(r)
                        if listing:
                            listings.append(listing)
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        # Fallback: parse HTML cards directly
        if not listings:
            cards = soup.select("article.property-card") or soup.select("[data-test='property-card']")
            for card in cards[:50]:
                try:
                    listing = self._parse_card(card)
                    if listing:
                        listings.append(listing)
                except Exception as e:
                    logger.debug(f"[Zillow] Error parsing card: {e}")

        return listings

    def _extract_results(self, data):
        """Recursively search JSON data for listing results."""
        if isinstance(data, dict):
            if "listResults" in data:
                return data["listResults"]
            if "searchResults" in data:
                sr = data["searchResults"]
                if isinstance(sr, dict) and "listResults" in sr:
                    return sr["listResults"]
            for v in data.values():
                result = self._extract_results(v)
                if result:
                    return result
        elif isinstance(data, list):
            for item in data:
                result = self._extract_results(item)
                if result:
                    return result
        return None

    def _parse_result(self, r):
        try:
            price = r.get("unformattedPrice") or r.get("price", "")
            if isinstance(price, str):
                price = re.sub(r"[^\d.]", "", price)
                price = float(price) if price else None

            beds = r.get("beds")
            baths = r.get("baths")

            return {
                "title": r.get("statusText", "") + " " + r.get("address", ""),
                "address": r.get("address", "") or r.get("addressStreet", ""),
                "price": price,
                "bedrooms": beds,
                "bathrooms": baths,
                "description": r.get("address", ""),
                "url": r.get("detailUrl", ""),
                "photo_urls": [r.get("imgSrc", "")] if r.get("imgSrc") else [],
                "date_posted": None,
                "source": self.SOURCE_NAME,
            }
        except Exception as e:
            logger.debug(f"[Zillow] Error parsing result: {e}")
            return None

    def _parse_card(self, card):
        link = card.select_one("a")
        url = link.get("href", "") if link else ""
        if url and not url.startswith("http"):
            url = "https://www.zillow.com" + url

        title_el = card.select_one("[data-test='property-card-addr']") or card.select_one("address")
        title = title_el.get_text(strip=True) if title_el else ""

        price_el = card.select_one("[data-test='property-card-price']") or card.select_one(".property-card-price")
        price_text = price_el.get_text(strip=True) if price_el else ""
        price = None
        if price_text:
            m = re.search(r"[\d,]+", price_text.replace(",", ""))
            if m:
                try:
                    price = float(m.group().replace(",", ""))
                except ValueError:
                    pass

        return {
            "title": title,
            "address": title,
            "price": price,
            "bedrooms": None,
            "bathrooms": None,
            "description": title,
            "url": url,
            "photo_urls": [],
            "date_posted": None,
            "source": self.SOURCE_NAME,
        }
