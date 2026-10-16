import re
import requests
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from app.services.xbrl_service import XBRLService
from app.services.news_service import NewsService
from app.services.sec_service import SECService
from app.services.fred_service import FredService
from app.services.agent_service import AgentService
from app.database import supabase_client
from app.status_store import (
    log_update,
    get_logs,
    clear_logs,
    is_vectorizing,
    sanitize_log_message,
)


class VectorizeRequest(BaseModel):
    filing_id: str
    storage_bucket_url: str
    ticker: str


router = APIRouter(prefix="/api/v1/ingestion", tags=["Ingestion"])

_TICKER_REGEX = re.compile(r"^[A-Z0-9.\-]{1,12}$")


def normalize_and_validate_ticker(raw_ticker: str) -> str:
    """Sanitizes ticker input (strips whitespace and leading '$') and validates format."""
    cleaned = (raw_ticker or "").strip().lstrip("$").strip().upper()
    if not cleaned or not _TICKER_REGEX.match(cleaned):
        suggestions = get_ticker_suggestions(raw_ticker)
        suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format '{raw_ticker}'." + suggestion_text,
        )
    return cleaned


# --- TIER 5: FUZZY SEARCH HELPER ---
def get_ticker_suggestions(query: str):
    """Fetches equity ticker suggestions from Yahoo Finance search."""
    if not query or not query.strip():
        return []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        res = requests.get(
            url,
            params={"q": query.strip()[:30], "quotesCount": 5},
            headers=headers,
            timeout=5,
        )
        if res.status_code == 200:
            quotes = res.json().get("quotes", [])
            suggestions = []
            for q in quotes:
                symbol = q.get("symbol")
                name = q.get("shortname") or q.get("longname") or ""
                if symbol and q.get("quoteType") == "EQUITY":
                    suggestions.append(f"{name} ({symbol})" if name else symbol)
                if len(suggestions) >= 3:
                    break
            return suggestions
    except Exception:
        pass
    return []


# --- BACKGROUND WORKER ---
def background_sec_vectorization(ticker: str):
    """Silently downloads and vectorizes SEC filings in the background with atomic lock protection."""
    ticker_upper = ticker.strip().upper()
    try:
        print(f"[BACKGROUND] Starting heavy SEC vectorization for {ticker_upper}...")
        res = SECService.download_and_vectorize_filing(ticker_upper)
        if res.get("status") != "already_running":
            print(f"[BACKGROUND] Successfully vectorized filing for {ticker_upper}! Ready for RAG.")
    except Exception as e:
        log_update(ticker_upper, f"Background SEC ingestion failed: {sanitize_log_message(str(e))}")
        print(f"[BACKGROUND] Error vectorizing {ticker_upper}: {e}")


# --- AUTO-PIPELINE (FAST RESEARCH) ---
@router.post("/analyze/{ticker}")
async def generate_research_report(ticker: str, background_tasks: BackgroundTasks):
    try:
        ticker_upper = normalize_and_validate_ticker(ticker)
        clear_logs(ticker_upper)
        log_update(ticker_upper, "Initiating Autonomous Pipeline...")

        # 1. Validate equity & ingest fundamentals
        try:
            log_update(ticker_upper, "Validating equity status...")
            XBRLService.fetch_and_store_fundamentals(ticker_upper)
        except ValueError as ve:
            log_update(ticker_upper, f"Validation failed: {ve}")
            suggestions = get_ticker_suggestions(ticker_upper)
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            raise HTTPException(status_code=400, detail=str(ve) + suggestion_text)

        # 2. Fetch News
        log_update(ticker_upper, "Fetching latest market news...")
        NewsService.fetch_and_store_news(ticker_upper)

        # 3. NON-BLOCKING SEC CHECK
        res = (
            supabase_client.table("soc_sec_filings")
            .select("id, is_ready")
            .eq("ticker", ticker_upper)
            .order("filed_at", desc=True)
            .limit(1)
            .execute()
        )
        if not res.data:
            if not is_vectorizing(ticker_upper):
                log_update(ticker_upper, "SEC filing not found. Triggering background ingestion...")
                background_tasks.add_task(background_sec_vectorization, ticker_upper)
            else:
                log_update(ticker_upper, "SEC filing ingestion is currently running in the background.")
        elif not res.data[0].get("is_ready") and not is_vectorizing(ticker_upper):
            # Previous run may have been interrupted; check if chunks exist or re-trigger
            chunk_check = (
                supabase_client.table("soc_filing_chunks")
                .select("id", count="exact")
                .eq("ticker", ticker_upper)
                .limit(1)
                .execute()
            )
            if chunk_check.count and chunk_check.count > 0:
                supabase_client.table("soc_sec_filings").update({"is_ready": True}).eq("id", res.data[0]["id"]).execute()
                log_update(ticker_upper, "SEC filing verified in database.")
            else:
                log_update(ticker_upper, "Resuming incomplete SEC background vectorization...")
                background_tasks.add_task(background_sec_vectorization, ticker_upper)
        else:
            log_update(ticker_upper, "SEC filing found in database.")

        # 4. Generate report WITHOUT RAG (Safe even if vectorization is running)
        result = AgentService.generate_intelligence_report(ticker_upper, use_rag=False)
        return result

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_log_message(str(e)))


