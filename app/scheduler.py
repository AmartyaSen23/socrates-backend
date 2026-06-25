from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from app.database import supabase_client
from app.services.news_service import NewsService
from app.services.xbrl_service import XBRLService
from app.services.sec_listener_service import SECListenerService

def hourly_news_pull():
    print(f"[{datetime.now()}] SCHEDULER: Starting hourly news pull...")
    # 1. Fetch only the active tickers from our watchlist
    response = supabase_client.table("soc_watchlist").select("ticker").eq("is_active", True).execute()
    tickers = [row["ticker"] for row in response.data]
    
    # 2. Iterate and ingest (We add a tiny delay in the service to be polite to yfinance)
    for ticker in tickers:
        try:
            print(f"Pulling news for {ticker}...")
            NewsService.fetch_and_store_news(ticker)
            
            # Update the timestamp in the database
            supabase_client.table("soc_watchlist").update(
                {"last_news_pull": datetime.utcnow().isoformat()}
            ).eq("ticker", ticker).execute()
            
        except Exception as e:
            print(f"Failed to pull news for {ticker}: {e}")
            
    print(f"[{datetime.now()}] SCHEDULER: Hourly news pull complete.")

def daily_fundamentals_pull():
    print(f"[{datetime.now()}] SCHEDULER: Starting daily fundamentals pull...")
    response = supabase_client.table("soc_watchlist").select("ticker").eq("is_active", True).execute()
    tickers = [row["ticker"] for row in response.data]
    
    for ticker in tickers:
        try:
            print(f"Pulling fundamentals for {ticker}...")
            XBRLService.fetch_and_store_fundamentals(ticker)
            
            supabase_client.table("soc_watchlist").update(
                {"last_fund_pull": datetime.utcnow().isoformat()}
            ).eq("ticker", ticker).execute()
            
        except Exception as e:
            print(f"Failed to pull fundamentals for {ticker}: {e}")

def check_sec_filings_job():
    try:
        SECListenerService.check_live_filings()
    except Exception as e:
        print(f"SEC Cron Job failed: {e}")

# Initialize the scheduler
scheduler = BackgroundScheduler()

# Mount the jobs
# For testing purposes, we can set it to run every few minutes instead of hours
scheduler.add_job(hourly_news_pull, 'interval', hours=1)
scheduler.add_job(daily_fundamentals_pull, 'interval', days=1)
scheduler.add_job(check_sec_filings_job, 'interval', minutes=10)