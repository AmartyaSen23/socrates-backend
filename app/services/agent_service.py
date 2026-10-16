import json
import re
import requests
from groq import Groq
from datetime import datetime, timezone
from typing import Dict, Any, List, Set, Optional
from app.config import settings
from app.database import supabase_client
from app.status_store import log_update


class AgentService:
    # Curated order of Groq text reasoning models known to support structured JSON generation
    PREFERRED_MODELS = [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ]

    EXCLUDED_MODEL_KEYWORDS = [
        "guard", "safeguard", "whisper", "tts", "playai", "orpheus", "embed", "vision", "allam"
    ]

    @staticmethod
    def get_dynamic_fallback_model(client: Groq, exclude_models: Optional[Set[str]] = None) -> str:
        """
        Pings Groq's API for currently active models available to the user's tier,
        excluding any models that already failed or hit rate limits in this request,
        and selects the strongest reasoning model available.
        """
        exclude = exclude_models or set()
        try:
            available_models = client.models.list().data
            model_ids = [
                m.id for m in available_models
                if m.id not in exclude
                and not any(k in m.id.lower() for k in AgentService.EXCLUDED_MODEL_KEYWORDS)
            ]

            # 1. Check curated preferred models first
            for pref in AgentService.PREFERRED_MODELS:
                if pref in model_ids and pref not in exclude:
                    return pref

            # 2. Check by parameter count priority
            priority_sizes = ["120b", "70b", "32b", "27b", "20b", "9b", "8b"]
            for size in priority_sizes:
                for m_id in model_ids:
                    if size in m_id.lower():
                        return m_id

            # 3. Any remaining valid text model
            if model_ids:
                return model_ids[0]

        except Exception:
            pass

        # Ultimate fallback rotation if models.list() fails
        for fallback in AgentService.PREFERRED_MODELS:
            if fallback not in exclude:
                return fallback
        return "llama-3.3-70b-versatile"

    @staticmethod
    def _format_currency(val: Any) -> str:
        if val is None:
            return "N/A"
        try:
            num = float(val)
            abs_num = abs(num)
            if abs_num >= 1_000_000_000_000:
                return f"${num / 1_000_000_000_000:,.2f}T (${int(num):,})"
            if abs_num >= 1_000_000_000:
                return f"${num / 1_000_000_000:,.2f}B (${int(num):,})"
            if abs_num >= 1_000_000:
                return f"${num / 1_000_000:,.2f}M (${int(num):,})"
            return f"${num:,.2f}"
        except (ValueError, TypeError):
            return str(val)

    @staticmethod
    def _parse_and_normalize_report(raw_content: str) -> Dict[str, Any]:
        """
        Extracts JSON even if wrapped in reasoning <think> tags or markdown blocks,
        and enforces strict types and bounds for all 9 schema fields.
        """
        if not raw_content:
            raise ValueError("Empty response received from LLM.")

        cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                raise
            data = json.loads(match.group(0))

        if not isinstance(data, dict):
            raise ValueError("LLM output JSON root must be an object.")

        def clamp_score(val: Any, default: int = 50) -> int:
            try:
                num = int(round(float(val)))
                return max(0, min(100, num))
            except (ValueError, TypeError):
                return default

        def ensure_str_list(val: Any, fallback_item: str) -> List[str]:
            if isinstance(val, list):
                items = [str(x).strip() for x in val if x and str(x).strip()]
            elif isinstance(val, str) and val.strip():
                items = [s.strip() for s in val.split(";") if s.strip()]
            else:
                items = []
            while len(items) < 3:
                items.append(fallback_item)
            return items[:3]

        sentiment_score = clamp_score(data.get("sentiment_score"), 50)
        raw_label = str(data.get("sentiment_label", "")).strip().capitalize()
        if raw_label not in ("Bullish", "Bearish", "Neutral"):
            if sentiment_score >= 60:
                raw_label = "Bullish"
            elif sentiment_score <= 40:
                raw_label = "Bearish"
            else:
                raw_label = "Neutral"

        return {
            "sentiment_score": sentiment_score,
            "sentiment_label": raw_label,
            "risk_score": clamp_score(data.get("risk_score"), 50),
            "major_risks": ensure_str_list(data.get("major_risks"), "Market and macroeconomic volatility"),
            "bullish_score": clamp_score(data.get("bullish_score"), sentiment_score),
            "growth_drivers": ensure_str_list(data.get("growth_drivers"), "Core operational execution and market expansion"),
            "confidence_score": clamp_score(data.get("confidence_score"), 75),
            "bull_case_summary": str(data.get("bull_case_summary") or "Insufficient bullish data available.").strip(),
            "bear_case_summary": str(data.get("bear_case_summary") or "Insufficient bearish data available.").strip(),
        }

    @staticmethod
    def generate_intelligence_report(ticker: str, use_rag: bool = False):
        ticker = ticker.strip().upper()
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # ==========================================
        # 1. THE CACHE BARRIER (TIER 1)
        # ==========================================
        log_update(ticker, f"Checking database cache for today's report (Deep RAG: {use_rag})...")
        cached_res = (
            supabase_client.table("soc_research_intelligence")
            .select("*")
            .eq("ticker", ticker)
            .eq("analysis_date", today_str)
            .eq("is_deep_rag", use_rag)
            .execute()
        )

        if cached_res.data:
            log_update(ticker, "⚡ CACHE HIT! Returning instant pre-computed response.")
            db_row = cached_res.data[0]
            standardized_data = {
                "sentiment_score": db_row.get("sentiment_score"),
                "sentiment_label": db_row.get("sentiment_label"),
                "risk_score": db_row.get("risk_score"),
                "major_risks": db_row.get("major_risks") or [],
                "bullish_score": db_row.get("bullish_score"),
                "growth_drivers": db_row.get("growth_drivers") or [],
                "confidence_score": db_row.get("confidence_score"),
                "bull_case_summary": db_row.get("bull_case_summary"),
                "bear_case_summary": db_row.get("bear_case_summary"),
            }
            return {"status": "success", "data": standardized_data}

        # ==========================================
        # 2. Gather Context (News, Fundamentals & Macro)
        # ==========================================
        log_update(ticker, "Cache miss. Generating fresh intelligence...")
        news_res = (
            supabase_client.table("soc_news_articles")
            .select("title, summary, published_at")
            .eq("ticker", ticker)
            .order("published_at", desc=True)
            .limit(15)
            .execute()
        )
        fund_res = (
            supabase_client.table("soc_company_fundamentals")
            .select("*")
            .eq("ticker", ticker)
            .order("fiscal_date", desc=True)
            .limit(1)
            .execute()
        )

        if not news_res.data and not fund_res.data:
            raise Exception(f"Insufficient data to analyze {ticker}")

        news_context = (
            "\n".join([
                f"- {(n.get('published_at') or '')[:10]}: {n.get('title', '')} ({n.get('summary', '')})"
                for n in (news_res.data or [])
            ])
            or "No recent institutional news articles available."
        )

        if fund_res.data:
            f_row = fund_res.data[0]
            fund_context = json.dumps({
                "ticker": f_row.get("ticker"),
                "fiscal_date": f_row.get("fiscal_date"),
                "market_cap_formatted": AgentService._format_currency(f_row.get("market_cap")),
                "revenue_formatted": AgentService._format_currency(f_row.get("revenue")),
                "total_debt_formatted": AgentService._format_currency(f_row.get("total_debt")),
                "eps": f_row.get("eps"),
                "pe_ratio": f_row.get("pe_ratio"),
            }, indent=2)
        else:
            fund_context = "No fundamentals available."

        # Fetch macro context if available in DB (zero external API cost)
        macro_context = "No macroeconomic data cached."
        try:
            macro_res = supabase_client.table("soc_economic_events").select("*").limit(10).execute()
            if macro_res.data:
                macro_lines = [
                    f"- {m.get('event_name')}: {m.get('actual_value')} (as of {m.get('released_at')})"
                    for m in macro_res.data
                ]
                macro_context = "\n".join(macro_lines)
        except Exception:
            pass

        # ==========================================
        # 3. DEEP RAG: Multi-Query Vector Search (TIER 2)
        # ==========================================
        sec_context = "No deep SEC analysis requested."
        if use_rag:
            log_update(ticker, "Executing Multi-Query Deep RAG Search on SEC Filings...")
            try:
                rag_queries = [
                    "What are the primary risk factors, regulatory threats, litigation, and competitive dangers?",
                    "What are the major growth drivers, new product launches, R&D, and strategic opportunities?",
                    "What is the financial performance, revenue growth, operating margins, liquidity, and debt structure?",
                ]

                cohere_url = "https://api.cohere.ai/v1/embed"
                headers = {
                    "Authorization": f"Bearer {settings.cohere_api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "texts": rag_queries,
                    "model": "embed-english-v3.0",
                    "input_type": "search_query",
                }
                res = requests.post(cohere_url, json=payload, headers=headers, timeout=15)
                if res.status_code != 200:
                    raise Exception(f"Cohere Embed HTTP {res.status_code}: {res.text}")

                query_embeddings = res.json().get("embeddings", [])

                unique_chunks: Dict[Any, str] = {}
                for threshold in (0.25, 0.12):
                    for q_emb in query_embeddings:
                        rpc_res = supabase_client.rpc(
                            "match_filing_chunks",
                            {
                                "query_embedding": q_emb,
                                "match_threshold": threshold,
                                "match_count": 3,
                                "p_ticker": ticker,
                            },
                        ).execute()

                        if rpc_res.data:
                            for chunk in rpc_res.data:
                                unique_chunks[chunk["id"]] = chunk["chunk_content"]
                    if unique_chunks:
                        break

                if unique_chunks:
                    final_chunks = list(unique_chunks.values())[:6]
                    sec_context = "\n\n".join([f"Excerpt {i + 1}:\n{text}" for i, text in enumerate(final_chunks)])
                    log_update(ticker, f"Successfully aggregated {len(final_chunks)} unique SEC chunks across 3 queries!")
                else:
                    sec_context = "SEC filings were searched, but no relevant excerpts exceeded similarity threshold."
            except Exception as e:
                print(f"RAG Search Error: {e}")
                sec_context = "SEC filing retrieval encountered a temporary error."

        # ==========================================
        # 4. Build the System Prompt & JSON Schema
        # ==========================================
        system_prompt = """You are the Socrates Master Research Agent, an elite institutional AI financial analyst.
Analyze the provided company fundamentals, macroeconomic backdrop, institutional news, and SEC filing excerpts.
You must output ONLY valid JSON matching this exact schema:
{
    "sentiment_score": int (0-100),
    "sentiment_label": str ("Bullish", "Bearish", or "Neutral"),
    "risk_score": int (0-100, where 100 is extreme risk),
    "major_risks": [str, str, str],
    "bullish_score": int (0-100),
    "growth_drivers": [str, str, str],
    "confidence_score": int (0-100, based on data completeness and consistency),
    "bull_case_summary": str (1 detailed institutional paragraph citing specific numbers/catalysts),
    "bear_case_summary": str (1 detailed institutional paragraph citing specific risks/headwinds)
}"""

        user_prompt = (
            f"Target Ticker: {ticker}\n\n"
            f"AUDITED FUNDAMENTALS & LIVE VALUATION:\n{fund_context}\n\n"
            f"US MACROECONOMIC BACKDROP:\n{macro_context}\n\n"
            f"LATEST INSTITUTIONAL NEWS:\n{news_context}\n\n"
            f"SEC FILING EXCERPTS (DEEP RAG):\n{sec_context}"
        )

        # ==========================================
        # 5. Call Groq Cloud (Fault-Tolerant Multi-Model Inference)
        # ==========================================
        client = Groq(api_key=settings.groq_api_key)

        current_model = AgentService.PREFERRED_MODELS[0]
        tried_models: Set[str] = set()
        current_max_tokens = 4096

        max_retries = 4
        intelligence_data = None
        last_error = None

        for attempt in range(max_retries):
            log_update(ticker, f"Agent is synthesizing analysis using {current_model} (Attempt {attempt + 1})...")
            try:
                completion = client.chat.completions.create(
                    model=current_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                    max_tokens=current_max_tokens,
                    response_format={"type": "json_object"},
                )

                raw_json = completion.choices[0].message.content
                intelligence_data = AgentService._parse_and_normalize_report(raw_json)
                log_update(ticker, "Groq successfully generated and validated the JSON report!")
                break

            except Exception as e:
                last_error = e
                err_str = str(e)
                err_lower = err_str.lower()

                # CASE 1: Model Not Found / Decommissioned / Rate Limited (404 / 429 / 503)
                if any(
                    k in err_lower
                    for k in [
                        "model_not_found", "does not exist", "decommissioned", "404",
                        "rate_limit", "rate limit", "429", "too many requests",
                        "503", "502", "over capacity", "service unavailable",
                    ]
                ):
                    tried_models.add(current_model)
                    log_update(ticker, f"⚠️ Model '{current_model}' unavailable or rate-limited. Rerouting...")
                    current_model = AgentService.get_dynamic_fallback_model(client, exclude_models=tried_models)
                    log_update(ticker, f"🔄 Dynamic Fallback: Switched to '{current_model}'.")
                    continue

                # CASE 2: Token Limit / JSON Generation Failure
                elif any(
                    k in err_lower
                    for k in [
                        "max completion tokens", "limit reached", "failed_generation",
                        "json_validate_failed", "jsondecodeerror", "expecting value",
                    ]
                ):
                    current_max_tokens = min(current_max_tokens * 2, 8192)
                    tried_models.add(current_model)
                    current_model = AgentService.get_dynamic_fallback_model(client, exclude_models=tried_models)
                    log_update(
                        ticker,
                        f"🔄 Retrying JSON synthesis with model '{current_model}' (max_tokens={current_max_tokens})...",
                    )
                    continue

                else:
                    raise Exception(f"Groq API Error: {err_str}")

        if not intelligence_data:
            raise Exception(f"Failed to generate intelligence report after all fallback retries: {last_error}")

        # ==========================================
        # 6. Map and Insert into Intelligence DB
        # ==========================================
        db_payload = {
            "ticker": ticker,
            "analysis_date": today_str,
            "is_deep_rag": use_rag,
            "sentiment_score": intelligence_data["sentiment_score"],
            "sentiment_label": intelligence_data["sentiment_label"],
            "risk_score": intelligence_data["risk_score"],
            "major_risks": intelligence_data["major_risks"],
            "bullish_score": intelligence_data["bullish_score"],
            "growth_drivers": intelligence_data["growth_drivers"],
            "confidence_score": intelligence_data["confidence_score"],
            "bull_case_summary": intelligence_data["bull_case_summary"],
            "bear_case_summary": intelligence_data["bear_case_summary"],
        }

        try:
            supabase_client.table("soc_research_intelligence").upsert(
                db_payload, on_conflict="ticker,analysis_date,is_deep_rag"
            ).execute()
            return {"status": "success", "data": intelligence_data}
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")