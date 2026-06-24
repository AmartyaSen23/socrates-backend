import feedparser
import re
from app.database import supabase_client
from app.services.sec_service import SECService # Your existing 10-K downloader/chunker

class SECListenerService:
    @staticmethod
    def check_live_filings():
        print("Polling live SEC EDGAR RSS Feed...")
        
        # Live SEC feed for all latest filings
        SEC_RSS_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&start=0&count=40&output=atom"
        
        # SEC requires a descriptive User-Agent or they block the request
        headers = {
            "User-Agent": "SocratesAI Research Engine amartya@lpu.in"
        }
        
        try:
            # Fetch the raw XML feed text using requests to include headers
            import requests
            response = requests.get(SEC_RSS_URL, headers=headers)
            if response.status_code != 200:
                print(f"SEC RSS Feed returned status code: {response.status_code}")
                return
                
            # Parse the feed content
            feed = feedparser.parse(response.content)
            
            # 1. Pull the active tickers you care about from your watchlist
            watch_res = supabase_client.table("soc_watchlist").select("ticker").eq("is_active", True).execute()
            tracked_tickers = {row["ticker"].upper() for row in watch_res.data}
            
            if not tracked_tickers:
                print("No active tickers in watchlist. Skipping SEC scan.")
                return

            print(f"Scanning latest filings for tracked assets: {tracked_tickers}")

            for entry in feed.entries:
                title = entry.title # Format usually: "10-K - NVIDIA CORP (0001045810) (Filer)"
                
                # Extract the form type (e.g., 10-K, 10-Q)
                form_match = re.match(r"^([10\-[KQCP]+[^ ]*)", title)
                if not form_match:
                    continue
                form_type = form_match.group(1)

                # We only care about annual (10-K) and quarterly (10-Q) reports
                if form_type not in ["10-K", "10-Q"]:
                    continue

                # Extract the ticker symbol from the title or entry text if available
                # The SEC RSS feed title includes the company name. We map via matching words or extracting CIK.
                # To keep it ultra-accurate, let's look for our tracked tickers directly in the title string.
                matched_ticker = None
                for ticker in tracked_tickers:
                    if f"({ticker})" in title or ticker in title.upper():
                        matched_ticker = ticker
                        break
                
                if matched_ticker:
                    print(f"🚨 MATCH FOUND! New {form_type} filing detected for {matched_ticker}!")
                    print(f"Filing Title: {title}")
                    
                    # 2. Trigger your Vector RAG Pipeline Autonomously!
                    # This will download, clean, chunk, embed via Cohere, and save to pgvector
                    try:
                        print(f"Launching vectorizer for {matched_ticker} {form_type}...")
                        # Assuming your existing SECService has a method to process a specific form type
                        SECService.download_and_vectorize_filing(matched_ticker, form_type)
                        print(f"Successfully vectorized and cached {matched_ticker} {form_type}.")
                    except Exception as ve:
                        print(f"Failed to auto-vectorize filing for {matched_ticker}: {ve}")
                        
        except Exception as e:
            print(f"Error checking SEC RSS feed: {e}")