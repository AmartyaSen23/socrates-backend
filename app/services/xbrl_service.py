import requests
import math
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update

class XBRLService:
    @staticmethod
    def fetch_and_store_fundamentals(ticker: str):
        ticker_upper = ticker.upper()
        today = datetime.today().strftime('%Y-%m-%d')

        # 1. CHECK DATABASE CACHE
        try:
            cached_data = supabase_client.table("soc_company_fundamentals") \
                .select("*") \
                .eq("ticker", ticker_upper) \
                .eq("fiscal_date", today) \
                .execute()
                
            if cached_data.data:
                log_update(ticker_upper, "Fundamentals exist in cache. Skipping API.")
                return cached_data.data
        except Exception as e:
            pass

        log_update(ticker_upper, "Engaging Global Institutional Scanner (TradingView Protocol)...")

        # 🛡️ THE FIX: Stealth Browser Headers to bypass Cloudflare
        tv_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Origin": "https://www.tradingview.com",
            "Referer": "https://www.tradingview.com/"
        }

        try:
            # ==========================================
            # STEP 1: RESOLVE GLOBAL EXCHANGE
            # ==========================================
            search_url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={ticker_upper}&hl=1&type=stock"
            search_res = requests.get(search_url, headers=tv_headers, timeout=10)
            
            if search_res.status_code != 200:
                raise ValueError(f"Failed to reach Global Search API. Status: {search_res.status_code}")
                
            results = search_res.json()
            if not results:
                raise ValueError(f"Ticker '{ticker_upper}' not found on any global exchange.")
            
            # Grab the top match to get the exact Exchange and Country
            best_match = results[0]
            exchange = best_match.get("exchange")
            symbol = best_match.get("symbol")
            country = best_match.get("country", "US").lower()
            
            tv_ticker = f"{exchange}:{symbol}"
            log_update(ticker_upper, f"Resolved to Global Exchange: {tv_ticker} ({country.upper()})")

            # Map the country to TradingView's regional scanner clusters
            region_map = {
                "us": "america",
                "in": "india",
                "uk": "uk",
                "ca": "canada",
                "au": "australia",
                "cn": "china",
                "jp": "japan",
                "de": "germany",
                "fr": "france"
            }
            region = region_map.get(country, "america") # Fallback to america

            # ==========================================
            # STEP 2: RIP EXACT FUNDAMENTALS
            # ==========================================
            scanner_url = f"https://scanner.tradingview.com/{region}/scan"
            payload = {
                "symbols": {"tickers": [tv_ticker]},
                "columns": [
                    "market_cap_basic", 
                    "price_earnings_ttm", 
                    "earnings_per_share_basic_ttm", 
                    "total_revenue", 
                    "total_debt"
                ]
            }
            
            # 🛡️ THE FIX: Pass headers here too!
            scan_res = requests.post(scanner_url, headers=tv_headers, json=payload, timeout=10)
            
            if scan_res.status_code != 200:
                raise ValueError(f"Scanner rejected the data request. Status: {scan_res.status_code}")
                
            scan_data = scan_res.json().get("data", [])
            if not scan_data:
                raise ValueError(f"No fundamental data published for {tv_ticker}.")
                
            # Extract the 5 data points
            metrics = scan_data[0].get("d", [])
            
            market_cap = metrics[0]
            pe_ratio = metrics[1]
            eps = metrics[2]
            revenue = metrics[3]
            total_debt = metrics[4]

            if not market_cap:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

            log_update(ticker_upper, "Successfully extracted audited global fundamentals.")

        except Exception as e:
            raise Exception(f"Valuation Engine Failed: {str(e)}")

        # ==========================================
        # PHASE 3: SAFE TYPE CASTING & SUPABASE INJECT
        # ==========================================
        def safe_cast(val):
            if val is None or (isinstance(val, float) and math.isnan(val)): 
                return None
            return int(val)

        payload = {
            "ticker": ticker_upper,
            "revenue": safe_cast(revenue), 
            "eps": float(eps) if eps is not None and not math.isnan(float(eps)) else None,
            "pe_ratio": float(pe_ratio) if pe_ratio is not None and not math.isnan(float(pe_ratio)) else None,
            "market_cap": safe_cast(market_cap),
            "total_debt": safe_cast(total_debt),
            "fiscal_date": today
        }
        
        try:
            supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            return payload
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")