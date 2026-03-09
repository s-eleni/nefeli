"""Configuration and environment variable loading."""

import os
import json
from pathlib import Path

# Load .env file if it exists
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

# API Keys
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
SMTP_EMAIL = os.environ.get("SMTP_EMAIL", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
RENTCAST_API_KEY = os.environ.get("RENTCAST_API_KEY", "")

# Flask
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

# Scraper settings
SCRAPER_DELAY_MIN = int(os.environ.get("SCRAPER_DELAY_MIN", "2"))
SCRAPER_DELAY_MAX = int(os.environ.get("SCRAPER_DELAY_MAX", "5"))

# LLM Model
LLM_MODEL = "claude-sonnet-4-20250514"

# Project paths
PROJECT_ROOT = Path(__file__).parent
SHUTTLE_STOPS_PATH = PROJECT_ROOT / "shuttle_stops.json"
DB_PATH = PROJECT_ROOT / "data" / "rental_agent.db"

# Load shuttle stops
def load_shuttle_stops():
    with open(SHUTTLE_STOPS_PATH) as f:
        return json.load(f)

# Neighborhoods by city
NEIGHBORHOODS = {
    "San Francisco": [
        "Noe Valley", "Inner Sunset", "Outer Sunset", "Western Addition",
        "Hayes Valley", "Castro", "Mission", "Dolores Park/Dolores Heights",
        "Bernal Heights", "Glen Park", "Cole Valley", "Haight-Ashbury",
        "Lower Haight", "Pacific Heights", "Cow Hollow", "Marina",
        "Russian Hill", "Nob Hill", "North Beach", "Telegraph Hill",
        "SOMA", "Potrero Hill", "Dogpatch", "Mission Bay", "Excelsior",
        "Bayview", "Visitacion Valley", "Tenderloin", "Civic Center",
        "Financial District", "Inner Richmond", "Outer Richmond",
        "Parkside", "Twin Peaks", "Diamond Heights", "Crocker-Amazon",
    ],
}

# Default red flags checklist
DEFAULT_RED_FLAGS = [
    "Scam likely (too good to be true price, vague details)",
    "No photos or stock photos only",
    "Requests money before viewing",
    "Ground floor / basement unit",
    "No natural light / windowless rooms",
    "Alley-facing or rear entrance",
    "Excessive fees or hidden costs",
    "Very short lease term",
    "No in-unit or in-building laundry",
    "Street noise concerns",
]

# User-agent rotation list
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]
