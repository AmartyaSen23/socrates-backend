import re
import requests
import alpaca_trade_api as tradeapi
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dateutil import parser
from typing import List, Dict, Any
from app.database import supabase_client
from app.config import settings
from app.status_store import log_update


class NewsService:
    @staticmethod
    def _build_entity_patterns(ticker_upper: str, raw_company_name: str = "") -> List[re.Pattern]:
        """
        Builds compiled regex patterns for the Dynamic Entity Gate.
        Uses word-boundary matching so short tickers (e.g. 'F', 'T', 'C', 'AI') don't match
        unrelated words, and properly strips corporate & share-class suffixes.
        """
        patterns: List[re.Pattern] = [
            re.compile(rf"(?<![a-z0-9])\$?{re.escape(ticker_upper.lower())}(?![a-z0-9])", re.IGNORECASE)
        ]

        if raw_company_name:
            clean = raw_company_name.lower()
            # Strip parentheticals e.g. "(The)" or "(DE)"
            clean = re.sub(r"\([^)]*\)", " ", clean)
            # Strip share class / ADR descriptors
            clean = re.sub(
                r"\b(class\s+[a-z]|series\s+[a-z]|common\s+stock|ordinary\s+shares|"
                r"american\s+depositary\s+shares|american\s+depositary\s+receipts|"
                r"sponsored\s+adr|unsponsored\s+adr|adr|ads|shares)\b.*",
                "",
                clean,
            )
            # Strip trailing corporate suffixes (with or without trailing period)
            clean = re.sub(
                r"[\s,]+(inc\.?|incorporated|corp\.?|corporation|llc|plc|ltd\.?|limited|"
                r"company|co\.?|holdings?|group|n\.?v\.?|s\.?a\.?|ag|se|lp|l\.?p\.?)\s*$",
                "",
                clean,
            ).strip(" ,.-")
            # Run suffix strip a second time in case of stacked suffixes like "Co., Ltd."
            clean = re.sub(
                r"[\s,]+(inc\.?|incorporated|corp\.?|corporation|llc|plc|ltd\.?|limited|"
                r"company|co\.?|holdings?|group)\s*$",
                "",
                clean,
            ).strip(" ,.-")

            if len(clean) >= 2:
                patterns.append(re.compile(rf"\b{re.escape(clean)}\b", re.IGNORECASE))
                first_word = clean.split()[0]
                # Avoid generic first words like "the", "first", "general", "american", "united"
                generic_words = {
                    "the", "first", "general", "american", "united", "national",
                    "international", "global", "standard", "pacific", "atlantic",
                }
                if len(first_word) > 2 and first_word not in generic_words:
                    patterns.append(re.compile(rf"\b{re.escape(first_word)}\b", re.IGNORECASE))

        return patterns

    @staticmethod
    def _matches_entity_gate(headline: str, summary: str, symbols: List[str], patterns: List[re.Pattern], ticker_upper: str) -> bool:
        full_text = f"{headline}. {summary}"
        upper_symbols = [s.upper() for s in symbols if isinstance(s, str)]
        # If the article is exclusively tagged for this single ticker, accept it unless it's a generic market roundup
        if len(upper_symbols) == 1 and upper_symbols[0] == ticker_upper:
            return True
        # If syndicated across many tickers (>4), require the entity to appear in the headline itself
        if len(upper_symbols) > 4:
            return any(p.search(headline) for p in patterns)
        return any(p.search(full_text) for p in patterns)

    @staticmethod
    def _normalize_timestamp(raw_ts: Any) -> str:
        if hasattr(raw_ts, "isoformat"):
            return raw_ts.isoformat()
        if isinstance(raw_ts, (int, float)):
            try:
                return datetime.fromtimestamp(raw_ts, tz=timezone.utc).isoformat()
            except Exception:
                return datetime.now(timezone.utc).isoformat()
        if isinstance(raw_ts, str) and raw_ts.strip():
            try:
                return parser.isoparse(raw_ts).isoformat()
            except Exception:
                try:
                    return parser.parse(raw_ts).isoformat()
                except Exception:
                    return datetime.now(timezone.utc).isoformat()
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def fetch_and_store_news(ticker: str, force: bool = False):
        ticker_upper = ticker.strip().upper()

        # Check if fresh news was already ingested for this ticker within the last 30 minutes
        if not force:
            try:
                cutoff_iso = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
                recent_check = (
                    supabase_client.table("soc_news_articles")
                    .select("url")
                    .eq("ticker", ticker_upper)
                    .gte("created_at", cutoff_iso)
                    .limit(1)
                    .execute()
                )
                if recent_check.data:
                    log_update(ticker_upper, "Recent institutional news exists in cache. Skipping external News API.")
                    return {"status": "cached", "articles_inserted": 0}
            except Exception:
                pass

        print(f"[{ticker_upper}] Fetching institutional news...")

        raw_company_name = ""
        payloads: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        # ==========================================
        # LAYER 1: ALPACA BENZINGA INSTITUTIONAL SDK
        # ==========================================
        if settings.alpaca_api_key and settings.alpaca_secret:
            executor = ThreadPoolExecutor(max_workers=1)
            try:
                nlp_api = tradeapi.REST(
                    key_id=settings.alpaca_api_key,
                    secret_key=settings.alpaca_secret,
                    base_url="https://api.alpaca.markets",
                    api_version="v2",
                )

                try:
                    asset_future = executor.submit(nlp_api.get_asset, ticker_upper)
                    asset = asset_future.result(timeout=4.0)
                    raw_company_name = getattr(asset, "name", "") or ""
                except Exception:
                    raw_company_name = ""

                patterns = NewsService._build_entity_patterns(ticker_upper, raw_company_name)

                future = executor.submit(nlp_api.get_news, ticker_upper, limit=15)
                live_news = future.result(timeout=10.0)

                if live_news:
                    print(f"[{ticker_upper}] Pulled {len(live_news)} Alpaca/Benzinga articles. Filtering...")
                    for item in live_news:
                        headline = (getattr(item, "headline", "") or "").strip()
                        summary = (getattr(item, "summary", "") or "").strip()
                        url = (getattr(item, "url", "") or "").strip()
                        symbols = getattr(item, "symbols", []) or []

                        if not url or not headline:
                            continue

                        if not NewsService._matches_entity_gate(headline, summary, symbols, patterns, ticker_upper):
                            print(f"[{ticker_upper}] Dropped syndicated noise: {headline}")
                            continue

                        pub_time_str = NewsService._normalize_timestamp(getattr(item, "created_at", None))
                        payloads.append({
                            "ticker": ticker_upper,
                            "title": headline,
                            "summary": summary or headline,
                            "url": url,
                            "published_at": pub_time_str,
                            "created_at": now_iso,
                        })
            except TimeoutError:
                print(f"[{ticker_upper}] ⚠️ Alpaca News API timed out after 10s. Cascading to fallback news gateway...")
            except Exception as e:
                print(f"[{ticker_upper}] ⚠️ Alpaca News API error ({e}). Cascading to fallback news gateway...")
            finally:
                # Non-blocking shutdown prevents hanging thread from blocking caller on TimeoutError
                executor.shutdown(wait=False, cancel_futures=True)

        # ==========================================
        # LAYER 2: FINNHUB COMPANY NEWS FALLBACK
        # ==========================================
        if not payloads and settings.finnhub_api_key:
            try:
                print(f"[{ticker_upper}] Fetching fallback institutional news from Finnhub...")
                today_dt = datetime.now(timezone.utc)
                from_dt = today_dt - timedelta(days=30)
                fh_headers = {"X-Finnhub-Token": settings.finnhub_api_key}

                if not raw_company_name:
                    try:
                        prof_res = requests.get(
                            "https://finnhub.io/api/v1/stock/profile2",
                            params={"symbol": ticker_upper},
                            headers=fh_headers,
                            timeout=4,
                        )
                        if prof_res.status_code == 200:
                            raw_company_name = prof_res.json().get("name", "") or ""
                    except Exception:
                        pass

                patterns = NewsService._build_entity_patterns(ticker_upper, raw_company_name)

                fh_res = requests.get(
                    "https://finnhub.io/api/v1/company-news",
                    params={
                        "symbol": ticker_upper,
                        "from": from_dt.strftime("%Y-%m-%d"),
                        "to": today_dt.strftime("%Y-%m-%d"),
                    },
                    headers=fh_headers,
                    timeout=6,
                )
                if fh_res.status_code == 200 and isinstance(fh_res.json(), list):
                    for item in fh_res.json()[:20]:
                        headline = (item.get("headline") or "").strip()
                        summary = (item.get("summary") or "").strip()
                        url = (item.get("url") or "").strip()
                        related = [s.strip() for s in (item.get("related") or "").split(",") if s.strip()]

                        if not url or not headline:
                            continue
                        if not NewsService._matches_entity_gate(headline, summary, related, patterns, ticker_upper):
                            continue

                        pub_time_str = NewsService._normalize_timestamp(item.get("datetime"))
                        payloads.append({
                            "ticker": ticker_upper,
                            "title": headline,
                            "summary": summary or headline,
                            "url": url,
                            "published_at": pub_time_str,
                            "created_at": now_iso,
                        })
                        if len(payloads) >= 15:
                            break
            except Exception as e:
                print(f"[{ticker_upper}] Finnhub News fallback error: {e}")

        # ==========================================
        # LAYER 3: POLYGON REFERENCE NEWS FALLBACK
        # ==========================================
        if not payloads and settings.polygon_api_key:
            try:
                print(f"[{ticker_upper}] Fetching fallback news from Polygon.io...")
                patterns = NewsService._build_entity_patterns(ticker_upper, raw_company_name)
                poly_res = requests.get(
                    "https://api.polygon.io/v2/reference/news",
                    params={"ticker": ticker_upper, "limit": 15, "apiKey": settings.polygon_api_key},
                    timeout=6,
                )
                if poly_res.status_code == 200:
                    results = poly_res.json().get("results", []) or []
                    for item in results:
                        headline = (item.get("title") or "").strip()
                        summary = (item.get("description") or "").strip()
                        url = (item.get("article_url") or "").strip()
                        tickers_list = item.get("tickers") or []

                        if not url or not headline:
                            continue
                        if not NewsService._matches_entity_gate(headline, summary, tickers_list, patterns, ticker_upper):
                            continue

                        pub_time_str = NewsService._normalize_timestamp(item.get("published_utc"))
                        payloads.append({
                            "ticker": ticker_upper,
                            "title": headline,
                            "summary": summary or headline,
                            "url": url,
                            "published_at": pub_time_str,
                            "created_at": now_iso,
                        })
            except Exception as e:
                print(f"[{ticker_upper}] Polygon News fallback error: {e}")

        # Deduplicate payloads by URL before upserting to prevent Postgres ON CONFLICT batch error
        deduped_map: Dict[str, Dict[str, Any]] = {}
        for p in payloads:
            deduped_map[p["url"]] = p
        final_payloads = list(deduped_map.values())

        if not final_payloads:
            print(f"[{ticker_upper}] No valid, entity-specific news articles found across providers.")
            return {"status": "success", "articles_inserted": 0, "message": "No valid entity-specific URLs."}

        try:
            supabase_client.table("soc_news_articles").upsert(
                final_payloads, on_conflict="url"
            ).execute()
            log_update(ticker_upper, f"Ingested {len(final_payloads)} verified institutional news articles.")
            return {"status": "success", "articles_inserted": len(final_payloads)}
        except Exception as e:
            print(f"[{ticker_upper}] Supabase Database Error: {str(e)}")
            return {"status": "error", "message": "Failed to save news to DB."}