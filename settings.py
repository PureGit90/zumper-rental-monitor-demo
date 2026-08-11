"""
Settings for the Zumper rental listings monitor.

Edit SEARCH_URL to point at any Zumper search results page (city, price range,
and bed/bath filters are all encoded in the URL itself, so no separate filter
config is needed -- copy the URL straight from your browser's address bar
after setting filters on Zumper.com).
"""

# Any Zumper search URL, filters and all. Example below is Zumper's
# "apartments for rent in Brooklyn, NY" search with a $2,000-$3,500 filter.
SEARCH_URL = "https://www.zumper.com/apartments-for-rent/brooklyn-ny?priceMin=2000&priceMax=3500&bedrooms=1"

# How often the monitor should poll, in minutes. Zumper's own listings update
# continuously, so 3-15 minutes catches new posts fast without hammering the
# site. Client's job post asked for "every 3-15 mins" -- default splits the
# difference.
POLL_INTERVAL_MINUTES = 5

# Where deduplicated results are written. Re-running the script appends only
# new rows -- it never rewrites or duplicates existing ones.
OUTPUT_CSV_PATH = "output/new_listings.csv"

# Local store of listing IDs already seen, so restarts don't re-save old
# listings as "new."
SEEN_IDS_PATH = "output/seen_listing_ids.json"

# Columns written to the output CSV, in order.
CSV_COLUMNS = [
    "first_seen",
    "title",
    "price",
    "beds",
    "baths",
    "sqft",
    "address",
    "listing_url",
    "amenities",
]
