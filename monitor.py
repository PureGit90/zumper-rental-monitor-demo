"""
Core monitor logic: fetch listings from a Zumper search URL, dedupe against
what's already been seen, and append only the new rows to a CSV.

Built mock-first: _mock_listings() returns realistic Zumper-style listing
data with zero network calls or credentials, so the whole pipeline
(fetch -> dedupe -> CSV export) is fully explorable and testable with no
setup. fetch_live_listings() is a real best-effort scraper for when someone
wants to point it at a live search URL; it's wrapped so a live-site or
JS-rendering failure never crashes the run, it just falls back to a clear
error the caller can surface.

Run standalone: `python monitor.py` runs one scan against settings.SEARCH_URL
using sample data and prints what it would write to CSV.
"""

import csv
import hashlib
import json
import os
import random
from datetime import datetime, timedelta

import settings

# ---------------------------------------------------------------------------
# Mock data (built first, per project convention -- every demo needs a
# realistic offline fallback before any live-fetch code is written)
# ---------------------------------------------------------------------------

_MOCK_STREETS = [
    "Bergen St", "Dean St", "Nostrand Ave", "Franklin Ave", "Union St",
    "Prospect Pl", "Sterling Pl", "Lincoln Rd", "Ocean Ave", "Flatbush Ave",
    "Vanderbilt Ave", "Washington Ave", "Classon Ave", "St Johns Pl",
]

_MOCK_AMENITY_SETS = [
    "In-unit laundry, dishwasher, hardwood floors",
    "Doorman, elevator, gym, roof deck",
    "Pet friendly, private outdoor space",
    "Central air, stainless steel appliances",
    "Laundry in building, bike storage",
    "Renovated kitchen, walk-in closet",
]

_MOCK_TITLE_ADJECTIVES = [
    "Sunny", "Renovated", "Spacious", "Bright", "Charming", "Newly listed",
    "Cozy", "Modern", "Updated", "Top-floor",
]

_MOCK_TITLE_FEATURES = [
    "with private balcony", "near the park", "in elevator building",
    "with in-unit laundry", "prewar details", "with private outdoor space",
    "great natural light", "close to transit",
]


def _extract_city_label(search_url: str) -> str:
    """Best-effort human-readable city label pulled from the search URL path,
    used only to make mock listing addresses match whatever URL was pasted
    in. Falls back to a sane default if the URL doesn't match the expected
    Zumper path shape."""
    try:
        path = search_url.split("apartments-for-rent/")[1].split("?")[0]
        slug = path.split("/")[0]
        parts = slug.split("-")
        if len(parts) >= 2:
            city = " ".join(p.capitalize() for p in parts[:-1])
            state = parts[-1].upper()
            return f"{city}, {state}"
    except (IndexError, AttributeError):
        pass
    return "Brooklyn, NY"


def _listing_id(address: str, listing_url: str) -> str:
    """Stable dedupe key. Prefers the listing URL (Zumper IDs live there);
    falls back to a hash of the address if a URL is ever missing."""
    basis = listing_url or address
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _mock_listings(search_url: str, count: int = None, seed_offset: int = 0) -> list:
    """Returns realistic-looking Zumper rental listings with zero network
    calls. This is the default data source for the demo -- no API key, no
    scraping, no setup required."""
    rng = random.Random(hash(search_url) + seed_offset)
    city_label = _extract_city_label(search_url)
    n = count if count is not None else rng.randint(3, 7)

    listings = []
    for i in range(n):
        street_num = rng.randint(100, 899)
        street = rng.choice(_MOCK_STREETS)
        unit = rng.choice(["", f" #{rng.randint(1, 6)}{rng.choice('ABCDEF')}"])
        address = f"{street_num} {street}{unit}, {city_label}"
        beds = rng.choice([0, 1, 1, 2, 2, 3])
        baths = 1 if beds <= 1 else rng.choice([1, 1, 2])
        beds_label = "Studio" if beds == 0 else str(beds)
        sqft = rng.randint(400, 650) if beds == 0 else rng.randint(550 + beds * 150, 750 + beds * 250)
        price = rng.randint(1800, 2600) if beds == 0 else rng.randint(2000 + beds * 700, 2900 + beds * 900)
        listing_id = rng.randint(10_000_000, 99_999_999)
        listing_url = f"https://www.zumper.com/apartment-for-rent/{listing_id}"
        bed_phrase = "Studio" if beds == 0 else f"{beds}BR"
        title = f"{rng.choice(_MOCK_TITLE_ADJECTIVES)} {bed_phrase} {rng.choice(_MOCK_TITLE_FEATURES)}"
        listings.append({
            "title": title,
            "price": price,
            "beds": beds_label,
            "baths": str(baths),
            "sqft": sqft,
            "address": address,
            "listing_url": listing_url,
            "amenities": rng.choice(_MOCK_AMENITY_SETS),
        })
    return listings


