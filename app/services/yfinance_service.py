import requests
from app.database import supabase_client
from datetime import datetime

class YFinanceService:
    @staticmethod
    def fetch_and_store_fundamentals(ticker: str):
        ticker_upper = ticker.upper()
        today = datetime.today().strftime('%Y-%m-%d')

        # 1. CHECK DATABASE FIRST
        try:
            cached_data = supabase_client.table("soc_company_fundamentals") \
                .select("*") \
                .eq("ticker", ticker_upper) \
                .eq("fiscal_date", today) \
                .execute()
                
            if cached_data.data:
                print(f"[{ticker_upper}] Data already exists. Skipping API.")
                return cached_data.data
        except Exception as e:
            print(f"Cache check failed, proceeding to fetch: {e}")
        
        print(f"[{ticker_upper}] Executing Yahoo Crumb Handshake...")
        
        # 2. THE YAHOO 401 BYPASS (Cookie & Crumb Handshake)
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        })

        try:
            # Step A: Hit the front page to grab a session cookie
            session.get('https://fc.yahoo.com', timeout=10)
            
            # Step B: Request the cryptographic crumb
            crumb_response = session.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10)
            crumb = crumb_response.text
            
            if not crumb or 'html' in crumb:
                raise ValueError("Yahoo security blockade: Failed to generate authentication crumb.")
                
            # Step C: Attach the crumb to our v7 query
            url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker_upper}&crumb={crumb}"
            response = session.get(url, timeout=10)
            
            if response.status_code != 200:
                raise ValueError(f"Yahoo API rejected request with status code {response.status_code}")
                
            data = response.json()
            quote_result = data.get("quoteResponse", {}).get("result", [])
            
            if not quote_result:
                raise ValueError(f"No market equity data returned for target '{ticker_upper}'")
                
            asset_data = quote_result[0]
            
            # --- TIER 5: EQUITIES ONLY FILTER ---
            quote_type = asset_data.get("quoteType")
            if quote_type != "EQUITY":
                raise ValueError(f"'{ticker_upper}' is a {quote_type}. Socrates AI requires publicly traded corporate equities.")

            market_cap = asset_data.get("marketCap")
            pe_ratio = asset_data.get("trailingPE")
            eps = asset_data.get("trailingEps")
            revenue = asset_data.get("totalRevenue")
            
            if market_cap is None or market_cap == 0:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

            print(f"[{ticker_upper}] Successfully bypassed security and extracted matrix data.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Bypass Engine Interrupted: {str(e)}")

        # 3. FORGE THE SUPABASE PAYLOAD
        payload = {
            "ticker": ticker_upper,
            "revenue": revenue, 
            "eps": eps,
            "pe_ratio": pe_ratio,
            "market_cap": market_cap,
            "total_debt": None,
            "fiscal_date": today
        }
        
        try:
            db_response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            
            return db_response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")