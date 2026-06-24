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
            fast = stock.fast_info

            if not fast or not hasattr(fast, 'market_cap'): 
                raise ValueError(f"Yahoo Finance returned an empty response for '{ticker_upper}'. The API is likely throttling us.")
                
            # --- TIER 5: STRICT EQUITY VALIDATION ---
            market_cap = fast.market_cap
            
            if market_cap is None or market_cap == 0:
                raise ValueError(f"'{ticker_upper}' lacks market cap data. Socrates AI requires publicly traded companies.")
                
        except ValueError as ve:
            raise ve # Pass our custom validation error up to the router
        except Exception as e:
            raise Exception(f"YFinance API Error: {str(e)}")
            
        print(f"Successfully pulled data for {ticker}. Formatting for database...")

        pe_ratio = None
        revenue = None
        eps = None
        total_debt = None
        try:
            # We cautiously peek into .info
            pe_ratio = stock.info.get('trailingPE')
            revenue = stock.info.get('totalRevenue')
            eps = stock.info.get('trailingEps')
            total_debt = stock.info.get('totalDebt')
        except Exception as e:
            print(f"[{ticker_upper}] Yahoo blocked deep fundamentals, falling back to fast_info.")

        payload = {
            "ticker": ticker_upper,
            "revenue": revenue,
            "eps": eps,
            "pe_ratio": pe_ratio,
            "market_cap": market_cap,
            "total_debt": total_debt,
            "fiscal_date": today
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