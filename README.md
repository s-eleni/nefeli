# Nefeli — Rental Apartment Monitoring Agent

A full end-to-end rental apartment monitoring agent that helps renters in competitive markets find apartments faster. Built as a Python/Flask web app.

## What It Does

1. **Scrapes listings** from 10+ rental platforms (Zillow, Craigslist, Apartments.com, Redfin, Trulia, Rent.com, Zumper, PadMapper, Hotpads) plus API sources (RentCast, RealtyMole)
2. **Deduplicates** cross-platform listings using fuzzy address matching
3. **Filters** by hard criteria (price, beds, baths, parking, laundry)
4. **Calculates distances** to work shuttle stops via Google Maps API
5. **Analyzes listings with LLM** (Claude) — detects red flags, scores/ranks listings, validates rankings with a judge step
6. **Drafts outreach messages** for the top 5 listings
7. **Sends email alerts** with a formatted HTML report

## Architecture

```
User Form → Scrapers (parallel) → Dedup → Hard Filter → Distance Calc
    → LLM Red Flags → LLM Scoring → LLM Judge → Outreach Draft → Email
```

### Project Structure

```
app.py                  # Flask entry point + pipeline orchestration
config.py               # Environment variables, neighborhoods, defaults
scrapers/               # One file per data source
  base_scraper.py       # Abstract base class
  craigslist.py         # Craigslist SF housing
  zillow.py             # Zillow Rentals
  apartments_com.py     # Apartments.com
  hotpads.py            # Hotpads
  redfin.py             # Redfin Rentals
  trulia.py             # Trulia Rentals
  rent_com.py           # Rent.com
  zumper.py             # Zumper
  padmapper.py          # PadMapper
  api_sources.py        # RentCast + RealtyMole APIs
pipeline/               # Processing pipeline modules
  dedup.py              # Fuzzy deduplication + SQLite history
  filters.py            # Hard filters (price, beds, parking, etc.)
  distance.py           # Google Maps distance to shuttle stops
  llm_analysis.py       # Red flags + scoring + judge validation
  outreach.py           # LLM outreach message drafting
  email_sender.py       # HTML email assembly + SMTP sending
templates/              # Jinja2 HTML templates
  index.html            # Preferences form
  results.html          # Results display
static/
  style.css             # Styles
shuttle_stops.json      # Shuttle stop locations (do not modify)
```

## Setup

### 1. Clone and install

```bash
git clone https://github.com/s-eleni/nefeli.git
cd nefeli
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for LLM analysis |
| `GOOGLE_MAPS_API_KEY` | Yes | Google Maps for distance calculation |
| `SMTP_EMAIL` | No | Gmail address for sending alerts |
| `SMTP_PASSWORD` | No | Gmail app password (not your regular password) |
| `RENTCAST_API_KEY` | No | RentCast API key ([sign up](https://www.rentcast.io/api)) |

**Gmail App Password:** Go to [Google Account Security](https://myaccount.google.com/security) → 2-Step Verification → App passwords → Generate a password for "Mail".

**RentCast API:** Sign up at https://www.rentcast.io/api — free tier allows 50 requests/month.

### 3. Run locally

```bash
python app.py
```

Open http://localhost:5000 in your browser.

## Deploy to Render (Recommended)

This is the easiest free deployment option:

1. Push this repo to GitHub (it's already at `s-eleni/nefeli`)
2. Go to [render.com](https://render.com) and sign up / log in
3. Click **New** → **Web Service**
4. Connect your GitHub account and select the `s-eleni/nefeli` repo
5. Render will auto-detect `render.yaml`. Settings:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300 --workers 2`
6. Add environment variables in the Render dashboard:
   - `ANTHROPIC_API_KEY`
   - `GOOGLE_MAPS_API_KEY`
   - `SMTP_EMAIL` and `SMTP_PASSWORD` (optional)
   - `RENTCAST_API_KEY` (optional)
7. Click **Create Web Service** — it will deploy automatically

Your app will be live at `https://nefeli-XXXX.onrender.com`.

## Deploy to Railway (Alternative)

1. Go to [railway.app](https://railway.app)
2. New Project → Deploy from GitHub Repo → select `s-eleni/nefeli`
3. Add environment variables in Settings
4. Railway auto-detects the `Procfile`

## Deploy to Fly.io (Alternative)

```bash
fly launch --name nefeli
fly secrets set ANTHROPIC_API_KEY=your_key GOOGLE_MAPS_API_KEY=your_key
fly deploy
```

## Run in Google Colab

If cloud deployment isn't viable, you can run the app in Colab with a public URL:

1. Open a new Colab notebook
2. Run these cells in order:

```python
# Cell 1: Install dependencies
!pip install flask requests beautifulsoup4 lxml anthropic googlemaps rapidfuzz pyngrok gunicorn

# Cell 2: Clone the repo
!git clone https://github.com/s-eleni/nefeli.git
%cd nefeli

# Cell 3: Set environment variables
import os
os.environ['ANTHROPIC_API_KEY'] = 'your_key_here'
os.environ['GOOGLE_MAPS_API_KEY'] = 'your_key_here'
# os.environ['SMTP_EMAIL'] = 'your_email'
# os.environ['SMTP_PASSWORD'] = 'your_app_password'

# Cell 4: Run with pyngrok
from pyngrok import ngrok
import threading

# Set your ngrok auth token (sign up at ngrok.com for free)
ngrok.set_auth_token("your_ngrok_token")

# Start Flask in a background thread
from app import app
threading.Thread(target=lambda: app.run(port=5000)).start()

# Create public URL
public_url = ngrok.connect(5000)
print(f"Public URL: {public_url}")
```

## How the Pipeline Works

1. **Form submission** triggers `/run` endpoint
2. **Scrapers run in parallel** (ThreadPoolExecutor) across all 10+ sources
3. **Deduplication** uses `rapidfuzz` for fuzzy address matching + SQLite for historical tracking
4. **Hard filters** remove listings that don't meet price/beds/baths/parking/laundry criteria
5. **Google Maps API** calculates walking distance to all 8 shuttle stops
6. **LLM Call 1** (per listing, parallel): Red flag detection
7. **LLM Call 2** (per listing, parallel): Scoring against user preferences
8. **LLM Call 3** (single call): Judge validates the full ranking
9. **LLM Call 4** (top 5, parallel): Draft personalized outreach messages
10. **Email** sends HTML report via Gmail SMTP (or saves locally)

## Notes

- All scrapers attempt real connections. If a site blocks or fails, it's logged and skipped gracefully.
- The pipeline timeout on Render is set to 300s (5 min) to allow for LLM processing.
- SQLite database is created at `data/rental_agent.db` on first run.
- The `shuttle_stops.json` file contains 8 work shuttle stops in San Francisco.
