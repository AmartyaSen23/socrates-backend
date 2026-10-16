import math
import time
import threading
import requests
import yfinance as yf
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.database import supabase_client
from app.status_store import log_update
from app.config import settings


class XBRLService:
    # Official SEC User-Agent requirement
    SEC_HEADERS = {"User-Agent": "SocratesResearchEngine amartya@socrates-ai.com"}

    # In-memory cache for SEC CIK ticker mapping (avoids downloading 1.5MB JSON on every request)
    _cik_cache: Dict[str, str] = {}
    _cik_cache_timestamp: float = 0.0
    _cik_cache_ttl: float = 86400.0  # 24 hours
    _cik_lock = threading.Lock()

    @staticmethod
    def _ensure_cik_cache() -> Dict[str, str]:
        now = time.time()
        with XBRLService._cik_lock:
            if XBRLService._cik_cache and (now - XBRLService._cik_cache_timestamp) < XBRLService._cik_cache_ttl:
                return XBRLService._cik_cache

            url = "https://www.sec.gov/files/company_tickers.json"
            response = requests.get(url, headers=XBRLService.SEC_HEADERS, timeout=10)
            if response.status_code != 200:
                raise ValueError(f"Failed to fetch SEC CIK mapping (HTTP {response.status_code}).")

            data = response.json()
            mapping: Dict[str, str] = {}
            for _, company in data.items():
                t = str(company.get("ticker", "")).upper().strip()
                cik_str = str(company.get("cik_str", "")).zfill(10)
                if t and cik_str:
                    mapping[t] = cik_str
                    # Support both BRK-B and BRK.B conventions seamlessly
                    mapping[t.replace("-", ".")] = cik_str
                    mapping[t.replace(".", "-")] = cik_str

            XBRLService._cik_cache = mapping
            XBRLService._cik_cache_timestamp = now
            return XBRLService._cik_cache

    @staticmethod
    def get_cik_from_ticker(ticker: str) -> str:
        ticker_clean = ticker.strip().upper()
        mapping = XBRLService._ensure_cik_cache()
        cik = mapping.get(ticker_clean)
        if cik:
            return cik
        raise ValueError(f"Ticker '{ticker_clean}' not found in SEC EDGAR database.")

    @staticmethod
    def extract_latest_fact(
        company_facts: dict,
        possible_tags: List[str],
        require_annual_period: bool = False,
    ) -> Optional[float]:
        """
        Extracts the most recent audited metric across US-GAAP and IFRS taxonomies.
        Evaluates all candidate tags and selects the observation with the newest period end date
        to avoid returning stale data from deprecated XBRL tags.
        """
        accounting_standards = ["us-gaap", "ifrs-full"]
        preferred_units = ["USD", "USD/shares", "pure"]

        candidates: List[Dict[str, Any]] = []

        for standard in accounting_standards:
            taxonomy = company_facts.get("facts", {}).get(standard, {})
            if not taxonomy:
                continue

            for priority_idx, tag in enumerate(possible_tags):
                if tag not in taxonomy:
                    continue

                units = taxonomy[tag].get("units", {})
                if not units:
                    continue

                # Strictly require USD or USD/shares (or dimensionless 'pure') so foreign currencies (INR, TWD, JPY, EUR)
                # are never misinterpreted as USD in downstream valuation and LLM analysis.
                val_key = None
                for pref in preferred_units:
                    if pref in units:
                        val_key = pref
                        break
                if val_key is None:
                    continue

                observations = units.get(val_key, [])
                for obs in observations:
                    if "val" not in obs or obs["val"] is None or "filed" not in obs:
                        continue

                    end_date = obs.get("end", "")
                    start_date = obs.get("start", "")
                    form = obs.get("form", "")
                    fp = obs.get("fp", "")

                    # Determine if this observation represents a full fiscal year (~330-385 days)
                    is_annual = False
                    if start_date and end_date:
                        try:
                            d_start = datetime.strptime(start_date, "%Y-%m-%d")
                            d_end = datetime.strptime(end_date, "%Y-%m-%d")
                            days = (d_end - d_start).days
                            if 330 <= days <= 385:
                                is_annual = True
                        except Exception:
                            pass
                    elif form in ("10-K", "20-F", "40-F", "10-K/A", "20-F/A") or fp == "FY":
                        is_annual = True

                    candidates.append({
                        "val": float(obs["val"]),
                        "end": end_date,
                        "filed": obs.get("filed", ""),
                        "is_annual": is_annual,
                        "priority": -priority_idx,
                    })

        if not candidates:
            return None

        pool = candidates
        if require_annual_period:
            annual_pool = [c for c in pool if c["is_annual"]]
            if annual_pool:
                pool = annual_pool

        # Sort by latest period end date first, then filing date, then tag priority
        best = max(pool, key=lambda c: (c["end"], c["filed"], c["priority"]))
        return best["val"]

    @staticmethod
    def fetch_and_store_fundamentals(ticker: str):
        ticker_upper = ticker.strip().upper()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # 1. CHECK DATABASE CACHE
        try:
            cached_data = (
                supabase_client.table("soc_company_fundamentals")
                .select("*")
                .eq("ticker", ticker_upper)
                .eq("fiscal_date", today)
                .execute()
            )

            if cached_data.data:
                log_update(ticker_upper, "Fundamentals exist in cache. Skipping API.")
                return cached_data.data
        except Exception as e:
            print(f"Cache check failed: {e}")

        # ==========================================
        # PHASE 1: SEC EDGAR XBRL (The Official Way)
        # ==========================================
        log_update(ticker_upper, "Fetching audited accounting metrics from SEC EDGAR XBRL...")
        revenue: Optional[float] = None
        eps: Optional[float] = None
        total_debt: Optional[float] = None
        is_verified_sec_entity = False

        try:
            cik = XBRLService.get_cik_from_ticker(ticker_upper)
            is_verified_sec_entity = True
            facts_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
            facts_res = requests.get(facts_url, headers=XBRLService.SEC_HEADERS, timeout=10)

            if facts_res.status_code == 200:
                facts_data = facts_res.json()
                revenue = XBRLService.extract_latest_fact(
                    facts_data,
                    [
                        "RevenueFromContractWithCustomerExcludingAssessedTax",
                        "RevenueFromContractWithCustomerIncludingAssessedTax",
                        "Revenues",
                        "SalesRevenueNet",
                        "SalesRevenueGoodsNet",
                        "SalesRevenueServicesNet",
                        "RevenuesNetOfInterestExpense",
                        "TotalRevenuesAndOtherIncome",
                        "Revenue",  # IFRS standard tag
                    ],
                    require_annual_period=True,
                )
                eps = XBRLService.extract_latest_fact(
                    facts_data,
                    [
                        "EarningsPerShareDiluted",
                        "EarningsPerShareBasic",
                        "IncomeLossFromContinuingOperationsPerDilutedShare",
                        "DilutedEarningsLossPerShare",  # IFRS
                        "BasicEarningsLossPerShare",    # IFRS
                        "BasicAndDilutedEarningsLossPerShare",
                    ],
                    require_annual_period=True,
                )
                total_debt = XBRLService.extract_latest_fact(
                    facts_data,
                    [
                        "LongTermDebtAndCapitalLeaseObligations",
                        "DebtAndCapitalLeaseObligations",
                        "LongTermDebt",
                        "LongTermDebtNoncurrent",
                        "DebtCurrent",
                        "ShortTermBorrowings",
                        "Borrowings",  # IFRS
                        "NoncurrentPortionOfNoncurrentBorrowings",  # IFRS
                    ],
                    require_annual_period=False,
                )
                log_update(ticker_upper, "SEC XBRL Extraction Success.")
            else:
                log_update(ticker_upper, f"Warning: SEC XBRL returned status {facts_res.status_code}.")
        except Exception:
            log_update(ticker_upper, "SEC XBRL Extraction skipped (Not in SEC CIK index or Foreign ADR).")

        # ==========================================
        # PHASE 2: REAL-TIME VALUATION (AUTHENTICATED CASCADE)
        # ==========================================
        log_update(ticker_upper, "Fetching live market data...")
        market_cap: Optional[float] = None
        pe_ratio: Optional[float] = None
        current_price: Optional[float] = None

        # --- LAYER A: FMP PROFILE ENDPOINT ---
        if settings.fmp_api_key:
            try:
                fmp_url = f"https://financialmodelingprep.com/api/v3/profile/{ticker_upper}"
                res = requests.get(fmp_url, params={"apikey": settings.fmp_api_key}, timeout=5)
                if res.status_code in (403, 401):
                    # Try FMP stable endpoint for newer API keys / ADR tiers
                    stable_url = "https://financialmodelingprep.com/stable/profile"
                    res = requests.get(
                        stable_url,
                        params={"symbol": ticker_upper, "apikey": settings.fmp_api_key},
                        timeout=5,
                    )
                if res.status_code == 200:
                    data_list = res.json()
                    if isinstance(data_list, list):
                        if len(data_list) == 0:
                            if not is_verified_sec_entity:
                                # Fail fast only if also unverified by SEC EDGAR
                                raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by FMP.")
                            log_update(ticker_upper, "FMP returned empty profile for SEC-verified ticker. Cascading...")
                        else:
                            profile_obj = data_list[0]
                            current_price = profile_obj.get("price")
                            market_cap = profile_obj.get("mktCap") or profile_obj.get("marketCap")
                            pe_ratio = profile_obj.get("pe")
                            log_update(ticker_upper, "Successfully extracted valuation from FMP Profile.")
                    else:
                        log_update(ticker_upper, "FMP quota or endpoint restriction encountered. Cascading...")
                else:
                    log_update(ticker_upper, "Primary FMP tier restricted for asset. Routing to Finnhub Gateway...")
            except ValueError as ve:
                raise ve
            except Exception:
                log_update(ticker_upper, "FMP Engine network timeout or error. Cascading...")

        # --- LAYER B: FINNHUB AUTHENTICATED FALLBACK ---
        if (market_cap is None or current_price is None or pe_ratio is None or eps is None) and settings.finnhub_api_key:
            log_update(ticker_upper, "Querying Finnhub Authenticated Gateway...")
            try:
                fh_headers = {"X-Finnhub-Token": settings.finnhub_api_key}
                if current_price is None:
                    quote_res = requests.get(
                        "https://finnhub.io/api/v1/quote",
                        params={"symbol": ticker_upper},
                        headers=fh_headers,
                        timeout=5,
                    )
                    if quote_res.status_code == 200:
                        q_data = quote_res.json()
                        # Fail fast: Finnhub returns c=0 and d=None for completely nonexistent tickers
                        if q_data.get("c") == 0 and q_data.get("d") is None and not is_verified_sec_entity:
                            raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by Finnhub.")
                        if q_data.get("c"):
                            current_price = float(q_data["c"])

                if market_cap is None:
                    profile_res = requests.get(
                        "https://finnhub.io/api/v1/stock/profile2",
                        params={"symbol": ticker_upper},
                        headers=fh_headers,
                        timeout=5,
                    )
                    if profile_res.status_code == 200:
                        p_data = profile_res.json()
                        if p_data.get("marketCapitalization"):
                            market_cap = float(p_data["marketCapitalization"]) * 1_000_000

                if pe_ratio is None or eps is None or revenue is None:
                    metric_res = requests.get(
                        "https://finnhub.io/api/v1/stock/metric",
                        params={"symbol": ticker_upper, "metric": "all"},
                        headers=fh_headers,
                        timeout=5,
                    )
                    if metric_res.status_code == 200:
                        metrics = metric_res.json().get("metric", {}) or {}
                        if pe_ratio is None and metrics.get("peTTM") is not None:
                            pe_ratio = float(metrics["peTTM"])
                        if eps is None:
                            fh_eps = metrics.get("epsTTM") or metrics.get("epsBasicExclExtraItemsTTM") or metrics.get("epsNormalizedAnnual")
                            if fh_eps is not None:
                                eps = float(fh_eps)

                log_update(ticker_upper, f"Finnhub Pass Complete. PE acquired: {pe_ratio is not None}")
            except ValueError as ve:
                raise ve
            except Exception:
                log_update(ticker_upper, "Finnhub fallback encountered a network error.")

        # --- LAYER C: POLYGON.IO EMERGENCY AUTHENTICATED FALLBACK ---
        if (market_cap is None or current_price is None) and settings.polygon_api_key:
            log_update(ticker_upper, "Cascading to Polygon.io Emergency Gateway...")
            try:
                if current_price is None:
                    poly_url = f"https://api.polygon.io/v2/aggs/ticker/{ticker_upper}/prev"
                    poly_res = requests.get(
                        poly_url,
                        params={"adjusted": "true", "apiKey": settings.polygon_api_key},
                        timeout=5,
                    )
                    if poly_res.status_code == 200:
                        p_json = poly_res.json()
                        if p_json.get("resultsCount", 0) == 0 and not is_verified_sec_entity:
                            raise ValueError(f"Target '{ticker_upper}' explicitly rejected as invalid by Polygon.")
                        results = p_json.get("results", [])
                        if results and results[0].get("c") is not None:
                            current_price = float(results[0]["c"])

                if market_cap is None:
                    ticker_url = f"https://api.polygon.io/v3/reference/tickers/{ticker_upper}"
                    t_res = requests.get(
                        ticker_url,
                        params={"apiKey": settings.polygon_api_key},
                        timeout=5,
                    )
                    if t_res.status_code == 200:
                        t_data = t_res.json().get("results", {})
                        val = t_data.get("market_cap")
                        if val:
                            market_cap = float(val)
                            log_update(ticker_upper, "Successfully extracted market cap from Polygon.")
            except ValueError as ve:
                raise ve
            except Exception:
                log_update(ticker_upper, "Polygon emergency fallback failed.")

        # --- LAYER D: YFINANCE UNIVERSAL FETCH (ONLY IF ESSENTIAL DATA IS MISSING) ---
        if market_cap is None or current_price is None:
            log_update(ticker_upper, "Attempting YFinance fast fetch...")
            try:
                stock = yf.Ticker(ticker_upper)
                fast_info = getattr(stock, "fast_info", None)
                if fast_info is not None:
                    if current_price is None:
                        current_price = getattr(fast_info, "last_price", None) or getattr(
                            fast_info, "regular_market_previous_close", None
                        )
                    if market_cap is None:
                        market_cap = getattr(fast_info, "market_cap", None)

                if current_price and market_cap:
                    log_update(ticker_upper, "YFinance fetch successful: Price and Market Cap retrieved.")
                elif current_price:
                    log_update(ticker_upper, "YFinance fetch partial: Only Price retrieved.")
                else:
                    log_update(ticker_upper, "YFinance fetch failed: No essential data found.")
            except Exception:
                log_update(ticker_upper, "YFinance skipped. Moving to mathematical derivation...")

        # --- LAYER E: MATH DERIVATION FALLBACK ---
        if pe_ratio is None and current_price is not None and eps is not None:
            try:
                eps_float = float(eps)
                if eps_float > 0:
                    pe_ratio = float(current_price) / eps_float
                    log_update(ticker_upper, f"Calculated positive P/E ratio mathematically: {pe_ratio:.2f}")
                elif eps_float < 0:
                    log_update(ticker_upper, f"Skipped P/E calculation: Company is unprofitable (Negative EPS: {eps_float}).")
                else:
                    log_update(ticker_upper, "Skipped P/E calculation: EPS is exactly zero.")
            except (ValueError, TypeError):
                pass

        # Final Hard Validation
        if market_cap is None or (isinstance(market_cap, float) and (math.isnan(market_cap) or math.isinf(market_cap))) or market_cap <= 0:
            raise ValueError(f"Target '{ticker_upper}' lacks structural market valuation metrics after all authenticated fallbacks.")

        # ==========================================
        # PHASE 3: SAFE TYPE CASTING & SUPABASE INJECT
        # ==========================================
        def safe_int(val) -> Optional[int]:
            if val is None:
                return None
            try:
                f_val = float(val)
                if math.isnan(f_val) or math.isinf(f_val):
                    return None
                return int(round(f_val))
            except (ValueError, TypeError):
                return None

        def safe_float(val) -> Optional[float]:
            if val is None:
                return None
            try:
                f_val = float(val)
                if math.isnan(f_val) or math.isinf(f_val):
                    return None
                return round(f_val, 4)
            except (ValueError, TypeError):
                return None

        payload = {
            "ticker": ticker_upper,
            "revenue": safe_int(revenue),
            "eps": safe_float(eps),
            "pe_ratio": safe_float(pe_ratio),
            "market_cap": safe_int(market_cap),
            "total_debt": safe_int(total_debt),
            "fiscal_date": today,
        }

        try:
            db_response = (
                supabase_client.table("soc_company_fundamentals")
                .upsert(payload, on_conflict="ticker,fiscal_date")
                .execute()
            )
            return db_response.data
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")