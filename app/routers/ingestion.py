from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import requests
from app.services.yfinance_service import YFinanceService
from app.services.news_service import NewsService
from app.services.sec_service import SECService
from app.services.vector_service import VectorService
from app.services.fred_service import FredService
from app.services.agent_service import AgentService
from app.services.sec_listener_service import SECListenerService
from app.database import supabase_client
from app.status_store import log_update, get_logs, clear_logs

class VectorizeRequest(BaseModel):
    filing_id: str
    storage_bucket_url: str
    ticker: str

router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])

# --- TIER 5: FUZZY SEARCH HELPER ---
def get_ticker_suggestions(query: str):
    """Fetches ticker suggestions from Yahoo Finance search."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=3"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            quotes = res.json().get('quotes', [])
            suggestions = []
            for q in quotes:
                symbol = q.get('symbol')
                name = q.get('shortname', q.get('longname', ''))
                if symbol and q.get('quoteType') == 'EQUITY':
                    suggestions.append(f"{name} ({symbol})")
            return suggestions
    except Exception:
        pass
    return []

# --- BACKGROUND WORKER ---
def background_sec_vectorization(ticker: str):
    """Silently downloads and vectorizes SEC filings in the background."""
    try:
        print(f"[BACKGROUND] Starting heavy SEC vectorization for {ticker}...")
        sec_data = SECService.fetch_and_store_10k(ticker)
        
        filing_id = None
        storage_url = None
        
        if "db_record" in sec_data and isinstance(sec_data["db_record"], list) and len(sec_data["db_record"]) > 0:
            filing_id = sec_data["db_record"][0].get("id")
            storage_url = sec_data["db_record"][0].get("storage_bucket_url")
        elif "data" in sec_data and isinstance(sec_data["data"], list) and len(sec_data["data"]) > 0:
            filing_id = sec_data["data"][0].get("id")
            storage_url = sec_data["data"][0].get("storage_bucket_url")
        elif "id" in sec_data:
            filing_id = sec_data["id"]
            storage_url = sec_data["storage_bucket_url"]
        elif "filing_id" in sec_data:
            filing_id = sec_data["filing_id"]
            storage_url = sec_data["storage_bucket_url"]
            
        if not filing_id or not storage_url:
            raise ValueError(f"Missing ID/URL in SEC response payload.")

        VectorService.chunk_and_embed_filing(
            filing_id=filing_id,
            storage_bucket_url=storage_url,
            ticker=ticker
        )
        print(f"[BACKGROUND] Successfully vectorized 10-K for {ticker}! Ready for RAG.")
    except Exception as e:
        print(f"[BACKGROUND] Error vectorizing {ticker}: {e}")

# --- AUTO-PIPELINE (FAST RESEARCH) ---
@router.post("/analyze/{ticker}")
async def generate_research_report(ticker: str, background_tasks: BackgroundTasks):
    try:
        clear_logs(ticker)
        log_update(ticker, "Initiating Autonomous Pipeline...")
        
        # 1. Validate equity
        try:
            log_update(ticker, "Validating equity status...")
            YFinanceService.fetch_and_store_fundamentals(ticker)
        except ValueError as ve:
            log_update(ticker, f"Validation failed: {ve}")
            suggestions = get_ticker_suggestions(ticker)
            raise HTTPException(
                status_code=400, 
                detail={
                    "message": str(ve),
                    "suggestions": suggestions
                }
            )
            
        # 2. Fetch News
        log_update(ticker, "Fetching latest market news...")
        NewsService.fetch_and_store_news(ticker)
        
        # 3. NON-BLOCKING SEC CHECK:
        # Instead of raising 400 if not ready, we simply trigger the background
        # task if it hasn't been started, and proceed with the report.
        res = supabase_client.table("soc_sec_filings").select("id").eq("ticker", ticker.upper()).execute()
        if not res.data:
            log_update(ticker, "SEC filing not found. Triggering background ingestion...")
            background_tasks.add_task(background_sec_vectorization, ticker)
        else:
            log_update(ticker, "SEC filing found in database.")
            
        # 4. Generate report WITHOUT RAG (Safe even if vectorization is running)
        result = AgentService.generate_intelligence_report(ticker, use_rag=False)
        return result
        
    except HTTPException as he:
        raise he 
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- DEEP RAG PIPELINE ---
@router.post("/analyze/deep/{ticker}")
async def generate_deep_research_report(ticker: str):
    try:
        clear_logs(ticker)
        log_update(ticker, "Initiating DEEP RAG Pipeline...")
        
        # 1. Validate equity
        try:
            log_update(ticker, "Validating equity status...")
            YFinanceService.fetch_and_store_fundamentals(ticker)
        except ValueError as ve:
            log_update(ticker, f"Validation failed: {ve}")
            suggestions = get_ticker_suggestions(ticker)
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            raise HTTPException(status_code=400, detail=str(ve) + suggestion_text)
            
        # 2. Check if the specific filing is fully processed (Only select is_ready)
        res = supabase_client.table("soc_sec_filings") \
            .select("is_ready") \
            .eq("ticker", ticker.upper()) \
            .eq("is_ready", True) \
            .execute()
        
        if not res.data:
             log_update(ticker, "ERROR: SEC Data is missing or vectorizing. Pipeline halted.")
             raise HTTPException(
                 status_code=400, 
                 detail="SEC Data is still vectorizing in the background or doesn't exist. Please wait for the 'Deep Research is Ready' status."
             )
             
        # 3. Proceed
        result = AgentService.generate_intelligence_report(ticker, use_rag=True)
        return result
    except HTTPException as he:
        raise he 
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- MANUAL ROUTES ---
@router.get("/macro")
async def get_macro_data():
    try:
        res = supabase_client.table("soc_economic_events").select("*").execute()
        return {"status": "success", "data": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {str(e)}")

@router.post("/macro")
async def ingest_macro_economy():
    try:
        return FredService.fetch_and_store_macro_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- LIVE STATUS CONSOLE (TIER 4) ---
@router.get("/status/{ticker}")
async def get_pipeline_status(ticker: str):
    """Returns the live terminal output logs for the requested ticker."""
    return {"status": "success", "logs": get_logs(ticker)}