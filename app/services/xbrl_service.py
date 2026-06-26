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
        # DYNAMIC UPGRADE: Handle US Domestic (us-gaap) and International ADRs (ifrs-full)
        accounting_standards = ['us-gaap', 'ifrs-full']
        
        for standard in accounting_standards:
            taxonomy = company_facts.get('facts', {}).get(standard, {})
            if not taxonomy:
                continue
                
            for tag in possible_tags:
                if tag in taxonomy:
                    units = taxonomy[tag].get('units', {})
                    # Grab USD if available, otherwise take the first reported currency unit
                    val_key = 'USD' if 'USD' in units else list(units.keys())[0] if units else None
                    
                    if val_key:
                        observations = units[val_key]
                        valid_obs = [obs for obs in observations if 'val' in obs and 'filed' in obs]
                        if valid_obs:
                            # Sort by filed date to ensure we grab the absolute latest audited number
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
        # PHASE 2 & 3: THE VALUATION WATERFALL
        # ==========================================
        log_update(ticker_upper, "Initiating dynamic valuation waterfall...")
        market_cap = None
        pe_ratio = None
        current_price = None

        # Best practice: Pull this from os.environ
        FINNHUB_API_KEY = "your_free_finnhub_api_key"

        # --- BLOCK A: FINNHUB PRIMARY API ---
        try:
            # 1. Quote Endpoint (Live Price)
            quote_res = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker_upper}&token={FINNHUB_API_KEY}", timeout=5)
            if quote_res.status_code == 200:
                q_data = quote_res.json()
                if q_data.get('c') and float(q_data['c']) > 0:
                    current_price = float(q_data['c'])

            # 2. Profile2 Endpoint (Rock-Solid Market Cap & Shares Outstanding)
            shares_outstanding = None
            profile_res = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker_upper}&token={FINNHUB_API_KEY}", timeout=5)
            if profile_res.status_code == 200:
                p_data = profile_res.json()
                if p_data.get('marketCapitalization'):
                    market_cap = float(p_data['marketCapitalization']) * 1000000
                if p_data.get('shareOutstanding'):
                    shares_outstanding = float(p_data['shareOutstanding']) * 1000000

            # 3. Metric Endpoint (For PE and EPS)
            metric_res = requests.get(f"https://finnhub.io/api/v1/stock/metric?symbol={ticker_upper}&metric=all&token={FINNHUB_API_KEY}", timeout=5)
            if metric_res.status_code == 200:
                m_data = metric_res.json().get('metric', {})
                pe_ratio = m_data.get('peTTM')
                if eps is None:
                    eps = m_data.get('epsTTM')
                    
        except Exception as e:
            log_update(ticker_upper, f"Finnhub primary fetch encountered an issue: {e}")

        # --- BLOCK B: YFINANCE SILENT FALLBACK ---
        if market_cap is None or current_price is None:
            log_update(ticker_upper, "Finnhub missed structural data. Cascading to yfinance fallback...")
            try:
                stock = yf.Ticker(ticker_upper)
                fast = stock.fast_info
                if current_price is None:
                    current_price = getattr(fast, 'last_price', getattr(fast, 'previous_close', None))
                if market_cap is None:
                    market_cap = getattr(fast, 'market_cap', None)
            except Exception:
                pass

        # --- BLOCK C: MATHEMATICAL RECONSTRUCTION ---
        if market_cap is None and current_price is not None and shares_outstanding is not None:
            log_update(ticker_upper, "Cascading to Math Reconstruction: Price * Shares...")
            market_cap = current_price * shares_outstanding

        if pe_ratio is None and current_price and eps and float(eps) > 0:
            pe_ratio = current_price / float(eps)

        # Final Hard Validation
        if market_cap is None or (isinstance(market_cap, float) and math.isnan(market_cap)):
            raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics after all fallbacks.")
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