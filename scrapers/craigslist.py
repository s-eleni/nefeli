"""Craigslist SF housing/apts scraper."""

import logging
import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

CITY_SUBDOMAINS = {
    "San Francisco": "sfbay",
    "New York": "newyork",
    "Los Angeles": "losangeles",
    "Chicago": "chicago",
    "Seattle": "seattle",
}

CITY_AREAS = {
    "San Francisco": "sfc",
}


class CraigslistScraper(BaseScraper):
    SOURCE_NAME = "Craigslist"

    def scrape(self, city, max_rent, min_beds, min_baths):
        subdomain = CITY_SUBDOMAINS.get(city, "sfbay")
        area = CITY_AREAS.get(city, "")
        area_path = f"/{area}" if area else ""

        listings = []
        base_url = f"https://{subdomain}.craigslist.org"
        search_url = f"{base_url}/search{area_path}/apa"

        params = {
            "max_price": int(max_rent),
            "min_bedrooms": int(min_beds),
            "min_bathrooms": int(min_baths),
            "availabilityMode": 0,
            "sale_date": "all+dates",
        }

        try:
            resp = requests.get(search_url, params=params, headers=self._get_headers(), timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"[Craigslist] Search request failed: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        result_rows = soup.select("li.cl-static-search-result")
        if not result_rows:
            result_rows = soup.select("li.result-row")
        if not result_rows:
            result_rows = soup.select(".cl-search-result")

        for row in result_rows[:50]:
            try:
                link = row.select_one("a")
                if not link:
                    continue

                title = link.get_text(strip=True)
                url = link.get("href", "")
                if url and not url.startswith("http"):
                    url = base_url + url

                price_el = row.select_one(".priceinfo") or row.select_one(".result-price")
                price_text = price_el.get_text(strip=True) if price_el else ""
                price = None
                if price_text:
                    price_text = price_text.replace("$", "").replace(",", "")
                    try:
                        price = float(price_text)
                    except ValueError:
                        pass

                listings.append({
                    "title": title,
                    "address": "",
                    "price": price,
                    "bedrooms": None,
                    "bathrooms": None,
                    "description": title,
                    "url": url,
                    "photo_urls": [],
                    "date_posted": None,
                    "source": self.SOURCE_NAME,
                })
            except Exception as e:
                logger.debug(f"[Craigslist] Error parsing row: {e}")
                continue

        # Fetch details for each listing to get address and description
        for listing in listings[:20]:
            if not listing["url"]:
                continue
            self._delay()
            try:
                detail_resp = requests.get(listing["url"], headers=self._get_headers(), timeout=15)
                detail_resp.raise_for_status()
                detail_soup = BeautifulSoup(detail_resp.text, "lxml")

                # Get description
                body = detail_soup.select_one("#postingbody")
                if body:
                    listing["description"] = body.get_text(strip=True)

                # Get address from map
                map_el = detail_soup.select_one("#map")
                if map_el:
                    lat = map_el.get("data-latitude", "")
                    lng = map_el.get("data-longitude", "")
                    if lat and lng:
                        listing["address"] = f"{lat},{lng}"

                address_el = detail_soup.select_one(".mapaddress") or detail_soup.select_one("div.mapbox small")
                if address_el:
                    listing["address"] = address_el.get_text(strip=True)

                # Get housing info (beds/baths)
                attrs = detail_soup.select(".shared-line-bubble .attr")
                for attr in attrs:
                    text = attr.get_text(strip=True).lower()
                    if "br" in text:
                        try:
                            listing["bedrooms"] = int(text.replace("br", "").strip())
                        except ValueError:
                            pass
                    elif "ba" in text:
                        try:
                            listing["bathrooms"] = float(text.replace("ba", "").strip())
                        except ValueError:
                            pass

                # Get photos
                thumbs = detail_soup.select("#thumbs a")
                for thumb in thumbs[:5]:
                    img_url = thumb.get("href", "")
                    if img_url:
                        listing["photo_urls"].append(img_url)

                # Get post date
                time_el = detail_soup.select_one("time.date.timeago")
                if time_el:
                    listing["date_posted"] = time_el.get("datetime", "")

            except Exception as e:
                logger.debug(f"[Craigslist] Error fetching detail: {e}")

        return listings
