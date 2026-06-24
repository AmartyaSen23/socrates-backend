import yfinance as yf
from app.database import supabase_client
from datetime import datetime
import requests

class NewsService:
    @staticmethod
    def fetch_and_store_news(ticker: str):
        ticker = ticker.upper()
        print(f"Fetching news for {ticker} from Yahoo Finance...")
        
        news = []
        
        # ATTEMPT 1: Standard YFinance (Fastest if it works)
        try:
            stock = yf.Ticker(ticker)
            news = stock.news
        except Exception as e:
            print(f"YFinance News API Error: {str(e)}")

        # ATTEMPT 2: THE AGGRESSIVE CRUMB BYPASS (No Cowardice allowed)
        if not news:
            print(f"[{ticker}] Standard news blocked. Initiating Aggressive Crumb Handshake...")
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Connection': 'keep-alive'
            })
            
            try:
                # Step A: Hit the front page to grab a session cookie
                session.get('https://fc.yahoo.com', timeout=10)
                
                # Step B: Request the cryptographic crumb
                crumb_response = session.get('https://query1.finance.yahoo.com/v1/test/getcrumb', timeout=10)
                crumb = crumb_response.text
                
                if crumb and 'html' not in crumb:
                    # Step C: Attach the crumb to the search query to force it through the firewall
                    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={ticker}&newsCount=8&crumb={crumb}"
                    response = session.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        data = response.json()
                        news = data.get('news', [])
                        if news:
                            print(f"[{ticker}] Bypass Successful! Extracted {len(news)} articles.")
                    else:
                        print(f"[{ticker}] Bypass rejected with status {response.status_code}")
            except Exception as e:
                print(f"[{ticker}] Bypass engine interrupted: {str(e)}")

        # If they STILL block us after stealing their cookies, we return success so the FastAPI router doesn't crash the rest of the RAG pipeline.
        if not news:
            print(f"[{ticker}] Final Failure: Yahoo completely blocked the request. Moving on to RAG.")
            return {"status": "success", "articles_inserted": 0, "message": "News API throttled."}
            
        print(f"Successfully pulled {len(news)} articles for {ticker}. Formatting for database...")

        payloads = []
        for article in news:
            # Try getting 'link', fallback to 'url' if Yahoo changed their API
            url = article.get("link", "") or article.get("url", "")
            if not url:
                continue # Skip invalid articles to prevent empty URL database conflicts
                
            # Fallback to the current time if providerPublishTime is missing
            pub_time = article.get("providerPublishTime")
            dt_obj = datetime.fromtimestamp(pub_time) if pub_time else datetime.utcnow()
            
            payloads.append({
                "ticker": ticker,
                "title": article.get("title", ""),
                "summary": article.get("summary", "") or article.get("publisher", ""), 
                "url": url,
                "published_at": dt_obj.isoformat(),
                "created_at": datetime.utcnow().isoformat()
            })
        
        print(f"Pushing {len(payloads)} valid articles to Supabase...")
        
        # SAFETY CHECK: Don't ping the database if we have no valid articles!
        if not payloads:
            print("No valid articles with URLs were found. Skipping database insertion.")
            return {"status": "success", "articles_inserted": 0, "message": "Yahoo returned articles without URLs."}
        
        try:
            # Use upsert instead of insert to handle duplicate articles gracefully
            response = supabase_client.table("soc_news_articles").upsert(
                payloads, on_conflict="url"
            ).execute()
            
            return {"status": "success", "articles_inserted": len(payloads)}
        except Exception as e:
            print(f"Supabase Database Error: {str(e)}")
            # Don't kill the pipeline just because the database hiccuped on news
            return {"status": "error", "message": "Failed to save news to DB."}