# --- DEEP RAG PIPELINE ---
@router.post("/analyze/deep/{ticker}")
async def generate_deep_research_report(ticker: str, background_tasks: BackgroundTasks):
    try:
        ticker_upper = normalize_and_validate_ticker(ticker)
        clear_logs(ticker_upper)
        log_update(ticker_upper, "Initiating DEEP RAG Pipeline...")

        # 1. Validate equity & ensure fundamentals exist
        try:
            log_update(ticker_upper, "Validating equity status...")
            XBRLService.fetch_and_store_fundamentals(ticker_upper)
        except ValueError as ve:
            log_update(ticker_upper, f"Validation failed: {ve}")
            suggestions = get_ticker_suggestions(ticker_upper)
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
            raise HTTPException(status_code=400, detail=str(ve) + suggestion_text)

        # 2. Check if the specific filing is fully processed
        res = (
            supabase_client.table("soc_sec_filings")
            .select("id, is_ready")
            .eq("ticker", ticker_upper)
            .order("filed_at", desc=True)
            .limit(1)
            .execute()
        )

        # If no record exists, trigger background job if not already running
        if not res.data:
            if not is_vectorizing(ticker_upper):
                log_update(ticker_upper, "No SEC filing record found. Launching background ingestion...")
                background_tasks.add_task(background_sec_vectorization, ticker_upper)
            else:
                log_update(ticker_upper, "SEC vectorization is actively running in the background...")
            raise HTTPException(
                status_code=400,
                detail="SEC filing initiated. Vectorization started in background. Please wait 30 seconds.",
            )

        # Check if vectorization is still in progress or needs auto-repair
        if not res.data[0].get("is_ready"):
            if is_vectorizing(ticker_upper):
                # Do NOT mark is_ready=True while chunks are actively being inserted!
                log_update(ticker_upper, "ERROR: SEC Data is still actively vectorizing. Pipeline halted.")
                raise HTTPException(
                    status_code=400,
                    detail="SEC Data is still vectorizing in the background. Please wait for the 'Deep Research is Ready' status.",
                )

            chunk_check = (
                supabase_client.table("soc_filing_chunks")
                .select("id", count="exact")
                .eq("ticker", ticker_upper)
                .limit(1)
                .execute()
            )

            if chunk_check.count and chunk_check.count > 0:
                log_update(ticker_upper, "Detected completed chunks for filing. Auto-repairing is_ready status.")
                supabase_client.table("soc_sec_filings").update({"is_ready": True}).eq("id", res.data[0]["id"]).execute()
            else:
                log_update(ticker_upper, "Detected stalled SEC record with 0 chunks. Restarting background vectorization...")
                background_tasks.add_task(background_sec_vectorization, ticker_upper)
                raise HTTPException(
                    status_code=400,
                    detail="SEC Data vectorization was restarted in the background. Please wait for the 'Deep Research is Ready' status.",
                )

        # 3. Ensure latest news is available before Deep RAG synthesis
        NewsService.fetch_and_store_news(ticker_upper)

        # 4. Proceed with Multi-Query Deep RAG synthesis
        result = AgentService.generate_intelligence_report(ticker_upper, use_rag=True)
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_log_message(str(e)))


# --- MANUAL & DASHBOARD ROUTES ---
@router.get("/macro")
async def get_macro_data():
    try:
        res = (
            supabase_client.table("soc_economic_events")
            .select("*")
            .order("released_at", desc=True)
            .limit(20)
            .execute()
        )
        raw_rows = res.data or []
        seen = set()
        deduped = []
        for row in raw_rows:
            ev = row.get("event_name")
            if ev and ev not in seen:
                seen.add(ev)
                deduped.append(row)
        return {"status": "success", "data": deduped}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {sanitize_log_message(str(e))}")


