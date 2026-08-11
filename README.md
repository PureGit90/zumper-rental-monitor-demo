# Zumper Rental Listings Monitor — Working Demo

## What This Does
Point it at any Zumper search URL (city, price, beds, whatever filters are already
in the URL) and it pulls current listings, throws out anything already seen, and
appends only the new rows to a deduplicated CSV -- Title, Price, Beds/Baths, Sqft,
Full Address, Listing URL, Amenities, plus a first-seen timestamp. Built to run on
a schedule (every 3-15 minutes) so new listings get caught close to the moment
they're posted.

## How It Works
Schedule tick → Zumper search URL (from `settings.py`) → fetch listings + build
dedupe key + check against seen IDs → append only new rows to CSV → log fetched
/ new / already-seen counts. Full breakdown and a diagram in `workflow.md`.

## Quick Start

**Command line:**
```bash
pip install -r requirements.txt
python monitor.py
```
Runs one scan against the sample search URL in `settings.py` using realistic mock
listing data, and writes new rows to `output/new_listings.csv`.

**Streamlit demo (interactive):**
```bash
pip install -r requirements.txt
streamlit run app.py
```
Click **Run scan now** to simulate a scheduled tick. Sample data mode is on by
default, so the full fetch → dedupe → CSV loop is explorable with zero setup --
run it a few times in a row and watch the "already seen" count climb as the
monitor recognizes listings it already tracked, exactly like it would across
real scheduled runs.

## Configuration
- `settings.SEARCH_URL` -- any Zumper search URL, filters included. See
  `sample_data/example_search_urls.txt` for a few examples across different
  cities/price ranges.
- `settings.POLL_INTERVAL_MINUTES` -- how often the scheduled version should run
  (client's post asked for 3-15 minutes; default is 5).
- `settings.OUTPUT_CSV_PATH` / `settings.SEEN_IDS_PATH` -- where results and the
  dedupe state get written.
- No API keys or credentials needed to run the demo.

## Demo Limitations
- This is an MVP demo built against sample data before applying -- Zumper renders
  its search results with JavaScript, so a plain HTTP request (what
  `fetch_live_listings()` in `monitor.py` attempts) usually can't see listing data
  in the raw page. Production version swaps that one function for a
  headless-browser fetch (Playwright) or Zumper's internal JSON endpoint; the
  dedupe and CSV export logic underneath doesn't change at all.
- The Streamlit app simulates the schedule by generating a new "batch" of sample
  listings each time you click **Run scan now**, instead of running on an actual
  timer -- the real script (`monitor.py`) is meant to run under cron or a simple
  sleep loop, not inside a UI.
- Dedupe here is exact-match on listing URL (falls back to address). That's the
  right approach for Zumper since every listing has a unique URL.
