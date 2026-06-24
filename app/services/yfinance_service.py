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
        
        print(f"[{ticker_upper}] Bypassing yfinance library. Pinging Yahoo Engine directly...")
        
        # 2. RAW HTTP CALL TO YAHOO V7 DIRECT ENDPOINT (Bypasses Cookie Wall)
        url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker_upper}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                raise ValueError(f"Yahoo API rejected request with status code {response.status_code}")
                
            data = response.json()
            quote_result = data.get("quoteResponse", {}).get("result", [])
            
            if not quote_result:
                raise ValueError(f"No market equity data returned for target '{ticker_upper}'")
                
            asset_data = quote_result[0]
            
            # --- TIER 5: EQUITIES ONLY FILTER ---
            # Double check that we aren't scanning crypto or indices
            quote_type = asset_data.get("quoteType")
            if quote_type != "EQUITY":
                raise ValueError(f"'{ticker_upper}' is a {quote_type}. Socrates AI requires publicly traded corporate equities.")

            # 3. EXTRACT METRICS SAFELY FROM RAW API RESPONSE
            market_cap = asset_data.get("marketCap")
            pe_ratio = asset_data.get("trailingPE")
            eps = asset_data.get("trailingEps")
            revenue = asset_data.get("totalRevenue") # May require an extra endpoint if empty, but quote often packages it
            
            # If direct totalRevenue isn't on the quick quote, let's keep it clean
            if market_cap is None or market_cap == 0:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

            print(f"[{ticker_upper}] Successfully intercepted market matrix data.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Bypass Engine Interrupted: {str(e)}")

        # 4. FORGE THE SUPABASE PAYLOAD
        payload = {
            "ticker": ticker_upper,
            "revenue": revenue, 
            "eps": eps,
            "pe_ratio": pe_ratio,
            "market_cap": market_cap,
            "total_debt": None, # Heavy balance sheet metrics are fully locked behind cookie walls on cloud providers
            "fiscal_date": today
        }
        
        print(f"Payload ready for transfer: {payload}")
        print("Committing matrix to Supabase...")
        
        try:
            response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            
            return response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")