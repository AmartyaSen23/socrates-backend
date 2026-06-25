import requests
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update

class XBRLService:
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
        # PHASE 1: SEC EDGAR XBRL (Accounting Data)
        # ==========================================
        log_update(ticker_upper, "Fetching audited accounting metrics from SEC EDGAR XBRL...")
        revenue = None
        eps = None
        total_debt = None
        
        try:
            cik = XBRLService.get_cik_from_ticker(ticker_upper)
            facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts_res = requests.get(facts_url, headers=XBRLService.SEC_HEADERS, timeout=15)
            
            if facts_res.status_code == 200:
                facts_data = facts_res.json()
                revenue = XBRLService.extract_latest_fact(facts_data, ['Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax'])
                eps = XBRLService.extract_latest_fact(facts_data, ['EarningsPerShareBasic', 'EarningsPerShareDiluted'])
                total_debt = XBRLService.extract_latest_fact(facts_data, ['LongTermDebt', 'DebtCurrent', 'LongTermDebtAndCapitalLeaseObligations'])
                log_update(ticker_upper, f"SEC XBRL Extraction Success.")
            else:
                log_update(ticker_upper, f"Warning: SEC XBRL returned status {facts_res.status_code}.")
        except Exception as e:
            log_update(ticker_upper, f"SEC XBRL Extraction failed or skipped for Foreign Issuer.")

        # ==========================================
        # PHASE 2: YAHOO FALLBACK ROUTINE
        # ==========================================
        log_update(ticker_upper, "Executing Market Valuation Fallback...")
        market_cap = None
        pe_ratio = None

        try:
            # 1. Try simple YFinance first (often works for foreign ADRs like WIT)
            stock = yf.Ticker(ticker_upper)
            info = stock.info
            
            if info and "regularMarketPrice" in info or "marketCap" in info:
                market_cap = info.get("marketCap")
                pe_ratio = info.get("trailingPE")
                if eps is None: eps = info.get("trailingEps")
                if revenue is None: revenue = info.get("totalRevenue")
                if total_debt is None: total_debt = info.get("totalDebt")
                log_update(ticker_upper, "Successfully extracted valuation from standard Yahoo.")
            else:
                # 2. If standard YFinance is blocked, use the Crumb Bypass
                log_update(ticker_upper, "Standard Yahoo blocked. Attempting Crumb Handshake...")
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                    'Accept': '*/*'
                })
                session.get('https://fc.yahoo.com', timeout=10)
                crumb_response = session.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10)
                crumb = crumb_response.text
                
                url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker_upper}&crumb={crumb}"
                response = session.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    quote_result = data.get("quoteResponse", {}).get("result", [])
                    if quote_result:
                        asset_data = quote_result[0]
                        if asset_data.get("quoteType") != "EQUITY":
                            raise ValueError(f"'{ticker_upper}' is a {asset_data.get('quoteType')}. Socrates AI requires equities.")
                        
                        market_cap = asset_data.get("marketCap")
                        pe_ratio = asset_data.get("trailingPE")
                        if eps is None: eps = asset_data.get("trailingEps")
                        if revenue is None: revenue = asset_data.get("totalRevenue")
                        log_update(ticker_upper, "Successfully bypassed security and extracted matrix data.")

            if market_cap is None or market_cap == 0:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Valuation Engine Failed: {str(e)}")

        # ==========================================
        # PHASE 3: SAFE TYPE CASTING & SUPABASE INJECT
        # ==========================================
        # THE FIX: Cast large floats to integers to prevent PostgreSQL 'BIGINT' crashes!
        safe_revenue = int(revenue) if revenue is not None else None
        safe_market_cap = int(market_cap) if market_cap is not None else None
        safe_total_debt = int(total_debt) if total_debt is not None else None
        # EPS and PE can remain floats

        payload = {
            "ticker": ticker_upper,
            "revenue": safe_revenue, 
            "eps": eps,
            "pe_ratio": pe_ratio,
            "market_cap": safe_market_cap,
            "total_debt": safe_total_debt,
            "fiscal_date": today
        }
        
        try:
            db_response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            return db_response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")