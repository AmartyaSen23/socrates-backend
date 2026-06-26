import requests
import math
import yfinance as yf
from app.database import supabase_client
from datetime import datetime, timedelta
from app.status_store import log_update

class XBRLService:
    # Official SEC User-Agent requirement
    SEC_HEADERS = {'User-Agent': 'SocratesResearchEngine admin@socrates.com'}

    @staticmethod
    def get_cik_from_ticker(ticker: str) -> str:
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=XBRLService.SEC_HEADERS, timeout=10)
        if response.status_code != 200:
            raise ValueError("Failed to fetch SEC CIK mapping.")
            
        data = response.json()
        for key, company in data.items():
            if company['ticker'] == ticker:
                return str(company['cik_str']).zfill(10)
        raise ValueError(f"Ticker '{ticker}' not found in SEC EDGAR database.")

    @staticmethod
    def extract_latest_fact(company_facts: dict, possible_tags: list) -> float:
        us_gaap = company_facts.get('facts', {}).get('us-gaap', {})
        for tag in possible_tags:
            if tag in us_gaap:
                units = us_gaap[tag].get('units', {})
                if 'USD' in units:
                    observations = units['USD']
                    valid_obs = [obs for obs in observations if 'val' in obs and 'filed' in obs]
                    if valid_obs:
                        latest_obs = sorted(valid_obs, key=lambda x: x['filed'], reverse=True)[0]
                        return float(latest_obs['val'])
        return None

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
            print(f"Cache check failed: {e}")

        # ==========================================
        # PHASE 1: SEC EDGAR XBRL (The Official Way)
        # ==========================================
        log_update(ticker_upper, "Fetching audited accounting metrics from SEC EDGAR XBRL...")
        revenue = None
        eps = None
        total_debt = None
        
        try:
            cik = XBRLService.get_cik_from_ticker(ticker_upper)
            facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts_res = requests.get(facts_url, headers=XBRLService.SEC_HEADERS, timeout=10)
            
            if facts_res.status_code == 200:
                facts_data = facts_res.json()
                revenue = XBRLService.extract_latest_fact(facts_data, ['Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax'])
                eps = XBRLService.extract_latest_fact(facts_data, ['EarningsPerShareBasic', 'EarningsPerShareDiluted'])
                total_debt = XBRLService.extract_latest_fact(facts_data, ['LongTermDebt', 'DebtCurrent', 'LongTermDebtAndCapitalLeaseObligations'])
                log_update(ticker_upper, f"SEC XBRL Extraction Success.")
            else:
                log_update(ticker_upper, f"Warning: SEC XBRL returned status {facts_res.status_code}.")
        except Exception as e:
            log_update(ticker_upper, f"SEC XBRL Extraction skipped (Likely Foreign ADR).")

        # ==========================================
        # PHASE 2: STANDARD YFINANCE FAST_INFO
        # ==========================================
        log_update(ticker_upper, "Fetching live market data via yfinance fast_info...")
        market_cap = None
        pe_ratio = None
        current_price = None

        try:
            stock = yf.Ticker(ticker_upper)
            
            # --- LAYER 1: Object/Dict agnostic fast_info extraction ---
            try:
                fast = stock.fast_info
                # Attempt attribute access (newer yfinance)
                market_cap = getattr(fast, 'market_cap', None)
                current_price = getattr(fast, 'last_price', None)
                
                # Attempt dict access (older yfinance) if attributes were missing
                if market_cap is None and hasattr(fast, 'get'):
                    market_cap = fast.get('market_cap', fast.get('marketCap'))
                if current_price is None and hasattr(fast, 'get'):
                    current_price = fast.get('last_price', fast.get('regularMarketPrice'))
            except Exception:
                pass

            # --- LAYER 2: Try grabbing standard .info for missing gaps ---
            try:
                info = stock.info
                if market_cap is None: market_cap = info.get("marketCap")
                if current_price is None: current_price = info.get("currentPrice", info.get("regularMarketPrice"))
                if revenue is None: revenue = info.get("totalRevenue")
                if eps is None: eps = info.get("trailingEps")
                if total_debt is None: total_debt = info.get("totalDebt")
                if pe_ratio is None: pe_ratio = info.get("trailingPE")
            except Exception:
                log_update(ticker_upper, "Note: Standard .info dictionary was blocked by Yahoo.")

            # --- LAYER 3: The Ultimate Bulletproof Fallback (Mathematical Reconstruction) ---
            if current_price is None or (isinstance(current_price, float) and math.isnan(current_price)):
                try:
                    hist = stock.history(period="5d")
                    if not hist.empty:
                        current_price = float(hist['Close'].iloc[-1])
                except Exception:
                    pass

            if market_cap is None or (isinstance(market_cap, float) and math.isnan(market_cap)):
                try:
                    start_date = (datetime.today() - timedelta(days=30)).strftime('%Y-%m-%d')
                    shares = stock.get_shares_full(start=start_date, end=today)
                    if shares is not None and not shares.empty and current_price:
                        market_cap = current_price * float(shares.iloc[-1])
                        log_update(ticker_upper, "Market Cap mathematically reconstructed via shares outstanding!")
                except Exception:
                    pass

            # Calculate P/E mathematically if Yahoo hid it!
            if pe_ratio is None and current_price and eps and eps > 0:
                pe_ratio = current_price / eps
                
            log_update(ticker_upper, "Successfully extracted valuation using standard APIs.")

        except Exception as e:
            raise Exception(f"Standard Valuation Engine Failed: {str(e)}")

        # Hard validation checkpoint
        if market_cap is None or (isinstance(market_cap, float) and math.isnan(market_cap)):
            raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

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
            db_response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            return db_response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")