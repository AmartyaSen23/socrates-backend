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
        # PHASE 2: FINNHUB API (Replacing yfinance)
        # ==========================================
        log_update(ticker_upper, "Fetching live market data via Finnhub API...")
        market_cap = None
        pe_ratio = None
        current_price = None

        # Best practice: Pull this from os.environ or your .env file
        FINNHUB_API_KEY = "your_free_finnhub_api_key" 

        try:
            # 1. Fetch Current Price (Quote Endpoint)
            quote_url = f"https://finnhub.io/api/v1/quote?symbol={ticker_upper}&token={FINNHUB_API_KEY}"
            quote_res = requests.get(quote_url, timeout=10)
            
            if quote_res.status_code == 200:
                quote_data = quote_res.json()
                # Finnhub returns 'c' for current price. It returns 0 if the symbol is invalid.
                if quote_data.get('c') and float(quote_data.get('c')) > 0:
                    current_price = float(quote_data['c'])
            
            # 2. Fetch Valuation Metrics (Basic Financials Endpoint)
            metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker_upper}&metric=all&token={FINNHUB_API_KEY}"
            metrics_res = requests.get(metrics_url, timeout=10)
            
            if metrics_res.status_code == 200:
                # Finnhub nests the actual data inside a 'metric' dictionary
                metrics_data = metrics_res.json().get('metric', {})
                
                # Finnhub returns marketCapitalization in Millions (e.g., 2800000 for 2.8 Trillion)
                raw_mcap = metrics_data.get('marketCapitalization')
                if raw_mcap:
                    market_cap = float(raw_mcap) * 1000000  # Convert millions to standard integer format
                    
                pe_ratio = metrics_data.get('peTTM')
                
                # Bonus: Backfill EPS if the SEC XBRL Phase missed it
                if eps is None:
                    eps = metrics_data.get('epsTTM')
                
            if current_price and market_cap:
                log_update(ticker_upper, "Successfully extracted valuation using Finnhub API.")
            else:
                log_update(ticker_upper, f"Warning: Finnhub could not find full valuation for {ticker_upper}.")
                 
        except Exception as e:
            raise Exception(f"Finnhub Valuation Engine Failed: {str(e)}")

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