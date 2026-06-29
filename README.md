🏛️ Socrates Research Engine - Core Backend

The Quantitative AI Brain.
A hyper-resilient, fail-fast, multi-agent financial ingestion pipeline.

🚀 Overview

The Socrates Backend is a masterclass in defensive programming and data engineering. Built on FastAPI, it aggregates real-time news, official SEC Edgar filings, and live market valuations. It then feeds this data into a Retrieval-Augmented Generation (RAG) pipeline powered by Cohere and Groq to output structured, institutional-grade stock intelligence.

🏆 Architectural Masterpieces

1. The 5-Layer "Fail-Fast" Valuation Cascade (xbrl_service.py)

Market data APIs block cloud servers constantly. To guarantee a 100% success rate for gathering structural valuation metrics (Market Cap, P/E, EPS), Socrates utilizes a brutal, fail-fast 5-layer cascade:

Phase 1 (The Official Record): SEC EDGAR XBRL extraction for perfectly audited Revenue, Debt, and EPS.

Phase 2, Layer A (FMP API): Primary attempt at live Market Cap and P/E.

Phase 2, Layer B (Finnhub API): Secondary fallback.

Phase 2, Layer C (Polygon.io): Emergency authenticated gateway.

Phase 2, Layer D (YFinance): Universal fallback using fast_info.

Phase 2, Layer E (Mathematical Derivation): Reconstructing the P/E ratio mathematically (Price / EPS) if all APIs strip the data.

Fail-Fast Logic: If an API responds with 200 OK but returns $0.00 or empty arrays (proving the ticker is entirely fake), the cascade halts immediately, preventing API limit burn.

2. Deep SEC RAG Vectorization (vector_service.py)

Socrates automatically downloads, cleans, and chunks massive 10-K and 20-F filings.

Uses RecursiveCharacterTextSplitter (1500 chars, 200 overlap).

Batches texts and generates embed-english-v3.0 vectors via Cohere.

Inserts embeddings directly into a Supabase pgvector database.

Runs silently via BackgroundTasks to prevent HTTP timeouts.

3. The "Cache Barrier"

To optimize Groq API costs and reduce latency to <0.5 seconds, the AgentService intercepts requests. If an identical report (Standard or Deep RAG) was generated for that ticker today, it fetches the JSON directly from Supabase, bypassing all heavy computation.

4. Advanced NLP Ensemble

Leverages Groq (Llama-3.3-70b-versatile). The prompt engineering forces a rigid JSON schema, processing 3 separate semantic vector queries simultaneously (Risks, Growth, Financials) to form a holistic thesis.

🧰 Tech Stack

Framework: FastAPI, Uvicorn

AI & NLP: Groq (Llama-3), Cohere (Embeddings)

Database: Supabase (PostgreSQL + pgvector)

Market Data APIs: SEC EDGAR, Alpaca, FMP, Finnhub, Polygon, FRED (Macro)

Scheduling: APScheduler (Hourly news sweeps)

🗄️ Database Schema (Supabase)

Socrates operates on a strictly typed, relational schema:

soc_company_fundamentals: Caches daily valuation snapshots.

soc_news_articles: Deduplicated news pipeline.

soc_sec_filings & soc_filing_chunks: The pgvector RAG memory bank.

soc_research_intelligence: The final AI output cache.

soc_economic_events: US Macro tracking.

⚙️ Quick Start

Environment Setup: Ensure your .env is populated with keys for Supabase, Groq, Cohere, FMP, Finnhub, Polygon, and Alpaca.

Install Requirements:

pip install -r requirements.txt


Boot the Engine:

uvicorn main:app --reload --port 8000
