import re
import requests
import feedparser
from app.database import supabase_client
from app.services.sec_service import SECService
from app.services.xbrl_service import XBRLService


class SECListenerService:
    @staticmethod
    def check_live_filings():
        print("Polling live SEC EDGAR RSS Feed...")

        # Live SEC feed for all latest filings
        sec_rss_url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            "?action=getcurrent&type=&company=&dateb=&owner=include&start=0&count=40&output=atom"
        )

        # SEC requires a descriptive User-Agent or they block the request
        headers = {
            "User-Agent": "SocratesAI Research Engine amartya@lpu.in",
        }

        try:
            response = requests.get(sec_rss_url, headers=headers, timeout=15)
            if response.status_code != 200:
                print(f"SEC RSS Feed returned status code: {response.status_code}")
                return

            feed = feedparser.parse(response.content)

            # 1. Pull the active tickers from watchlist
            watch_res = (
                supabase_client.table("soc_watchlist")
                .select("ticker")
                .eq("is_active", True)
                .execute()
            )
            tracked_tickers = {
                row["ticker"].strip().upper()
                for row in (watch_res.data or [])
                if row.get("ticker")
            }

            if not tracked_tickers:
                print("No active tickers in watchlist. Skipping SEC scan.")
                return

            # Build CIK -> Ticker map for exact, zero-false-positive matching against SEC RSS titles
            cik_to_ticker = {}
            for t in tracked_tickers:
                try:
                    cik = XBRLService.get_cik_from_ticker(t)
                    cik_to_ticker[cik] = t
                except Exception:
                    pass

            print(f"Scanning latest filings for tracked assets: {tracked_tickers}")

            for entry in feed.entries:
                title = getattr(entry, "title", "")  # Format: "10-K - NVIDIA CORP (0001045810) (Filer)"
                if not title:
                    continue

                # Extract the form type accurately (e.g., 10-K, 10-Q, 20-F, 40-F)
                form_match = re.match(r"^(10-K|10-Q|20-F|40-F)\b", title.strip(), re.IGNORECASE)
                if not form_match:
                    continue
                form_type = form_match.group(1).upper()

                matched_ticker = None

                # Method A: Match via 10-digit CIK in parentheses "(0001045810)"
                cik_match = re.search(r"\((\d{10})\)", title)
                if cik_match and cik_match.group(1) in cik_to_ticker:
                    matched_ticker = cik_to_ticker[cik_match.group(1)]

                # Method B: Fallback explicit parenthetical ticker match e.g. "(NVDA)"
                if not matched_ticker:
                    for ticker in tracked_tickers:
                        if f"({ticker})" in title.upper():
                            matched_ticker = ticker
                            break

                if matched_ticker:
                    print(f"MATCH FOUND! New {form_type} filing detected for {matched_ticker}!")
                    print(f"Filing Title: {title}")

                    try:
                        print(f"Launching vectorizer for {matched_ticker} {form_type}...")
                        SECService.download_and_vectorize_filing(matched_ticker, preferred_form=form_type)
                        print(f"Successfully vectorized and cached {matched_ticker} {form_type}.")
                    except Exception as ve:
                        print(f"Failed to auto-vectorize filing for {matched_ticker}: {ve}")

        except Exception as e:
            print(f"Error checking SEC RSS feed: {e}")