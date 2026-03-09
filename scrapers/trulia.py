"""Trulia Rentals scraper."""

import logging
import re
import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_SLUGS = {
    "San Francisco": "San_Francisco,CA",
    "New York": "New_York,NY",
    "Los Angeles": "Los_Angeles,CA",
}


class TruliaScraper(BaseScraper):
    SOURCE_NAME = "Trulia"

    def scrape(self, city, max_rent, min_beds, min_baths):
        slug = CITY_SLUGS.get(city, city.replace(" ", "_") + ",CA")
        url = f"https://www.trulia.com/for_rent/{slug}/"

        filters = []
        if max_rent:
            filters.append(f"0-{int(max_rent)}_price")
        if min_beds:
            filters.append(f"{int(min_beds)}p_beds")

        if filters:
            url += "/".join(filters) + "/"

        listings = []

        try:
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Trulia] Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("[data-testid='search-result-list-container'] li") or soup.select(".resultCard")
        if not cards:
            cards = soup.select("li[data-testid]")

        for card in cards[:50]:
            try:
                link = card.select_one("a[href*='/p/']") or card.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.trulia.com" + href

                title = card.get_text(strip=True)[:100]

                price = None
                price_match = re.search(r"\$[\d,]+", card.get_text())
                if price_match:
                    try:
                        price = float(price_match.group().replace("$", "").replace(",", ""))
                    except ValueError:
                        pass

                beds = None
                beds_match = re.search(r"(\d+)\s*bd", card.get_text(), re.I)
                if beds_match:
                    beds = int(beds_match.group(1))

                baths = None
                baths_match = re.search(r"(\d+(?:\.\d+)?)\s*ba", card.get_text(), re.I)
                if baths_match:
                    baths = float(baths_match.group(1))

                listings.append({
                    "title": title,
                    "address": "",
                    "price": price,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "description": title,
                    "url": href,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Trulia] Error parsing card: {e}")

        return listings
