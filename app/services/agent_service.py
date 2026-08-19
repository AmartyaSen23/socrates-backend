import json
import requests
from groq import Groq
from datetime import datetime
from app.config import settings
from app.database import supabase_client
from app.status_store import log_update, get_logs, clear_logs

class AgentService:
    @staticmethod
    def generate_intelligence_report(ticker: str, use_rag: bool = False):
        ticker = ticker.upper()
        today_str = datetime.utcnow().strftime('%Y-%m-%d')
        
        # ==========================================
        # 1. THE CACHE BARRIER (TIER 1)
        # ==========================================
        log_update(ticker, f"Checking database cache for today's report (Deep RAG: {use_rag})...")
        cached_res = supabase_client.table("soc_research_intelligence") \
            .select("*") \
            .eq("ticker", ticker) \
            .eq("analysis_date", today_str) \
            .eq("is_deep_rag", use_rag) \
            .execute()
            
        if cached_res.data:
            log_update(ticker, "⚡ CACHE HIT! Returning instant pre-computed response.")
            db_row = cached_res.data[0]
            standardized_data = {
                "sentiment_score": db_row.get("sentiment_score"),
                "sentiment_label": db_row.get("sentiment_label"),
                "risk_score": db_row.get("risk_score"),
                "major_risks": db_row.get("major_risks"),
                "bullish_score": db_row.get("bullish_score"),
                "growth_drivers": db_row.get("growth_drivers"),
                "confidence_score": db_row.get("confidence_score"),
                "bull_case_summary": db_row.get("bull_case_summary"),
                "bear_case_summary": db_row.get("bear_case_summary")
            }
            return {"status": "success", "data": standardized_data}

        # ==========================================
        # 2. Gather the Context (News & Fundamentals)
        # ==========================================
        log_update(ticker, "Cache miss. Generating fresh intelligence...")
        news_res = supabase_client.table("soc_news_articles").select("title, summary, published_at").eq("ticker", ticker).order("published_at", desc=True).limit(15).execute()
        fund_res = supabase_client.table("soc_company_fundamentals").select("*").eq("ticker", ticker).order("fiscal_date", desc=True).limit(1).execute()
        
        if not news_res.data and not fund_res.data:
            raise Exception(f"Insufficient data to analyze {ticker}")

        news_context = "\n".join([f"- {n['published_at'][:10]}: {n['title']} ({n['summary']})" for n in news_res.data])
        fund_context = json.dumps(fund_res.data[0]) if fund_res.data else "No fundamentals available."

        # ==========================================
        # 3. DEEP RAG: Multi-Query Vector Search (TIER 2)
        # ==========================================
        sec_context = "No deep SEC analysis requested."
        if use_rag:
            log_update(ticker, "Executing Multi-Query Deep RAG Search on SEC Filings...")
            try:
                rag_queries = [
                    "What are the primary risk factors, regulatory threats, and competitive dangers?",
                    "What are the major growth drivers, new product launches, and strategic opportunities?",
                    "What is the financial performance, revenue growth, and debt structure?"
                ]
                
                cohere_url = "https://api.cohere.ai/v1/embed"
                headers = {"Authorization": f"Bearer {settings.cohere_api_key}", "Content-Type": "application/json"}
                payload = {
                    "texts": rag_queries,
                    "model": "embed-english-v3.0",
                    "input_type": "search_query"
                }
                res = requests.post(cohere_url, json=payload, headers=headers)
                query_embeddings = res.json()["embeddings"]

                unique_chunks = {}
                for i, q_emb in enumerate(query_embeddings):
                    rpc_res = supabase_client.rpc(
                        "match_filing_chunks",
                        {
                            "query_embedding": q_emb,
                            "match_threshold": 0.25,
                            "match_count": 3,
                            "p_ticker": ticker
                        }
                    ).execute()
                    
                    if rpc_res.data:
                        for chunk in rpc_res.data:
                            unique_chunks[chunk['id']] = chunk['chunk_content']

                if unique_chunks:
                    final_chunks = list(unique_chunks.values())[:6]
                    sec_context = "\n\n".join([f"Excerpt {i+1}:\n{text}" for i, text in enumerate(final_chunks)])
                    log_update(ticker, f"Successfully aggregated {len(final_chunks)} unique SEC chunks across 3 queries!")
                else:
                    sec_context = "SEC filings were searched, but no highly relevant data was found."
            except Exception as e:
                print(f"RAG Search Error: {e}")
                sec_context = f"Failed to retrieve SEC data: {str(e)}"

        # ==========================================
        # 4. Build the System Prompt & JSON Schema
        # ==========================================
        system_prompt = """
        You are the Socrates Master Research Agent, an elite AI financial analyst.
        Analyze the provided news, fundamentals, and SEC excerpts for the target company.
        You must output ONLY valid JSON matching this exact schema:
        {
            "sentiment_score": int (0-100),
            "sentiment_label": str ("Bullish", "Bearish", "Neutral"),
            "risk_score": int (0-100, where 100 is extreme risk),
            "major_risks": [str, str, str],
            "bullish_score": int (0-100),
            "growth_drivers": [str, str, str],
            "confidence_score": int (0-100, how confident are you in this analysis based on data quality),
            "bull_case_summary": str (1 paragraph),
            "bear_case_summary": str (1 paragraph)
        }
        """

        user_prompt = f"Target Ticker: {ticker}\n\nFUNDAMENTALS:\n{fund_context}\n\nLATEST NEWS:\n{news_context}\n\nSEC 10-K FILING EXCERPTS (DEEP RAG):\n{sec_context}"

        # ==========================================
        # 5. Call Groq Cloud (Blazing Fast Inference)
        # ==========================================
        client = Groq(api_key=settings.groq_api_key)
        
        log_update(ticker, "Agent is synthesizing analysis using Qwen 2.5 32B...")
        try:
            completion = client.chat.completions.create(
                model="qwen-2.5-32b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2, 
                max_tokens=4096,  # 🛡️ THE FIX: Forces Groq to allocate enough space for the full JSON
                response_format={"type": "json_object"} 
            )

            raw_json = completion.choices[0].message.content
            intelligence_data = json.loads(raw_json)
            log_update(ticker, "Groq successfully generated the JSON report!")
        except Exception as e:
            raise Exception(f"Groq API Error: {str(e)}")

        # ==========================================
        # 6. Map and Insert into Intelligence DB
        # ==========================================
        db_payload = {
            "ticker": ticker,
            "analysis_date": today_str,
            "is_deep_rag": use_rag,
            "sentiment_score": intelligence_data.get("sentiment_score"),
            "sentiment_label": intelligence_data.get("sentiment_label"),
            "risk_score": intelligence_data.get("risk_score"),
            "major_risks": intelligence_data.get("major_risks"),
            "bullish_score": intelligence_data.get("bullish_score"),
            "growth_drivers": intelligence_data.get("growth_drivers"),
            "confidence_score": intelligence_data.get("confidence_score"),
            "bull_case_summary": intelligence_data.get("bull_case_summary"),
            "bear_case_summary": intelligence_data.get("bear_case_summary")
        }

        try:
            supabase_client.table("soc_research_intelligence").upsert(
                db_payload, on_conflict="ticker,analysis_date,is_deep_rag"
            ).execute()
            return {"status": "success", "data": intelligence_data}
        except Exception as e:
            raise Exception(f"Supabase Database Error: {str(e)}")