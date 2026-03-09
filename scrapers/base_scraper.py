"""Abstract base class for all rental listing scrapers."""

import logging
import random
import time
from abc import ABC, abstractmethod

from config import USER_AGENTS, SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class that all scrapers inherit from."""

    SOURCE_NAME = "Unknown"

    def __init__(self):
        self.session = None

    def _get_headers(self):
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    def _delay(self):
        delay = random.uniform(SCRAPER_DELAY_MIN, SCRAPER_DELAY_MAX)
        logger.debug(f"[{self.SOURCE_NAME}] Waiting {delay:.1f}s between requests")
        time.sleep(delay)

    @abstractmethod
    def scrape(self, city, max_rent, min_beds, min_baths):
        """Scrape listings from this source.

        Args:
            city: City name (e.g. "San Francisco")
            max_rent: Maximum monthly rent
            min_beds: Minimum number of bedrooms
            min_baths: Minimum number of bathrooms

        Returns:
            List of dicts with keys: title, address, price, bedrooms, bathrooms,
            description, url, photo_urls, date_posted, source
        """
        pass

    def safe_scrape(self, city, max_rent, min_beds, min_baths):
        """Wrapper that catches exceptions so one scraper can't crash the pipeline."""
        try:
            logger.info(f"[{self.SOURCE_NAME}] Starting scrape for {city}...")
            listings = self.scrape(city, max_rent, min_beds, min_baths)
            logger.info(f"[{self.SOURCE_NAME}] Found {len(listings)} listings")
            return listings
        except Exception as e:
            logger.error(f"[{self.SOURCE_NAME}] Scrape failed: {e}")
            return []
