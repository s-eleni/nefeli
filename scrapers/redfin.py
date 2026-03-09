"""Redfin Rentals scraper."""

import json
import logging
import re
import requests

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_PARAMS = {
    "San Francisco": {"region_id": 17151, "region_type": 6, "slug": "city/17151/CA/San-Francisco"},
    "New York": {"region_id": 30749, "region_type": 6, "slug": "city/30749/NY/New-York"},
}


class RedfinScraper(BaseScraper):
    SOURCE_NAME = "Redfin"

    def scrape(self, city, max_rent, min_beds, min_baths):
        city_info = CITY_PARAMS.get(city)
        if not city_info:
            logger.warning(f"[Redfin] No config for city: {city}")
            return []

        # Use Redfin's stingray API endpoint
        url = "https://www.redfin.com/stingray/api/gis"
        params = {
            "al": 3,
            "has_deal": "false",
            "has_dishwasher": "false",
            "has_laundry_facility": "false",
            "has_laundry_hookups": "false",
            "has_parking": "false",
            "has_pool": "false",
            "has_short_term_lease": "false",
            "include_pending_homes": "false",
            "isRentals": "true",
            "max_price": int(max_rent) if max_rent else "",
            "min_beds": int(min_beds) if min_beds else "",
            "min_baths": int(min_baths) if min_baths else "",
            "num_homes": 50,
            "ord": "redfin-recommended-asc",
            "page_number": 1,
            "region_id": city_info["region_id"],
            "region_type": city_info["region_type"],
            "sf": "1,2,3,4,5,6,7",
            "status": 1,
            "uipt": "1,2,3,4,5,6,7,8",
            "v": 8,
        }
        params = {k: v for k, v in params.items() if v != ""}

        headers = self._get_headers()
        headers["Referer"] = "https://www.redfin.com/"

        listings = []

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            # Redfin prefixes response with {}&&
            text = resp.text
            if text.startswith("{}&&"):
                text = text[4:]
            data = json.loads(text)
        except Exception as e:
            logger.error(f"[Redfin] API request failed: {e}")
            return self._scrape_html(city, city_info, max_rent, min_beds, min_baths)

        homes = data.get("payload", {}).get("homes", [])
        for home in homes[:50]:
            try:
                price_info = home.get("priceInfo", {})
                price = price_info.get("amount")

                address_info = home.get("addressInfo", {})
                address = address_info.get("formattedAddress", "")

                beds = home.get("beds")
                baths = home.get("baths")

                listing_url = "https://www.redfin.com" + home.get("url", "")

                photos = []
                if home.get("photos"):
                    for p in home["photos"][:5]:
                        if isinstance(p, dict) and p.get("photoUrls"):
                            photos.append(p["photoUrls"].get("fullUri", ""))

                listings.append({
                    "title": address,
                    "address": address,
                    "price": price,
                    "bedrooms": beds,
                    "bathrooms": baths,
                    "description": f"{address} - {beds}BR/{baths}BA - ${price}",
                    "url": listing_url,
                    "photo_urls": photos,
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Redfin] Error parsing home: {e}")

        return listings

    def _scrape_html(self, city, city_info, max_rent, min_beds, min_baths):
        """Fallback HTML scraping if API doesn't work."""
        slug = city_info.get("slug", "")
        url = f"https://www.redfin.com/{slug}/apartments-for-rent"

        listings = []
        try:
            from bs4 import BeautifulSoup
            resp = requests.get(url, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            cards = soup.select(".HomeCard") or soup.select("[data-rf-test-id='mapHomeCard']")
            for card in cards[:50]:
                link = card.select_one("a")
                if not link:
                    continue
                href = link.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.redfin.com" + href

                price_el = card.select_one("[class*='price']") or card.select_one(".homecardV2Price")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = None
                m = re.search(r"[\d,]+", price_text.replace(",", ""))
                if m:
                    try:
                        price = float(m.group().replace(",", ""))
                    except ValueError:
                        pass

                title = link.get_text(strip=True)[:100]

                listings.append({
                    "title": title,
                    "address": title,
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
            logger.error(f"[Redfin] HTML scrape also failed: {e}")

        return listings
