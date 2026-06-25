import alpaca_trade_api as tradeapi
from app.database import supabase_client
from datetime import datetime
from app.config import settings
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dateutil import parser
import re

class NewsService:
    @staticmethod
    def fetch_and_store_news(ticker: str):
        ticker_upper = ticker.upper()
        ticker_lower = ticker.lower()
        print(f"[{ticker_upper}] Fetching institutional news from Alpaca SDK...")
        
        try:
            # Initialize Alpaca SDK REST Client
            # Base URL doesn't strictly matter for News (it auto-routes to data.alpaca.markets), but we provide the standard.
            nlp_api = tradeapi.REST(
                key_id=settings.alpaca_api_key,
                secret_key=settings.alpaca_secret,
                base_url='https://api.alpaca.markets', 
                api_version='v2'
            )
            
            # 🛡️ DYNAMIC ENTITY GENERATION
            try:
                # Ask Alpaca for the official company name
                asset = nlp_api.get_asset(ticker_upper)
                raw_name = getattr(asset, 'name', '').lower()
                
                # Strip out corporate suffixes (e.g., "Apple Inc." -> "apple", "NVIDIA Corporation" -> "nvidia")
                clean_name = re.sub(r',?\s+(inc\.|inc|corp\.|corp|corporation|llc|plc|ltd\.|ltd|company|co\.|co)\b', '', raw_name).strip()
            except Exception:
                clean_name = ""

            # Build our targeted keyword list
            valid_entities = [ticker_lower]
            if clean_name:
                valid_entities.append(clean_name)
                # Sometimes the brand is best known by its first word (e.g., "Palantir Technologies" -> "palantir")
                first_word = clean_name.split()[0]
                if len(first_word) > 2 and first_word not in valid_entities:
                    valid_entities.append(first_word)
                    
            print(f"[{ticker_upper}] Entity Gate tracking keywords: {valid_entities}")

            # 🛡️ Hard Timeout to prevent Alpaca server hangs
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(nlp_api.get_news, ticker_upper, limit=15)
                live_news = future.result(timeout=10.0)
                
        except TimeoutError:
            print(f"[{ticker_upper}] ⚠️ CRITICAL: Alpaca News API timed out after 10s. Defaulting to empty to maintain flow.")
            return {"status": "success", "articles_inserted": 0, "message": "News API timed out."}
        except Exception as e:
            print(f"[{ticker_upper}] ⚠️ Broker News API offline or failed: {e}")
            return {"status": "error", "message": "Broker API failed."}
            
        if not live_news:
            print(f"[{ticker_upper}] ⚠️ No live news items returned from exchange.")
            return {"status": "success", "articles_inserted": 0, "message": "No news available."}
            
        print(f"[{ticker_upper}] Successfully pulled {len(live_news)} Benzinga articles. Formatting...")
        
        payloads = []
        for item in live_news:
            # Alpaca SDK returns Entity objects, so we use getattr
            headline = getattr(item, 'headline', '')
            summary = getattr(item, 'summary', '')
            url = getattr(item, 'url', '')
            
            if not url or not headline:
                continue
                
            full_text = f"{headline}. {summary}".lower()
            
            # 🛡️ THE DYNAMIC ENTITY GATE
            # If NONE of our targeted keywords appear in the headline or summary, we drop the article
            if not any(entity in full_text for entity in valid_entities):
                print(f"[{ticker_upper}] Dropped syndicated noise: {headline}")
                continue
                
            created_at_raw = getattr(item, 'created_at', None)
            if hasattr(created_at_raw, 'isoformat'):
                pub_time_str = created_at_raw.isoformat()
            elif isinstance(created_at_raw, str):
                try:
                    pub_time_str = parser.isoparse(created_at_raw).isoformat()
                except Exception:
                    try:
                        pub_time_str = parser.parse(created_at_raw).isoformat()
                    except Exception:
                        pub_time_str = datetime.utcnow().isoformat()
            else:
                pub_time_str = str(created_at_raw) if created_at_raw else datetime.utcnow().isoformat()
            
            payloads.append({
                "ticker": ticker_upper,
                "title": headline,
                "summary": summary, 
                "url": url,
                "published_at": pub_time_str,
                "created_at": datetime.utcnow().isoformat()
            })
            
        if not payloads:
            print(f"[{ticker_upper}] No valid, entity-specific URLs found after filtering.")
            return {"status": "success", "articles_inserted": 0, "message": "No valid entity-specific URLs."}
            
        try:
            response = supabase_client.table("soc_news_articles").upsert(
                payloads, on_conflict="url"
            ).execute()
            print(f"[{ticker_upper}] {len(payloads)} Filtered Alpaca News injected to Supabase successfully! Response: {response}")
            return {"status": "success", "articles_inserted": len(payloads)}
        except Exception as e:
            print(f"[{ticker_upper}] Supabase Database Error: {str(e)}")
            return {"status": "error", "message": "Failed to save news to DB."}