"""Rent.com scraper."""

import logging
import re
import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_SLUGS = {
    "San Francisco": "california/san-francisco",
    "New York": "new-york/new-york",
    "Los Angeles": "california/los-angeles",
}


class RentComScraper(BaseScraper):
    SOURCE_NAME = "Rent.com"

    def scrape(self, city, max_rent, min_beds, min_baths):
        slug = CITY_SLUGS.get(city, "california/" + city.lower().replace(" ", "-"))
        url = f"https://www.rent.com/{slug}/apartments_condos_background"

        params = {}
        if max_rent:
            params["max_price"] = int(max_rent)
        if min_beds:
            params["beds_range"] = f"{int(min_beds)}"

        listings = []

        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Rent.com] Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        cards = soup.select("[data-tag_section='card']") or soup.select(".placard")
        if not cards:
            cards = soup.select("article") or soup.select("[class*='ListingCard']")

        for card in cards[:50]:
            try:
                link = card.select_one("a")
                if not link:
                    continue

                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.rent.com" + href

                title_el = card.select_one("[class*='title']") or card.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)[:100]

                address_el = card.select_one("[class*='address']")
                address = address_el.get_text(strip=True) if address_el else ""

                price = None
                price_el = card.select_one("[class*='price']") or card.select_one("[class*='Price']")
                if price_el:
                    m = re.search(r"[\d,]+", price_el.get_text().replace(",", ""))
                    if m:
                        try:
                            price = float(m.group())
                        except ValueError:
                            pass

                listings.append({
                    "title": title,
                    "address": address or title,
                    "price": price,
                    "bedrooms": None,
                    "bathrooms": None,
                    "description": f"{title} - {address}",
                    "url": href,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Rent.com] Error parsing card: {e}")

        return listings
