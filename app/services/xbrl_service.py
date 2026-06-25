import requests
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update
import yfinance as yf

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
            log_update(ticker_upper, f"SEC XBRL Extraction skipped (Likely Foreign Issuer).")

        # ==========================================
        # PHASE 2: YAHOO CRUMB BYPASS & FALLBACK
        # ==========================================
        log_update(ticker_upper, "Executing Market Valuation Crumb Handshake...")
        market_cap = None
        pe_ratio = None

        try:
            # --- ATTEMPT 1: The Restored Crumb Bypass ---
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': '*/*'
            })
            
            # Reverted to fc.yahoo.com for guaranteed cookie acquisition
            session.get('https://fc.yahoo.com', timeout=10)
            crumb_response = session.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10)
            crumb = crumb_response.text.strip()
            
            if not crumb or 'html' in crumb:
                raise ValueError("Failed to generate authentication crumb.")

            # 2A. Shallow Quote
            quote_url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker_upper}&crumb={crumb}"
            quote_response = session.get(quote_url, timeout=10)
            
            if quote_response.status_code == 401:
                raise ValueError("Yahoo API returned 401 Unauthorized. Crumb was rejected.")
            
            if quote_response.status_code == 200:
                data = quote_response.json()
                quote_result = data.get("quoteResponse", {}).get("result", [])
                if not quote_result:
                    raise ValueError(f"No market equity data returned for target '{ticker_upper}'")
                
                asset_data = quote_result[0]
                quote_type = asset_data.get("quoteType")
                
                if quote_type not in ["EQUITY", "ADR"]:
                    raise ValueError(f"'{ticker_upper}' is a {quote_type}. Socrates AI requires equities or ADRs.")
                
                market_cap = asset_data.get("marketCap")
                pe_ratio = asset_data.get("trailingPE")
                if eps is None: 
                    eps = asset_data.get("epsTrailingTwelveMonths") or asset_data.get("trailingEps")
            
            # 2B. Deep Financials
            if revenue is None or total_debt is None:
                summary_url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker_upper}?modules=financialData&crumb={crumb}"
                summary_res = session.get(summary_url, timeout=10)
                
                if summary_res.status_code == 200:
                    summary_data = summary_res.json()
                    res_list = summary_data.get("quoteSummary", {}).get("result", [])
                    if res_list:
                        fin_data = res_list[0].get("financialData", {})
                        if revenue is None:
                            rev_val = fin_data.get("totalRevenue", {})
                            revenue = rev_val.get("raw") if isinstance(rev_val, dict) else None
                        if total_debt is None:
                            debt_val = fin_data.get("totalDebt", {})
                            total_debt = debt_val.get("raw") if isinstance(debt_val, dict) else None

            log_update(ticker_upper, "Successfully bypassed security and extracted valuation/fundamentals.")

        except Exception as crumb_err:
            # --- ATTEMPT 2: The YFinance Safety Net ---
            log_update(ticker_upper, f"Crumb Bypass rejected ({str(crumb_err)}). Engaging yfinance safety net... Our boy Yahoo failed us 😭🙏🏻🥀💔")
            try:
                stock = yf.Ticker(ticker_upper)
                info = stock.info
                
                if not info or "marketCap" not in info:
                    raise ValueError("yfinance returned empty payload.")
                    
                quote_type = info.get("quoteType", "EQUITY")
                if quote_type not in ["EQUITY", "ADR"]:
                    raise ValueError(f"'{ticker_upper}' is a {quote_type}. Socrates AI requires equities or ADRs.")
                    
                market_cap = info.get("marketCap")
                pe_ratio = info.get("trailingPE")
                if eps is None: eps = info.get("trailingEps")
                if revenue is None: revenue = info.get("totalRevenue")
                if total_debt is None: total_debt = info.get("totalDebt")
                
                log_update(ticker_upper, "YFinance Fallback Success!")
            except Exception as yf_err:
                raise Exception(f"Valuation Engine Failed Completely. Both Crumb and YFinance blocked: {str(yf_err)} Yfinance Yet again failed us.. 🥀💔")

        if market_cap is None or market_cap == 0:
            raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics.")

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