from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone
from app.database import supabase_client
from app.services.news_service import NewsService
from app.services.xbrl_service import XBRLService
from app.services.sec_listener_service import SECListenerService


def hourly_news_pull():
    print(f"[{datetime.now(timezone.utc).isoformat()}] SCHEDULER: Starting hourly news pull...")
    try:
        response = supabase_client.table("soc_watchlist").select("ticker").eq("is_active", True).execute()
        tickers = [row["ticker"] for row in (response.data or []) if row.get("ticker")]
    except Exception as e:
        print(f"SCHEDULER: Failed to fetch watchlist for hourly news pull: {e}")
        return

    for ticker in tickers:
        try:
            print(f"Pulling news for {ticker}...")
            NewsService.fetch_and_store_news(ticker)

            supabase_client.table("soc_watchlist").update(
                {"last_news_pull": datetime.now(timezone.utc).isoformat()}
            ).eq("ticker", ticker).execute()

        except Exception as e:
            print(f"Failed to pull news for {ticker}: {e}")

    print(f"[{datetime.now(timezone.utc).isoformat()}] SCHEDULER: Hourly news pull complete.")


def daily_fundamentals_pull():
    print(f"[{datetime.now(timezone.utc).isoformat()}] SCHEDULER: Starting daily fundamentals pull...")
    try:
        response = supabase_client.table("soc_watchlist").select("ticker").eq("is_active", True).execute()
        tickers = [row["ticker"] for row in (response.data or []) if row.get("ticker")]
    except Exception as e:
        print(f"SCHEDULER: Failed to fetch watchlist for daily fundamentals pull: {e}")
        return

    for ticker in tickers:
        try:
            print(f"Pulling fundamentals for {ticker}...")
            XBRLService.fetch_and_store_fundamentals(ticker)

            supabase_client.table("soc_watchlist").update(
                {"last_fund_pull": datetime.now(timezone.utc).isoformat()}
            ).eq("ticker", ticker).execute()

        except Exception as e:
            print(f"Failed to pull fundamentals for {ticker}: {e}")


def check_sec_filings_job():
    try:
        SECListenerService.check_live_filings()
    except Exception as e:
        print(f"SEC Cron Job failed: {e}")


# Initialize the scheduler with coalescing and single-instance protection
scheduler = BackgroundScheduler(
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120}
)

# Mount the jobs
scheduler.add_job(hourly_news_pull, "interval", hours=1, id="hourly_news_pull", replace_existing=True)
scheduler.add_job(daily_fundamentals_pull, "interval", days=1, id="daily_fundamentals_pull", replace_existing=True)
scheduler.add_job(check_sec_filings_job, "interval", minutes=10, id="check_sec_filings_job", replace_existing=True)