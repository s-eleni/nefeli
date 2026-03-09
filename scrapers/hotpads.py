"""Hotpads scraper."""

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
}


class HotpadsScraper(BaseScraper):
    SOURCE_NAME = "Hotpads"

    def scrape(self, city, max_rent, min_beds, min_baths):
        slug = CITY_SLUGS.get(city, city.lower().replace(" ", "-") + "-ca")
        url = f"https://hotpads.com/{slug}/apartments-for-rent"

        params = {
            "maxPrice": int(max_rent) if max_rent else "",
            "beds": int(min_beds) if min_beds else "",
            "baths": int(min_baths) if min_baths else "",
        }
        params = {k: v for k, v in params.items() if v}

        listings = []

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Hotpads] Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("[data-testid='listing-card']") or soup.select(".ListingCard")
        if not cards:
            cards = soup.select("a[href*='/pad/']")

        for card in cards[:50]:
            try:
                if card.name == "a":
                    link = card
                else:
                    link = card.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://hotpads.com" + href

                title = link.get_text(strip=True)[:100]

                price = None
                price_el = card.select_one("[class*='price']") or card.select_one("[class*='Price']")
                if price_el:
                    m = re.search(r"[\d,]+", price_el.get_text())
                    if m:
                        try:
                            price = float(m.group().replace(",", ""))
                        except ValueError:
                            pass

                listings.append({
                    "title": title,
                    "address": "",
                    "price": price,
                    "bedrooms": None,
                    "bathrooms": None,
                    "description": title,
                    "url": href,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Hotpads] Error parsing card: {e}")

        return listings
