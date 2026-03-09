"""Deduplication logic using fuzzy matching and SQLite history."""

import hashlib
import logging
import sqlite3
from pathlib import Path

from rapidfuzz import fuzz

from config import DB_PATH

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 85  # Similarity score above which two addresses are considered the same


def init_db():
    """Initialize SQLite database for listing history."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_listings (
            listing_id TEXT PRIMARY KEY,
            address TEXT,
            source TEXT,
            price REAL,
            first_seen TEXT DEFAULT (datetime('now')),
            last_seen TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def generate_listing_id(listing):
    """Generate a unique ID for a listing based on source + URL or address."""
    key = listing.get("url", "") or listing.get("address", "")
    source = listing.get("source", "")
    raw = f"{source}:{key}"
    return hashlib.md5(raw.encode()).hexdigest()


def deduplicate(listings):
    """Remove duplicate listings across platforms.

    1. Fuzzy-match addresses to find cross-platform duplicates
    2. Check against seen_listings table for previously processed listings
    3. Return only new, unique listings
    """
    if not listings:
        return []

    conn = init_db()
    total_input = len(listings)

    # Step 1: Cross-platform dedup via fuzzy address matching
    unique = []
    seen_addresses = []

    for listing in listings:
        listing["listing_id"] = generate_listing_id(listing)

        address = (listing.get("address") or "").strip().lower()
        if not address:
            # If no address, keep it (can't dedup without address)
            unique.append(listing)
            continue

        is_dup = False
        for seen_addr in seen_addresses:
            score = fuzz.token_sort_ratio(address, seen_addr)
            if score >= FUZZY_THRESHOLD:
                is_dup = True
                break

        if not is_dup:
            unique.append(listing)
            seen_addresses.append(address)

    cross_platform_dupes = total_input - len(unique)
    logger.info(f"[Dedup] Removed {cross_platform_dupes} cross-platform duplicates")

    # Step 2: Check against historical seen_listings
    new_listings = []
    for listing in unique:
        cursor = conn.execute(
            "SELECT listing_id FROM seen_listings WHERE listing_id = ?",
            (listing["listing_id"],)
        )
        if cursor.fetchone():
            # Already seen - update last_seen
            conn.execute(
                "UPDATE seen_listings SET last_seen = datetime('now') WHERE listing_id = ?",
                (listing["listing_id"],)
            )
        else:
            new_listings.append(listing)
            # Insert into seen_listings
            conn.execute(
                "INSERT INTO seen_listings (listing_id, address, source, price) VALUES (?, ?, ?, ?)",
                (listing["listing_id"], listing.get("address", ""),
                 listing.get("source", ""), listing.get("price"))
            )

    conn.commit()
    historical_dupes = len(unique) - len(new_listings)
    logger.info(f"[Dedup] Removed {historical_dupes} previously seen listings")
    logger.info(f"[Dedup] {len(new_listings)} new unique listings to process")

    # Log source breakdown
    source_counts = {}
    for l in new_listings:
        src = l.get("source", "Unknown")
        source_counts[src] = source_counts.get(src, 0) + 1
    for src, count in sorted(source_counts.items()):
        logger.info(f"[Dedup]   {src}: {count} listings")

    conn.close()
    return new_listings
