import requests
import re
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
    def _rip_html_metric(html_text: str, json_keys: list, streamer_key: str, is_float: bool = False):
        """Rips exact metrics out of Yahoo's raw HTML DOM and Next.js hydration states."""
        # 1. Search the hidden JSON state
        for key in json_keys:
            match = re.search(rf'"{key}":\{{"raw":([\d\.\-]+)', html_text)
            if match:
                val = float(match.group(1))
                return val if is_float else int(val)
                
        # 2. Search the live fin-streamer tags as a backup
        if streamer_key:
            match = re.search(rf'data-field="{streamer_key}"[^>]*value="([\d\.\-]+)"', html_text)
            if match:
                val = float(match.group(1))
                return val if is_float else int(val)
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
            log_update(ticker_upper, f"SEC XBRL Extraction skipped (Likely Foreign Issuer like ADR).")

        # ==========================================
        # PHASE 2: STEALTH HTML RIPPER (No APIs, No Crumbs)
        # ==========================================
        log_update(ticker_upper, "Bypassing Yahoo APIs. Engaging direct HTML Data Ripper...")
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        try:
            # We hit the main webpage. They can't block this without killing their SEO.
            html_res = session.get(f'https://finance.yahoo.com/quote/{ticker_upper}', timeout=15)
            
            if html_res.status_code != 200:
                raise ValueError(f"Yahoo HTML page blocked. Status Code: {html_res.status_code}")
                
            html_text = html_res.text
            
            # 1. Validate Equity Type from HTML
            q_type_match = re.search(r'"quoteType":"([^"]+)"', html_text)
            if q_type_match:
                q_type = q_type_match.group(1)
                if q_type not in ["EQUITY", "ADR"]:
                    raise ValueError(f"'{ticker_upper}' is a {q_type}. Socrates AI requires equities or ADRs.")

            # 2. Rip Valuation Data
            market_cap = XBRLService._rip_html_metric(html_text, ["marketCap"], "marketCap", False)
            pe_ratio = XBRLService._rip_html_metric(html_text, ["trailingPE"], "trailingPE", True)
            
            # 3. Rip Fundamentals (Only override if SEC XBRL failed for foreign tickers)
            if eps is None:
                eps = XBRLService._rip_html_metric(html_text, ["trailingEps", "epsTrailingTwelveMonths"], "epsTrailingTwelveMonths", True)
            if revenue is None:
                revenue = XBRLService._rip_html_metric(html_text, ["totalRevenue"], "totalRevenue", False)
            if total_debt is None:
                total_debt = XBRLService._rip_html_metric(html_text, ["totalDebt"], "totalDebt", False)

            if market_cap is None:
                raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics in HTML payload.")
                
            log_update(ticker_upper, "HTML Rip Successful. Matrix data extracted flawlessly.")

        except ValueError as ve:
            raise ve
        except Exception as e:
            raise Exception(f"HTML Ripper Engine Failed: {str(e)}")

        # ==========================================
        # PHASE 3: SAFE TYPE CASTING & SUPABASE INJECT
        # ==========================================
        safe_revenue = int(revenue) if revenue is not None else None
        safe_market_cap = int(market_cap) if market_cap is not None else None
        safe_total_debt = int(total_debt) if total_debt is not None else None

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