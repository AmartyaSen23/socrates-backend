# 🏛️ Socrates AI: Autonomous Quantitative Research Engine (Core Backend)
![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111.0-009688.svg)
![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E.svg)
![Groq](https://img.shields.io/badge/Groq-Llama_3.3_70B-F55036.svg)
![Cohere](https://img.shields.io/badge/Cohere-Embed_v3.0-39594D.svg)
![SEC_EDGAR](https://img.shields.io/badge/SEC_EDGAR-Automated_Ingestion-005587.svg)
## 🧠 Overview

The Socrates Backend is a fully autonomous, production-ready data engineering and AI inference pipeline. Built on an asynchronous FastAPI architecture, it intercepts real-time institutional news, official SEC Edgar filings, and live market valuations.

Unlike standard wrapper applications, Socrates feeds this multi-dimensional data into a custom Retrieval-Augmented Generation (RAG) pipeline powered by Cohere and Groq to synthesize structured, institutional-grade quantitative stock intelligence at sub-second latencies.

## ✨ Key Technical Achievements (The "Wow" Factor)

### 1. The 5-Layer "Fail-Fast" Valuation Cascade

Market data APIs actively block cloud servers to deter bot traffic. To guarantee a 100% success rate for structural valuation metrics, Socrates utilizes an aggressive, self-healing 5-layer cascade:

Layer A (SEC & Alpaca): The "True Engineer" approach. Pulls live price from the Alpaca broker SDK and multiplies it by the official SEC SharesOutstanding XBRL tag.

Layer B (FMP & Finnhub): Primary authenticated attempts for live Market Cap, P/E, and EPS.

Layer C (Polygon.io): Emergency authenticated gateway cascade.

Layer D (Mathematical Derivation): Reconstructing missing Market Caps mathematically via 30-day historical share floats and 5-day close prices.

Strict Fail-Fast Logic: Instantly aborts and halts the pipeline if an API explicitly returns a $0.00 price or empty matrix, identifying fake tickers (e.g., NIFTY) to protect API limit burn.

### 2. Deep SEC RAG Vectorization Engine

Socrates automatically downloads, cleans, and chunks massive 10-K and 20-F SEC filings on demand without blocking the main event loop.

Semantic Slicing: Uses LangChain's RecursiveCharacterTextSplitter (1500 chars, 200 overlap) to preserve financial context.

Cloud Embedding: Batches text arrays to generate embed-english-v3.0 vectors via the Cohere API.

Direct pgvector Injection: Performs bulk asynchronous inserts directly into a Supabase PostgreSQL database.

Non-Blocking Orchestration: Orchestrates via FastAPI BackgroundTasks, allowing the frontend to poll status independently without triggering HTTP 504 Timeouts.

### 3. The "Cache Barrier" & Cost Optimization

To optimize Groq API costs and reduce latency to <0.5s, the AgentService implements a strict PostgreSQL intercept. If an identical report (Standard or Deep RAG) was generated for a requested ticker today, it fetches the JSON payload directly from Supabase, bypassing all heavy LLM computation and vector math.

### 4. Advanced NLP Ensemble

Leverages the Groq API to run Llama-3.3-70b-versatile at blazing inference speeds. The prompt engineering enforces a rigid JSON schema, processing 3 separate semantic vector queries simultaneously (Risks, Growth, Financials) alongside live Alpaca/Benzinga news streams to synthesize a holistic, conflict-free trading thesis.

## 🏗️ System Architecture

Sourcing Pipeline: Multithreaded ingestion of US Macro data (FRED), Institutional News (Alpaca), and Accounting Data (SEC EDGAR).

Vectorization Engine: Asynchronous text chunking -> Cohere embeddings -> Supabase pgvector storage.

Inference Engine: Multi-query RAG -> Context Aggregation -> Llama 3 70B JSON inference.

Resilience Layer: Exponential backoffs, fail-fast validations, and strict database constraint barriers.

## 🛠️ Tech Stack & Requirements

Framework & Server: fastapi (0.111.0), uvicorn (0.30.1), pydantic (2.13.3)

AI & Vectorization: groq (1.4.0), langchain-text-splitters (1.1.2)

Database & Cloud: supabase (2.5.1) (PostgreSQL + pgvector)

Market Data & Scraping: alpaca-trade-api (3.2.0), yfinance (0.2.41), sec-edgar-downloader (5.1.0), beautifulsoup4 (4.13.4)

Parsing & Scheduling: requests (2.32.3), feedparser (6.0.12), APScheduler (3.11.2)

## 🚀 Deployment

This system is designed for stateless deployment.

```
# Install exact requirements
pip install -r requirements.txt

# Boot the engine in development mode
uvicorn main:app --reload --port 8000
```

(Note: Requires active SUPABASE_URL, GROQ_API_KEY, COHERE_API_KEY, APCA_API_KEY_ID, and APCA_API_SECRET_KEY in the .env file).

## 👨‍💻 Author

Amartya Sen | B.Tech in Artificial Intelligence and Machine Learning (Core CSE with Specialization)
Architecting resilient, autonomous AI systems at the intersection of quantitative finance and deep learning.
