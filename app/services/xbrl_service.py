import requests
import math
import yfinance as yf
from app.database import supabase_client
from datetime import datetime
from app.status_store import log_update
from app.config import settings

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
        # Supports both US Domestic (us-gaap) and International ADRs like INFY (ifrs-full)
        accounting_standards = ['us-gaap', 'ifrs-full']
        
        for standard in accounting_standards:
            taxonomy = company_facts.get('facts', {}).get(standard, {})
            if not taxonomy:
                continue
                
            for tag in possible_tags:
                if tag in taxonomy:
                    units = taxonomy[tag].get('units', {})
                    if not units:
                        continue
                    val_key = 'USD' if 'USD' in units else list(units.keys())[0]
                    
                    observations = units[val_key]
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
        # PHASE 2: REAL-TIME VALUATION (AUTHENTICATED ONLY)
        # ==========================================
        log_update(ticker_upper, "Fetching live market data...")
        market_cap = None
        pe_ratio = None
        current_price = None

        # --- LAYER A: FMP PROFILE ENDPOINT ---
        try:
            fmp_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker_upper}?apikey={settings.fmp_api_key}"
            res = requests.get(fmp_url, timeout=5)
            if res.status_code == 200:
                data_list = res.json()
                if not data_list:
                    # 🛡️ FAIL FAST: FMP confirms this ticker does not exist. Halt cascade.
                    raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by FMP.")
                if data_list:
                    current_price = data_list[0].get('price')
                    market_cap = data_list[0].get('mktCap')
                    pe_ratio = data_list[0].get('pe')
                    log_update(ticker_upper, "Successfully extracted valuation from FMP Profile.")
            else:
                log_update(ticker_upper, f"FMP Profile unavailable: Status {res.status_code}")
        except ValueError as ve:
            raise ve # Pass the fail-fast exception up!
        except Exception as e:
            log_update(ticker_upper, f"FMP Engine exception: {e}")

        # --- LAYER B: FINNHUB AUTHENTICATED FALLBACK ---
        if market_cap is None or current_price is None:
            log_update(ticker_upper, "FMP unavailable. Switching to Finnhub Authenticated Gateway...")
            try:
                if current_price is None:
                    quote_res = requests.get(f"https://finnhub.io/api/v1/quote?symbol={ticker_upper}&token={settings.finnhub_api_key}", timeout=5)
                    if quote_res.status_code == 200:
                        q_data = quote_res.json()
                        # 🛡️ FAIL FAST: Finnhub returns c=0 for completely fake tickers
                        if q_data.get('c') == 0 and q_data.get('d') is None:
                            raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by Finnhub.")
                        if q_data.get('c') is not None:
                            current_price = float(q_data['c'])
                
                if market_cap is None:
                    profile_res = requests.get(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker_upper}&token={settings.finnhub_api_key}", timeout=5)
                    if profile_res.status_code == 200:
                        p_data = profile_res.json()
                        if p_data.get('marketCapitalization'):
                            market_cap = float(p_data['marketCapitalization']) * 1_000_000
                
                if pe_ratio is None:
                    metric_res = requests.get(f"https://finnhub.io/api/v1/stock/metric?symbol={ticker_upper}&metric=all&token={settings.finnhub_api_key}", timeout=5)
                    if metric_res.status_code == 200:
                        m_data = metric_res.json()
                        pe_ratio = m_data.get('metric', {}).get('peTTM')

                log_update(ticker_upper, f"Finnhub Pass Complete. PE acquired: {pe_ratio is not None}")
            except ValueError as ve:
                raise ve # Pass the fail-fast exception up!
            except Exception as e:
                log_update(ticker_upper, f"Finnhub fallback exception: {e}")

        # --- LAYER C: POLYGON.IO EMERGENCY AUTHENTICATED FALLBACK ---
        if market_cap is None or current_price is None or pe_ratio is None:
            if settings.polygon_api_key:
                log_update(ticker_upper, "Cascading to Polygon.io Emergency Gateway...")
                try:
                    if current_price is None:
                        poly_url = f"https://api.polygon.io/v2/aggs/ticker/{ticker_upper}/prev?adjusted=true&apiKey={settings.polygon_api_key}"
                        poly_res = requests.get(poly_url, timeout=5)
                        if poly_res.status_code == 200:
                            p_json = poly_res.json()
                            # 🛡️ FAIL FAST: Polygon confirms ticker doesn't exist
                            if p_json.get('resultsCount', 0) == 0:
                                raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by Polygon.")
                            results = p_json.get('results', [])
                            if results:
                                current_price = float(results[0].get('c'))
                    
                    ticker_url = f"https://api.polygon.io/v3/reference/tickers/{ticker_upper}?apiKey={settings.polygon_api_key}"
                    t_res = requests.get(ticker_url, timeout=5)
                    if t_res.status_code == 200:
                        t_data = t_res.json().get('results', {})
                        if market_cap is None:
                            val = t_data.get('market_cap')
                            if val:
                                market_cap = val
                                log_update(ticker_upper, "Successfully extracted market cap from Polygon.")
                    
                    if pe_ratio is None:
                        # Snapshot endpoint requires a higher Polygon subscription.
                        # Skip PE extraction from Polygon on the current plan.
                        pass
                except ValueError as ve:
                    raise ve # Pass the fail-fast exception up!
                except Exception as e:
                    log_update(ticker_upper, f"Polygon emergency fallback failed: {e}")

        # --- LAYER D: YFINANCE UNIVERSAL FETCH ---
        if market_cap is None or current_price is None or pe_ratio is None:
            log_update(ticker_upper, "Attempting YFinance universal fetch...")
            try:
                stock = yf.Ticker(ticker_upper)
                info = stock.info
                
                if current_price is None:
                    current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                if market_cap is None:
                    market_cap = info.get('marketCap') or stock.fast_info.market_cap
                if pe_ratio is None:
                    pe_ratio = info.get('trailingPE')

                if current_price and market_cap:
                    log_update(ticker_upper, "YFinance fetch successful: Price and Market Cap retrieved.")
                elif current_price:
                    log_update(ticker_upper, "YFinance fetch partial: Only Price retrieved.")
                else:
                    log_update(ticker_upper, "YFinance fetch failed: No essential data found.")
            except Exception as e:
                err_msg = str(e)
                if "Expecting value" in err_msg or "line 1 column 1" in err_msg or "404" in err_msg:
                    # 🛡️ FAIL FAST: YFinance doesn't know it either
                    raise ValueError(f"Target '{ticker_upper}' rejected by YFinance. Definitively invalid.")
                else:
                    log_update(ticker_upper, f"YFinance minor error: {err_msg}. Proceeding to Layer E...")

        # --- LAYER E: MATH DERIVATION FALLBACK ---
        if pe_ratio is None and current_price and eps:
            eps_float = float(eps)
            if eps_float > 0:
                pe_ratio = current_price / eps_float
                log_update(ticker_upper, f"Calculated positive P/E ratio mathematically (Warning: Check if quarterly or TTM): {pe_ratio:.2f}")
            elif eps_float < 0:
                log_update(ticker_upper, f"Skipped P/E calculation: Company is unprofitable (Negative EPS: {eps_float}).")
            else:
                log_update(ticker_upper, "Skipped P/E calculation: EPS is exactly zero.")

        # Final Hard Validation
        if market_cap is None or (isinstance(market_cap, float) and math.isnan(market_cap)):
            raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics after all authenticated fallbacks.")
        
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