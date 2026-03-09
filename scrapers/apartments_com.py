"""Apartments.com scraper."""

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


class ApartmentsComScraper(BaseScraper):
    SOURCE_NAME = "Apartments.com"

    def scrape(self, city, max_rent, min_beds, min_baths):
        slug = CITY_SLUGS.get(city, city.lower().replace(" ", "-") + "-ca")
        url = f"https://www.apartments.com/{slug}/"

        # Build filter params
        bed_filter = f"{int(min_beds)}-bedrooms" if min_beds and int(min_beds) > 0 else ""
        if bed_filter:
            url = f"https://www.apartments.com/{slug}/{bed_filter}/"

        params = {}
        if max_rent:
            params["px"] = int(max_rent)

        headers = self._get_headers()
        listings = []

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Apartments.com] Request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        cards = soup.select("li.mortar-wrapper") or soup.select("article.placard")
        if not cards:
            cards = soup.select("[data-listingid]")

        for card in cards[:50]:
            try:
                link = card.select_one("a.property-link") or card.select_one("a")
                if not link:
                    continue

                listing_url = link.get("href", "")
                title_el = card.select_one(".property-title") or card.select_one("span.js-placardTitle")
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)

                address_el = card.select_one(".property-address")
                address = address_el.get_text(strip=True) if address_el else ""

                price_el = card.select_one(".property-pricing") or card.select_one(".price-range")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = self._parse_price(price_text)

                beds_el = card.select_one(".property-beds") or card.select_one(".bed-range")
                beds_text = beds_el.get_text(strip=True) if beds_el else ""
                beds = self._parse_beds(beds_text)

                baths = None
                baths_text = beds_text
                baths_match = re.search(r"(\d+(?:\.\d+)?)\s*ba", baths_text, re.I)
                if baths_match:
                    baths = float(baths_match.group(1))

                img = card.select_one("img")
                photo = img.get("src", "") or img.get("data-src", "") if img else ""

                listings.append({
                    "title": title,
                    "address": address or title,
                    "price": price,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "description": f"{title} - {address} - {price_text} - {beds_text}",
                    "url": listing_url,
                    "photo_urls": [photo] if photo else [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Apartments.com] Error parsing card: {e}")
                continue

        return listings

    def _parse_price(self, text):
        if not text:
            return None
        matches = re.findall(r"[\d,]+", text.replace(",", ""))
        if matches:
            try:
                prices = [float(m.replace(",", "")) for m in matches]
                return min(p for p in prices if p > 100)
            except (ValueError, TypeError):
                pass
        return None

    def _parse_beds(self, text):
        if not text:
            return None
        m = re.search(r"(\d+)\s*(?:bed|br|bd)", text, re.I)
        if m:
            return int(m.group(1))
        if "studio" in text.lower():
            return 0
        return None
