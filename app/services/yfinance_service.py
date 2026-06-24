import yfinance as yf
from app.database import supabase_client
from datetime import datetime

class YFinanceService:
    @staticmethod
    def fetch_and_store_fundamentals(ticker: str):
        print(f"Fetching fundamentals for {ticker} from Yahoo Finance...")
        market_cap = None
        revenue = None
        try:
            stock = yf.Ticker(ticker)
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