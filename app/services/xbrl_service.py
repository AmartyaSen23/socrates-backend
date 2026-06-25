import requests
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update

class XBRLService:
    # SEC requires a descriptive User-Agent
    SEC_HEADERS = {'User-Agent': 'SocratesResearchEngine admin@socrates.com'}

    @staticmethod
    def get_cik_from_ticker(ticker: str) -> str:
        """Fetches the SEC CIK (Central Index Key) for a given ticker."""
        url = "https://www.sec.gov/files/company_tickers.json"
        response = requests.get(url, headers=XBRLService.SEC_HEADERS, timeout=10)
        if response.status_code != 200:
            raise ValueError("Failed to fetch SEC CIK mapping.")
            
        data = response.json()
        for key, company in data.items():
            if company['ticker'] == ticker:
                # SEC APIs require the CIK to be exactly 10 digits, padded with leading zeros
                return str(company['cik_str']).zfill(10)
        raise ValueError(f"Ticker '{ticker}' not found in SEC EDGAR database. It may not be a US public equity.")

    @staticmethod
    def extract_latest_fact(company_facts: dict, possible_tags: list) -> float:
        """Scans the SEC JSON for various GAAP tags and returns the most recent value."""
        us_gaap = company_facts.get('facts', {}).get('us-gaap', {})
        
        for tag in possible_tags:
            if tag in us_gaap:
                # Financials are usually reported in USD
                units = us_gaap[tag].get('units', {})
                if 'USD' in units:
                    observations = units['USD']
                    # We want the most recent Annual (10-K) or Quarterly (10-Q) filing
                    # Filter out empty values and sort by filing date
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
            print(f"Cache check failed, proceeding to fetch: {e}")

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
                
                # Companies use different tags for the same concepts. We check the most common ones.
                revenue = XBRLService.extract_latest_fact(facts_data, ['Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax'])
                eps = XBRLService.extract_latest_fact(facts_data, ['EarningsPerShareBasic', 'EarningsPerShareDiluted'])
                total_debt = XBRLService.extract_latest_fact(facts_data, ['LongTermDebt', 'DebtCurrent', 'LongTermDebtAndCapitalLeaseObligations'])
                
                log_update(ticker_upper, f"SEC XBRL Extraction Success. Debt found: ${total_debt:,.2f}" if total_debt else "SEC XBRL Extraction Success. No standard debt tag found.")
            else:
                log_update(ticker_upper, f"Warning: SEC XBRL returned status {facts_res.status_code}. Defaulting to None.")
        except Exception as e:
            log_update(ticker_upper, f"Warning: SEC XBRL Extraction failed: {e}. Metrics will be None.")
        
        # ==========================================
        # PHASE 2: YAHOO CRUMB BYPASS (Live Valuation)
        # ==========================================
        log_update(ticker_upper, "Executing Yahoo Crumb Handshake for Live Market Valuation...")
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        })

        try:
            session.get('https://fc.yahoo.com', timeout=10)
            crumb_response = session.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10)
            crumb = crumb_response.text
            
            if not crumb or 'html' in crumb:
                raise ValueError("Yahoo security blockade: Failed to generate authentication crumb.")
                
            url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker_upper}&crumb={crumb}"
            response = session.get(url, timeout=10)
            
            if response.status_code != 200:
                raise ValueError(f"Yahoo API rejected request with status code {response.status_code}")
                
            data = response.json()
            quote_result = data.get("quoteResponse", {}).get("result", [])
            
            if not quote_result:
                raise ValueError(f"No market equity data returned for target '{ticker_upper}'")
                
            asset_data = quote_result[0]
            
            quote_type = asset_data.get("quoteType")
            if quote_type != "EQUITY":
                raise ValueError(f"'{ticker_upper}' is a {quote_type}. Socrates AI requires publicly traded corporate equities.")

            market_cap = asset_data.get("marketCap")
            pe_ratio = asset_data.get("trailingPE")
            
            # If SEC EPS failed, fallback to Yahoo's live trailing EPS
            if eps is None:
                eps = asset_data.get("trailingEps")
            # If SEC Revenue failed, fallback to Yahoo's Revenue
            if revenue is None:
                revenue = asset_data.get("totalRevenue")

            if market_cap is None or market_cap == 0:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

            log_update(ticker_upper, "Successfully bypassed security and extracted live valuation matrix.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"Valuation Bypass Engine Interrupted: {str(e)}")

        # ==========================================
        # PHASE 3: FORGE THE SUPABASE PAYLOAD
        # ==========================================
        payload = {
            "ticker": ticker_upper,
            "revenue": revenue, 
            "eps": eps,
            "pe_ratio": pe_ratio,
            "market_cap": market_cap,
            "total_debt": total_debt,
            "fiscal_date": today
        }
        
        try:
            db_response = supabase_client.table("soc_company_fundamentals").upsert(
                payload, on_conflict="ticker, fiscal_date"
            ).execute()
            
            return db_response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")