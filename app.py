import io
from datetime import datetime

import pandas as pd
import streamlit as st

import settings
from monitor import run_scan

st.set_page_config(page_title="Zumper Rental Listings Monitor", page_icon="🏠", layout="wide")


def _init_state():
    if "seen_ids" not in st.session_state:
        st.session_state.seen_ids = set()
    if "all_rows" not in st.session_state:
        st.session_state.all_rows = []
    if "scan_log" not in st.session_state:
        st.session_state.scan_log = []
    if "scan_count" not in st.session_state:
        st.session_state.scan_count = 0


def main():
    _init_state()

    st.title("🏠 Zumper Rental Listings Monitor")
    st.caption(
        "Point it at any Zumper search URL. Every scan pulls current listings, "
        "throws out anything already seen, and appends only new ones to a CSV -- "
        "the exact loop a scheduled job would run every few minutes."
    )

    with st.sidebar:
        st.header("Monitor Settings")
        search_url = st.text_input("Zumper search URL", value=settings.SEARCH_URL)
        poll_minutes = st.slider(
            "Poll interval (minutes)", min_value=3, max_value=15,
            value=settings.POLL_INTERVAL_MINUTES,
        )
        use_live = st.checkbox(
            "Attempt live fetch (falls back to sample data)",
            value=False,
            help=(
                "Zumper renders results with JavaScript, so a plain HTTP request "
                "usually can't see listing data -- this will attempt it and fall "
                "back to sample data automatically if it can't. Production "
                "deployment would run this through a headless browser instead."
            ),
        )
        st.divider()
        st.caption(
            "Sample mode is on by default so the full fetch -> dedupe -> CSV "
            "loop is explorable with zero setup. Each 'Run scan' click "
            "simulates one scheduled tick -- new listings show up over "
            "repeated scans just like a real cron job would catch them."
        )
        if st.button("🔄 Reset session (clear seen listings)"):
            st.session_state.seen_ids = set()
            st.session_state.all_rows = []
            st.session_state.scan_log = []
            st.session_state.scan_count = 0
            st.rerun()

    run_clicked = st.button("▶️ Run scan now", type="primary")

    if run_clicked:
        result = run_scan(
            search_url=search_url,
            use_live=use_live,
            seed_offset=st.session_state.scan_count,
            seen_ids=st.session_state.seen_ids,
            write_csv=False,
        )
        st.session_state.scan_count += 1
        st.session_state.all_rows.extend(result["new_rows"])
        st.session_state.scan_log.append({
            "scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "fetched": result["fetched"],
            "new": result["new"],
            "already_seen": result["already_seen"],
            "source": "live" if result["used_live"] else "sample data",
        })
        if not result["used_live"] and use_live:
            st.warning(result["note"])
        elif result["used_live"]:
            st.success(result["note"])

    st.divider()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Scans run this session", st.session_state.scan_count)
    c2.metric("Total unique listings tracked", len(st.session_state.all_rows))
    latest = st.session_state.scan_log[-1] if st.session_state.scan_log else None
    c3.metric("New on last scan", latest["new"] if latest else "—")
    c4.metric("Already seen on last scan", latest["already_seen"] if latest else "—")

    st.divider()

    if not st.session_state.all_rows:
        st.info(
            "Click **Run scan now** to pull listings from the search URL above. "
            "Sample mode generates realistic Zumper-style listings so you can see "
            "the full dedupe + CSV export loop without any live scraping."
        )
    else:
        tab1, tab2, tab3 = st.tabs(
            ["📋 All tracked listings (CSV export)", "🆕 Newest scan", "📜 Scan history"]
        )

        df = pd.DataFrame(st.session_state.all_rows, columns=settings.CSV_COLUMNS)

        with tab1:
            st.write(
                f"**{len(df)} unique listings** tracked so far this session -- "
                "this is exactly what gets appended to `output/new_listings.csv` "
                "on a real run, no duplicate rows ever."
            )
            st.dataframe(df, use_container_width=True)
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download new_listings.csv",
                csv_bytes,
                "new_listings.csv",
                "text/csv",
            )

        with tab2:
            if latest and latest["new"] > 0:
                newest_df = df.tail(latest["new"])
                st.write(f"**{latest['new']} new listings** found on the most recent scan:")
                st.dataframe(newest_df, use_container_width=True)
            else:
                st.write("No new listings on the most recent scan -- everything fetched was already seen.")

        with tab3:
            log_df = pd.DataFrame(st.session_state.scan_log)
            st.write(
                f"Each row simulates one scheduled tick (every {poll_minutes} minutes in production):"
            )
            st.dataframe(log_df, use_container_width=True)

    st.divider()
    st.caption(
        "This is an MVP demo -- sample data stands in for a live Zumper fetch, and "
        "the schedule is simulated by clicking 'Run scan now' instead of running on "
        "an actual timer. Production version: `monitor.py` runs on a real cron "
        "schedule via `settings.POLL_INTERVAL_MINUTES`, live fetch goes through a "
        "headless browser to handle Zumper's JavaScript rendering, and results "
        "append to a persistent CSV on disk (or wherever you want them, "
        "Google Sheets/Airtable/email digest are quick additions)."
    )


if __name__ == "__main__":
    main()