@router.post("/macro")
async def ingest_macro_economy():
    try:
        return FredService.fetch_and_store_macro_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_log_message(str(e)))


@router.get("/history")
async def get_research_history(limit: int = 30):
    """Returns recent cached intelligence reports for the left sidebar history & instant switching."""
    try:
        safe_limit = max(1, min(100, limit))
        res = (
            supabase_client.table("soc_research_intelligence")
            .select(
                "id, ticker, analysis_date, is_deep_rag, sentiment_score, sentiment_label, "
                "risk_score, bullish_score, confidence_score, created_at"
            )
            .order("analysis_date", desc=True)
            .order("created_at", desc=True)
            .limit(safe_limit)
            .execute()
        )
        return {"status": "success", "data": res.data or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {sanitize_log_message(str(e))}")


@router.get("/report/{ticker}")
async def get_cached_report(ticker: str, is_deep_rag: Optional[bool] = None, analysis_date: Optional[str] = None):
    """Instantly retrieves a cached intelligence report and its supporting context without re-running LLM inference."""
    try:
        ticker_upper = normalize_and_validate_ticker(ticker)
        query = (
            supabase_client.table("soc_research_intelligence")
            .select("*")
            .eq("ticker", ticker_upper)
        )
        if is_deep_rag is not None:
            query = query.eq("is_deep_rag", is_deep_rag)
        if analysis_date:
            query = query.eq("analysis_date", analysis_date)

        res = query.order("analysis_date", desc=True).order("created_at", desc=True).limit(1).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail=f"No cached report found for {ticker_upper}.")

        formatted = AgentService.format_report_record(res.data[0], include_supporting=True)
        return {"status": "success", "data": formatted}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=sanitize_log_message(str(e)))


@router.get("/watchlist")
async def get_watchlist():
    """Returns active tracked tickers in the autonomous watchlist along with their latest fundamentals & sentiment."""
    try:
        res = (
            supabase_client.table("soc_watchlist")
            .select("*")
            .eq("is_active", True)
            .order("added_at", desc=False)
            .execute()
        )
        items = res.data or []
        return {"status": "success", "data": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {sanitize_log_message(str(e))}")


@router.post("/watchlist/{ticker}")
async def add_to_watchlist(ticker: str):
    """Adds or reactivates a ticker in the autonomous watchlist."""
    try:
        ticker_upper = normalize_and_validate_ticker(ticker)
        payload = {"ticker": ticker_upper, "is_active": True}
        res = (
            supabase_client.table("soc_watchlist")
            .upsert(payload, on_conflict="ticker")
            .execute()
        )
        return {"status": "success", "data": res.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {sanitize_log_message(str(e))}")


@router.delete("/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str):
    """Deactivates a ticker from the autonomous watchlist."""
    try:
        ticker_upper = normalize_and_validate_ticker(ticker)
        res = (
            supabase_client.table("soc_watchlist")
            .update({"is_active": False})
            .eq("ticker", ticker_upper)
            .execute()
        )
        return {"status": "success", "data": res.data}
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase Error: {sanitize_log_message(str(e))}")


# --- LIVE STATUS CONSOLE (TIER 4) ---
@router.get("/status/{ticker}")
async def get_pipeline_status(ticker: str):
    """Returns the live terminal output logs and SEC vectorization state for the requested ticker."""
    clean_ticker = (ticker or "").strip().lstrip("$").strip().upper()
    sec_ready = False
    sec_form = None
    sec_filed_at = None
    try:
        if clean_ticker and _TICKER_REGEX.match(clean_ticker):
            sec_res = (
                supabase_client.table("soc_sec_filings")
                .select("form_type, filed_at, is_ready")
                .eq("ticker", clean_ticker)
                .order("filed_at", desc=True)
                .limit(1)
                .execute()
            )
            if sec_res.data:
                sec_ready = bool(sec_res.data[0].get("is_ready"))
                sec_form = sec_res.data[0].get("form_type")
                sec_filed_at = sec_res.data[0].get("filed_at")
    except Exception:
        pass

    return {
        "status": "success",
        "logs": get_logs(clean_ticker),
        "is_vectorizing": is_vectorizing(clean_ticker),
        "sec_ready": sec_ready,
        "sec_form": sec_form,
        "sec_filed_at": sec_filed_at,
    }