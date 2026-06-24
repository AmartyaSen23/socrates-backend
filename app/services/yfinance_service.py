import yfinance as yf
from app.database import supabase_client
from datetime import datetime
import requests

class YFinanceService:
    @staticmethod
    def fetch_and_store_fundamentals(ticker: str):
        ticker_upper = ticker.upper()
        today = datetime.today().strftime('%Y-%m-%d')

        # 1. CHECK DATABASE FIRST TO AVOID RATE LIMITS
        try:
            cached_data = supabase_client.table("soc_company_fundamentals") \
                .select("*") \
                .eq("ticker", ticker_upper) \
                .eq("fiscal_date", today) \
                .execute()
                
            if cached_data.data:
                print(f"Data for {ticker_upper} already exists for today. Skipping Yahoo Finance.")
                return cached_data.data
        except Exception as e:
            print(f"Cache check failed, proceeding to fetch: {e}")
        
        print(f"Fetching fundamentals for {ticker} from Yahoo Finance...")
        session = requests.Session()

        # 2. USE A CUSTOM SESSION WITH A REAL BROWSER USER-AGENT
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        })

        market_cap = None
        revenue = None

        try:
            # Pass the custom session to yfinance
            stock = yf.Ticker(ticker_upper, session=session)
            info = stock.info

            if info is None:
                # Perhaps implement a small sleep and a retry here, or just raise a specific error
                raise ValueError(f"Yahoo Finance returned an empty response for {ticker}. The API is likely throttling us.")

            if not info or len(info) <= 5: 
                raise ValueError(f"The market data provider is currently unavailable for '{ticker}'. Please try again in a few minutes.")
                
            # --- TIER 5: STRICT EQUITY VALIDATION ---
            market_cap = info.get("marketCap")
            revenue = info.get("totalRevenue")
            
            if market_cap is None and revenue is None:
                raise ValueError(f"'{ticker}' appears to be a commodity, index, or invalid equity. Socrates AI requires publicly traded companies that file SEC 10-Ks.")
                
        except ValueError as ve:
            raise ve # Pass our custom validation error up to the router
        except Exception as e:
            raise Exception(f"YFinance API Error: {str(e)}")
            
        print(f"Successfully pulled data for {ticker}. Formatting for database...")

        payload = {
            "ticker": ticker.upper(),
            "revenue": revenue,
            "eps": info.get("trailingEps"),
            "pe_ratio": info.get("trailingPE"),
            "market_cap": market_cap,
            "total_debt": info.get("totalDebt"),
            "fiscal_date": datetime.today().strftime('%Y-%m-%d')
        }
        
        print(f"Payload ready: {payload}")
        print("Pushing to Supabase...")
        
        try:
            response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            
            return response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")