# ---------------------------------------------------------------------------
# Live fetch (best-effort, falls back to mock on any failure)
# ---------------------------------------------------------------------------

def fetch_live_listings(search_url: str) -> list:
    """Attempts a live fetch of a Zumper search results page. Zumper renders
    listings client-side via JavaScript, so a plain HTTP GET typically won't
    see listing data in the raw HTML -- production deployment would swap
    this for a headless-browser fetch (Playwright) or Zumper's internal JSON
    endpoint. Raises on any failure so the caller can fall back to mock data
    instead of crashing the monitor run.
    """
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(search_url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    cards = soup.select("[data-testid='listing-card']")
    if not cards:
        raise RuntimeError(
            "No listing cards found in raw HTML -- Zumper renders results "
            "client-side via JavaScript, so this page needs a headless "
            "browser (Playwright) to see live data. Falling back to sample "
            "data for this demo."
        )

    listings = []
    for card in cards:
        title_el = card.select_one("[data-testid='listing-title']")
        price_el = card.select_one("[data-testid='listing-price']")
        address_el = card.select_one("[data-testid='listing-address']")
        link_el = card.select_one("a[href]")
        listings.append({
            "title": title_el.get_text(strip=True) if title_el else "",
            "price": price_el.get_text(strip=True) if price_el else "",
            "beds": "",
            "baths": "",
            "sqft": "",
            "address": address_el.get_text(strip=True) if address_el else "",
            "listing_url": link_el["href"] if link_el else "",
            "amenities": "",
        })
    return listings


def fetch_listings(search_url: str, use_live: bool = False, seed_offset: int = 0) -> tuple:
    """Fetches listings, live if requested and reachable, otherwise sample
    data. Returns (listings, used_live: bool, note: str)."""
    if use_live:
        try:
            return fetch_live_listings(search_url), True, "Live fetch succeeded."
        except Exception as exc:
            return (
                _mock_listings(search_url, seed_offset=seed_offset),
                False,
                f"Live fetch failed ({exc}). Showing sample data instead.",
            )
    return _mock_listings(search_url, seed_offset=seed_offset), False, "Sample data mode."


# ---------------------------------------------------------------------------
# Dedupe + CSV output
# ---------------------------------------------------------------------------

def load_seen_ids(path: str = None) -> set:
    path = path or settings.SEEN_IDS_PATH
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(seen_ids: set, path: str = None):
    path = path or settings.SEEN_IDS_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(sorted(seen_ids), f, indent=2)


def dedupe(listings: list, seen_ids: set) -> tuple:
    """Splits listings into (new_rows, already_seen_count). Each new row
    gets a first_seen timestamp and its dedupe id gets added to seen_ids
    in place."""
    new_rows = []
    already_seen = 0
    now = datetime.now().isoformat(timespec="seconds")
    for listing in listings:
        lid = _listing_id(listing["address"], listing["listing_url"])
        if lid in seen_ids:
            already_seen += 1
            continue
        seen_ids.add(lid)
        row = dict(listing)
        row["first_seen"] = now
        new_rows.append(row)
    return new_rows, already_seen


def append_to_csv(rows: list, csv_path: str = None):
    """Appends new rows to the output CSV, writing a header only if the file
    doesn't exist yet. Never rewrites or duplicates existing rows."""
    csv_path = csv_path or settings.OUTPUT_CSV_PATH
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=settings.CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in settings.CSV_COLUMNS})


def run_scan(search_url: str = None, use_live: bool = False, seed_offset: int = 0,
             seen_ids: set = None, write_csv: bool = False, csv_path: str = None) -> dict:
    """Runs one monitor tick: fetch -> dedupe -> (optionally) write CSV.
    Returns a summary dict so callers (CLI or Streamlit) can report results.
    `seen_ids` can be passed in and is mutated in place, so a caller running
    repeated scans in one session (like the Streamlit app) can build up
    dedupe state across runs without touching disk.
    """
    search_url = search_url or settings.SEARCH_URL
    seen_ids = seen_ids if seen_ids is not None else load_seen_ids()

    listings, used_live, note = fetch_listings(search_url, use_live=use_live, seed_offset=seed_offset)
    new_rows, already_seen = dedupe(listings, seen_ids)

    if write_csv:
        append_to_csv(new_rows, csv_path)
        save_seen_ids(seen_ids)

    return {
        "fetched": len(listings),
        "new": len(new_rows),
        "already_seen": already_seen,
        "used_live": used_live,
        "note": note,
        "new_rows": new_rows,
        "seen_ids": seen_ids,
    }


if __name__ == "__main__":
    result = run_scan(write_csv=True)
    print(f"Scanned {settings.SEARCH_URL}")
    print(f"Note: {result['note']}")
    print(f"Fetched {result['fetched']} listings -- {result['new']} new, "
          f"{result['already_seen']} already seen.")
    if result["new_rows"]:
        print(f"Wrote {result['new']} new rows to {settings.OUTPUT_CSV_PATH}")
