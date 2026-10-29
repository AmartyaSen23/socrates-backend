<div align="center">

<!-- ANIMATED HERO WAVE BANNER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=0:04070d,35:064e3b,70:0f766e,100:0284c7&height=230&section=header&text=SOCRATES%20AI%20%E2%80%94%20CORE%20ENGINE&fontSize=42&fontColor=ffffff&fontAlignY=38&desc=Autonomous%20Quantitative%20Research%20%E2%80%A2%20SEC%20EDGAR%20XBRL%20%E2%80%A2%20Multi-Query%20pgvector%20RAG%20%E2%80%A2%20Groq%20LPU%20Inference&descAlignY=60&descSize=15&animation=fadeIn" width="100%" alt="Socrates AI Backend Banner" />

<!-- ANIMATED TYPING TELEMETRY SVG -->
<a href="https://socrates-frontend.vercel.app">
  <img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=18&duration=2600&pause=900&color=10B981&center=true&vCenter=true&width=920&lines=%E2%9A%A1+Sub-500ms+Tier-1+PostgreSQL+Cache+Barrier+%26+Multi-Model+Groq+LPU+Synthesis;%F0%9F%8F%9B%EF%B8%8F+Audited+SEC+EDGAR+XBRL+(US-GAAP+%26+IFRS)+%2B+5-Layer+Valuation+Cascade;%F0%9F%94%AC+Non-Blocking+10-K+%2F+20-F+%2F+40-F+iXBRL+Scrubber+%E2%86%92+Cohere+v3+%E2%86%92+Supabase+pgvector;%F0%9F%9B%B0%EF%B8%8F+Autonomous+APScheduler+Daemons%3A+10m+SEC+RSS+%E2%80%A2+1h+Benzinga+News+%E2%80%A2+24h+XBRL" alt="Typing Telemetry SVG" />
</a>

<br />

<!-- TECH STACK & LIVE STATUS BADGES -->
<p align="center">
  <a href="https://socrates-frontend.vercel.app"><img src="https://img.shields.io/badge/LIVE_TERMINAL-ONLINE-10B981?style=for-the-badge&logo=vercel&logoColor=white" alt="Live Terminal" /></a>
  <a href="https://socrates-backend-kbyq.onrender.com"><img src="https://img.shields.io/badge/API_ENGINE-v1.1.0-06B6D4?style=for-the-badge&logo=fastapi&logoColor=white" alt="API Version" /></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.111.0-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/Groq_LPU-Llama_3.3_70B-F55036?style=for-the-badge&logo=meta&logoColor=white" alt="Groq" />
  <img src="https://img.shields.io/badge/Cohere-Embed_v3.0-39594D?style=for-the-badge&logo=cohere&logoColor=white" alt="Cohere" />
  <img src="https://img.shields.io/badge/SEC_EDGAR-XBRL_%26_RSS-005587?style=for-the-badge&logo=gov.uk&logoColor=white" alt="SEC EDGAR" />
</p>

<!-- QUICK NAVIGATION BAR -->
<p align="center">
  <a href="#-executive-telemetry-scorecard"><kbd>📊 Telemetry</kbd></a> •
  <a href="#️-end-to-end-system-architecture"><kbd>🏗️ Architecture</kbd></a> •
  <a href="#-5-layer-valuation--xbrl-cascade"><kbd>💎 5-Layer Cascade</kbd></a> •
  <a href="#-deep-sec-rag--cohere-pgvector-engine"><kbd>🔬 Deep SEC RAG</kbd></a> •
  <a href="#-dynamic-5-model-groq-failover-mesh"><kbd>🤖 LLM Failover</kbd></a> •
  <a href="#️-supabase-postgresql--pgvector-schema"><kbd>🗄️ DB Schema</kbd></a> •
  <a href="#-api-gateway-reference"><kbd>📡 API Matrix</kbd></a>
</p>

</div>

---

## 📊 Executive Telemetry Scorecard

<table>
  <tr>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/CACHE_HIT_LATENCY-%3C_450ms-10B981?style=for-the-badge" alt="Latency" /><br />
      <sub><b>Tier-1 PostgreSQL Intercept</b><br />Bypasses LLM & Vector compute on same-day `(ticker, date, mode)` hits</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/VALUATION_UPTIME-99.9%25-06B6D4?style=for-the-badge" alt="Valuation Uptime" /><br />
      <sub><b>2-Phase XBRL + 5-Layer Cascade</b><br />SEC EDGAR GAAP/IFRS + FMP → Finnhub → Polygon → YFinance → Math</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/RAM_FOOTPRINT-%3C_512MB-8B5CF6?style=for-the-badge" alt="Memory Footprint" /><br />
      <sub><b>OOM-Proof Local iXBRL Scrubber</b><br />Regex stream-stripping for filings &gt;3MB prior to 1500-char chunking</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/LLM_RESILIENCE-5_MODELS-F59E0B?style=for-the-badge" alt="LLM Resilience" /><br />
      <sub><b>Self-Healing Groq Router</b><br />Auto-rotates across 5 reasoning models on HTTP 429/503 or token overflow</sub>
    </td>
  </tr>
</table>

---

## 🏗️ End-to-End System Architecture

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#0f172a', 'primaryTextColor': '#f8fafc', 'primaryBorderColor': '#10b981', 'lineColor': '#06b6d4', 'secondaryColor': '#1e293b', 'tertiaryColor': '#090d16'}}}%%
flowchart TB
    subgraph Client["🖥️ SOCRATES NEXT.JS 16 TERMINAL"]
        UI["Command Bar & Workspace<br/>(Fast Research / Deep SEC RAG)"]
        Term["Immortal Telemetry Console<br/>(1.5s Polling Stream)"]
    end

    subgraph Gateway["⚡ FASTAPI ASYNC GATEWAY (app/main.py & routers/ingestion.py)"]
        Router["/api/v1/ingestion/*<br/>Ticker Sanitizer + Yahoo Fuzzy Search"]
        StatusStore["Thread-Safe Status Store (app/status_store.py)<br/>OrderedDict(100 Tickers × 150 Logs) + Secret Redactor + Atomic Locks"]
        Scheduler["APScheduler Daemon (app/scheduler.py)<br/>• 10m SEC EDGAR Atom RSS Listener<br/>• 1h Watchlist News Sync<br/>• 24h Watchlist XBRL Sync"]
    end

    subgraph Services["🧠 AUTONOMOUS SERVICE LAYER (app/services/*)"]
        CacheBarrier{"Tier-1 Cache Barrier<br/>(soc_research_intelligence)"}
        XBRL["XBRLService<br/>Phase 1: SEC GAAP/IFRS Facts<br/>Phase 2: 5-Layer Price Cascade"]
        News["NewsService<br/>3-Layer Institutional Stream<br/>+ Regex Dynamic Entity Gate"]
        SEC["SECService & VectorService<br/>10-K/20-F/40-F Scrubber + Debt Regex<br/>→ 1500c Chunks → Cohere v3"]
        FRED["FredService<br/>US Macro Indicators<br/>(CPI, GDP, UNRATE, FEDFUNDS)"]
        Agent["AgentService<br/>3-Query RAG Aggregation<br/>+ 5-Model Groq JSON Synthesis"]
    end

    subgraph CloudDB["🗄️ SUPABASE POSTGRESQL + PGVECTOR + STORAGE"]
        DB_Int[("soc_research_intelligence")]
        DB_Fund[("soc_company_fundamentals")]
        DB_News[("soc_news_articles")]
        DB_Sec[("soc_sec_filings &<br/>sec-filings-raw Bucket")]
        DB_Vec[("soc_filing_chunks<br/>pgvector + match_filing_chunks RPC")]
        DB_Macro[("soc_economic_events")]
        DB_Watch[("soc_watchlist &<br/>soc_feedbacks")]
    end

    UI ==>|"POST /analyze/{ticker}<br/>POST /analyze/deep/{ticker}"| Router
    Term -.->|"GET /status/{ticker}"| StatusStore
    Router --> CacheBarrier
    CacheBarrier ==>|"⚡ Cache Hit (<450ms)"| UI
    CacheBarrier -->|"Cache Miss"| XBRL & News & SEC & FRED
    Scheduler --> XBRL & News & SEC

    XBRL --> DB_Fund
    News --> DB_News
    SEC --> DB_Sec --> DB_Vec
    FRED --> DB_Macro

    DB_Fund & DB_News & DB_Vec & DB_Macro --> Agent
    Agent -->|"Upsert Validated 9-Field JSON"| DB_Int
    DB_Int ==> UI
```

---

## 💎 5-Layer Valuation & XBRL Cascade

Standard financial wrappers break when cloud IPs are rate-limited or when analyzing foreign ADRs (`20-F` / `40-F`). [`XBRLService`](file:///C:/Users/Amart/Desktop/Projects/socrates_backend/app/services/xbrl_service.py) solves this with a **2-Phase Audited Accounting + 5-Layer Valuation Cascade**:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#0f172a', 'primaryTextColor': '#e2e8f0', 'primaryBorderColor': '#06b6d4', 'lineColor': '#10b981'}}}%%
flowchart LR
    Start(["🎯 Target Ticker"]) --> Cache{"Same-Day DB Cache?<br/>(soc_company_fundamentals)"}
    Cache -->|"HIT"| Return(["✅ Return Cached Row"])
    Cache -->|"MISS"| Phase1

    subgraph Phase1["🏛️ PHASE 1: OFFICIAL SEC EDGAR XBRL"]
        CIK["24h Thread-Safe CIK Map<br/>(Supports BRK-B & BRK.B)"] --> Tax["Taxonomy Parser<br/>(us-gaap & ifrs-full)"]
        Tax --> USD["Strict USD / Pure Unit Filter<br/>(Blocks INR/TWD/EUR Mismatch)"]
        USD --> Facts["Extract Latest Annual Facts:<br/>• Revenue (330-385d FY Window)<br/>• Diluted EPS<br/>• Total Debt"]
    end

    Phase1 --> L1

    subgraph Phase2["⚡ PHASE 2: 5-LAYER FAIL-FAST VALUATION CASCADE"]
        L1["Layer A: FMP Profile<br/>(/api/v3/profile & /stable/profile)"] -->|"Missing / 403"| L2["Layer B: Finnhub Gateway<br/>(/quote + /stock/profile2 + /metric)"]
        L2 -->|"Missing"| L3["Layer C: Polygon.io<br/>(/v2/aggs/prev + /v3/reference)"]
        L3 -->|"Missing"| L4["Layer D: YFinance<br/>(fast_info Price & Market Cap)"]
        L4 -->|"P/E Missing"| L5["Layer E: Math Derivation<br/>(P/E = Live Price ÷ Diluted EPS)"]
    end

    L1 & L2 & L3 -.->|"Explicit $0 / Empty & Unverified CIK"| Abort(["🛑 FAIL-FAST ABORT<br/>+ Yahoo Fuzzy Suggestions"])
    L5 --> Upsert[("💾 Upsert to Supabase<br/>soc_company_fundamentals")]
```

---

## 🔬 Deep SEC RAG & Cohere `pgvector` Engine

Massive `10-K`, `20-F`, `40-F`, and `10-Q` filings often exceed **15MB–40MB** of raw iXBRL markup, crashing standard cloud instances with `512MB RAM` limits or triggering `HTTP 504` gateway timeouts. [`SECService`](file:///C:/Users/Amart/Desktop/Projects/socrates_backend/app/services/sec_service.py) and [`VectorService`](file:///C:/Users/Amart/Desktop/Projects/socrates_backend/app/services/vector_service.py) execute an asynchronous, memory-bounded pipeline:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'actorBkg': '#0f172a', 'actorBorder': '#10b981', 'actorTextColor': '#f8fafc', 'signalColor': '#06b6d4', 'signalTextColor': '#e2e8f0'}}}%%
sequenceDiagram
    autonumber
    participant UI as 🖥️ Next.js Terminal
    participant API as ⚡ FastAPI Router
    participant Lock as 🔒 Atomic Lock & StatusStore
    participant SEC as 📄 SECService (Local Scrubber)
    participant Vec as 🧬 VectorService + Cohere v3
    participant DB as 🗄️ Supabase (Storage + pgvector)

    UI->>API: POST /api/v1/ingestion/analyze/deep/{ticker}
    API->>DB: Check soc_sec_filings (is_ready)
    alt Filing Not Vectorized Yet
        API->>Lock: try_acquire_vectorization(ticker)
        API-->>UI: HTTP 400 ("Vectorization started in background...")
        par BackgroundTask Non-Blocking Execution
            SEC->>SEC: Download 10-K / 20-F / 40-F to tempfile
            SEC->>SEC: Regex isolate <DOCUMENT><TEXT> & strip <ix:hidden>/<svg>
            SEC->>SEC: Low-RAM Regex Stripper (if >3MB) or BeautifulSoup (<3MB)
            SEC->>SEC: Contextual Regex Total Debt Backfill ($M/$B/$T)
            SEC->>DB: Upload clean prose to `sec-filings-raw` bucket
            Vec->>Vec: RecursiveCharacterTextSplitter (1500 chars, 200 overlap)
            loop Batches of 90 Chunks (with 60s Rate-Limit Cooldown)
                Vec->>Vec: Cohere `embed-english-v3.0` (input_type: search_document)
                Vec->>DB: Bulk Insert into `soc_filing_chunks` (pgvector)
                Vec->>Lock: log_update("Successfully inserted chunks...")
            end
            Vec->>DB: UPDATE soc_sec_filings SET is_ready = True
            Vec->>Lock: release_vectorization(ticker)
        and Frontend Immortal Telemetry Polling (Every 1.5s)
            UI->>Lock: GET /api/v1/ingestion/status/{ticker}
            Lock-->>UI: Stream live chunk progress + sec_ready = true
        end
    else Filing Ready (is_ready == True)
        API->>Vec: Embed 3 Simultaneous Queries (Risks, Growth, Margins)
        Vec->>DB: RPC `match_filing_chunks` (Adaptive Threshold: 0.25 → 0.12)
        DB-->>API: Top 6 Deduplicated SEC Excerpts
        API-->>UI: 200 OK — Enriched Deep SEC RAG Report
    end
```

---

## 🤖 Dynamic 5-Model Groq Failover Mesh

To guarantee **zero downtime** when LLM providers experience rate limits (`HTTP 429`), capacity spikes (`HTTP 503`), model deprecations (`HTTP 404`), or JSON truncation, [`AgentService`](file:///C:/Users/Amart/Desktop/Projects/socrates_backend/app/services/agent_service.py) implements an autonomous model rotation and schema normalization state machine:

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#0f172a', 'primaryBorderColor': '#10b981', 'lineColor': '#06b6d4'}}}%%
stateDiagram-v2
    [*] --> PrimaryModel: Initialize Inference (max_tokens=4096)

    state "1️⃣ llama-3.3-70b-versatile" as PrimaryModel
    state "2️⃣ openai/gpt-oss-120b" as Fallback1
    state "3️⃣ qwen/qwen3-32b" as Fallback2
    state "4️⃣ llama-3.1-8b-instant" as Fallback3
    state "5️⃣ gemma2-9b-it / Dynamic API Probe" as Fallback4
    state "🧹 Schema Normalizer (_parse_and_normalize_report)" as Normalizer

    PrimaryModel --> Normalizer: HTTP 200 JSON
    PrimaryModel --> Fallback1: 429 / 503 / 404 / Token Limit (max_tokens → 8192)
    Fallback1 --> Normalizer: HTTP 200 JSON
    Fallback1 --> Fallback2: 429 / 503 / JSON Error
    Fallback2 --> Normalizer: HTTP 200 JSON
    Fallback2 --> Fallback3: 429 / 503 / JSON Error
    Fallback3 --> Normalizer: HTTP 200 JSON
    Fallback3 --> Fallback4: 429 / 503 / JSON Error
    Fallback4 --> Normalizer: HTTP 200 JSON

    state Normalizer {
        [*] --> StripThink: Strip <think>...</think> & Markdown Fences
        StripThink --> ClampScores: Clamp Sentiment, Bull, Risk, Confidence [0..100]
        ClampScores --> EnforceArrays: Guarantee 3 Growth Drivers & 3 Major Risks
    }

    Normalizer --> [*]: Upsert to `soc_research_intelligence`
```

---

## 📰 3-Layer Institutional News & Dynamic Entity Gate

Syndicated financial feeds frequently tag mega-cap tickers (`NVDA`, `AAPL`) or single-letter tickers (`F`, `T`, `C`) in unrelated market roundups. [`NewsService`](file:///C:/Users/Amart/Desktop/Projects/socrates_backend/app/services/news_service.py) enforces a strict **30-minute cache barrier**, a **3-provider cascade**, and a **Regex Dynamic Entity Gate**:

| Layer | Provider | Timeout / Strategy | Dynamic Entity Gate (`_matches_entity_gate`) |
| :--- | :--- | :--- | :--- |
| **Layer 1** | **Alpaca Benzinga SDK** | `ThreadPoolExecutor` (`10.0s` hard timeout, non-blocking shutdown) | 1. Word-boundary regex on `$TICKER` (`(?<![a-z0-9])\$?ticker(?![a-z0-9])`)<br/>2. Strips corporate/ADR suffixes (`Inc.`, `Corp.`, `Class A`, `Sponsored ADR`)<br/>3. If tagged with `&gt;4` symbols, requires entity match **in headline** |
| **Layer 2** | **Finnhub Company News** | `6.0s` REST fallback (`30-day` window) | Filters up to 20 articles through the same compiled entity regex patterns |
| **Layer 3** | **Polygon.io Reference News** | `6.0s` emergency REST gateway | URL deduplication map prior to PostgreSQL `ON CONFLICT (url)` batch upsert |

---

## 🗄️ Supabase PostgreSQL & `pgvector` Schema

```mermaid
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#0f172a', 'primaryTextColor': '#f8fafc', 'primaryBorderColor': '#10b981', 'lineColor': '#06b6d4'}}}%%
erDiagram
    SOC_COMPANY_FUNDAMENTALS ||--o{ SOC_RESEARCH_INTELLIGENCE : "enriches"
    SOC_NEWS_ARTICLES ||--o{ SOC_RESEARCH_INTELLIGENCE : "contextualizes"
    SOC_SEC_FILINGS ||--|{ SOC_FILING_CHUNKS : "10-K / 20-F chunks"
    SOC_WATCHLIST ||--o{ SOC_SEC_FILINGS : "RSS auto-triggers"

    SOC_RESEARCH_INTELLIGENCE {
        uuid id PK
        varchar ticker "Indexed"
        date analysis_date "Composite Unique Key"
        boolean is_deep_rag "Fast vs Deep RAG"
        int sentiment_score "0-100"
        varchar sentiment_label "Bullish | Bearish | Neutral"
        int risk_score "0-100"
        jsonb major_risks "3 Verified Headwinds"
        int bullish_score "0-100"
        jsonb growth_drivers "3 Verified Catalysts"
        int confidence_score "0-100"
        text bull_case_summary "Institutional Paragraph"
        text bear_case_summary "Institutional Paragraph"
    }

    SOC_COMPANY_FUNDAMENTALS {
        varchar ticker PK
        date fiscal_date PK
        bigint market_cap
        bigint revenue "Audited SEC XBRL"
        bigint total_debt "XBRL + Prose Regex Backfill"
        float eps "Diluted EPS"
        float pe_ratio "Live or Derived"
    }

    SOC_SEC_FILINGS {
        uuid id PK
        varchar ticker
        varchar form_type "10-K | 20-F | 40-F | 10-Q"
        date filed_at
        text storage_bucket_url "sec-filings-raw path"
        boolean is_ready "Vectorization Barrier"
    }

    SOC_FILING_CHUNKS {
        uuid id PK
        uuid filing_id FK
        varchar ticker
        text chunk_content "1500 chars / 200 overlap"
        vector embedding "Cohere 1024-dim pgvector"
        int page_number
    }

    SOC_NEWS_ARTICLES {
        text url PK
        varchar ticker
        text title
        text summary
        timestamptz published_at
    }

    SOC_ECONOMIC_EVENTS {
        varchar event_name PK "CPI | GDP | UNRATE | FEDFUNDS"
        date released_at PK
        float actual_value
    }

    SOC_WATCHLIST {
        varchar ticker PK
        boolean is_active
        timestamptz last_news_pull
        timestamptz last_fund_pull
    }

    SOC_FEEDBACKS {
        uuid id PK
        varchar user_name
        varchar user_role
        int rating "1-5 Stars"
        varchar category
        varchar ticker_context
        text message
    }
```

---

## 📡 API Gateway Reference (`/api/v1/ingestion`)

| Method | Endpoint | Service Orchestration | Description |
| :---: | :--- | :--- | :--- |
| `POST` | `/analyze/{ticker}` | `XBRL` + `News` + `SEC (Async)` + `Agent` | Executes **Fast Research** (`use_rag=False`) and silently launches background SEC vectorization if missing. |
| `POST` | `/analyze/deep/{ticker}` | `XBRL` + `SEC` + `Vector` + `News` + `Agent` | Executes **Multi-Query Deep SEC RAG** (`use_rag=True`) or auto-repairs/initiates background indexing (`HTTP 400`). |
| `GET` | `/status/{ticker}` | `status_store` + `soc_sec_filings` | Streams bounded live execution logs (`MAX=150`), `is_vectorizing` lock state, and `sec_ready` metadata. |
| `GET` | `/report/{ticker}` | `AgentService` | Instant zero-LLM retrieval of a cached report snapshot with latest fundamentals, news, and SEC status. |
| `GET` | `/history` | `ingestion.py` | Curated **Intelligence Vault** feed supporting `unique_only=true` or `min_days_apart=7` temporal deduplication. |
| `GET` / `POST` | `/macro` | `FredService` | Reads or ingests live Federal Reserve (FRED) US CPI, GDP, Unemployment, and Fed Funds Rate indicators. |
| `GET` | `/search` | `ingestion.py` | Live Yahoo Finance equity autocomplete (`?q=`) for the command bar and fuzzy error recovery. |
| `GET`/`POST`/`DELETE` | `/watchlist/{ticker}` | `ingestion.py` + `APScheduler` | Manages active equities tracked by the autonomous background cron jobs. |
| `GET` / `POST` | `/feedback` | `ingestion.py` | Reads and stores verified 5-star institutional telemetry reviews in `soc_feedbacks`. |

---

## 📂 Repository Blueprint

```text
socrates_backend/
├── app/
│   ├── main.py                      # FastAPI v1.1.0 entry point, CORS regex rules & APScheduler lifespan
│   ├── config.py                    # Pydantic BaseSettings (.env loader for 9 cloud credentials)
│   ├── database.py                  # Singleton Supabase PostgreSQL + Storage client
│   ├── scheduler.py                 # Coalesced BackgroundScheduler (10m SEC RSS, 1h News, 24h XBRL)
│   ├── status_store.py              # Thread-safe LRU log ring buffer + Secret Redactor + Atomic Locks
│   ├── routers/
│   │   └── ingestion.py             # 12 REST endpoints + ticker validation + fuzzy suggestion engine
│   └── services/
│       ├── agent_service.py         # Tier-1 Cache Barrier + 3-Query RAG + 5-Model Groq Failover
│       ├── xbrl_service.py          # SEC EDGAR XBRL parser (US-GAAP/IFRS) + 5-Layer Valuation Cascade
│       ├── sec_service.py           # 10-K/20-F/40-F downloader, OOM-safe HTML scrubber & Debt regex
│       ├── vector_service.py        # LangChain chunker (1500/200) + Cohere v3 batch embedder -> pgvector
│       ├── sec_listener_service.py  # Live SEC EDGAR Atom RSS scanner matching watchlist CIKs
│       ├── news_service.py          # Alpaca Benzinga -> Finnhub -> Polygon cascade + Entity Gate
│       └── fred_service.py          # St. Louis Fed (FRED) macroeconomic telemetry collector
└── requirements.txt                 # Pinned production dependencies
```

---

## 🚀 Quick Start & Environment Setup

### 1. Configure `.env` Credentials
Create a `.env` file in the root of `socrates_backend`:

```ini
# Required Core Infrastructure
SUPABASE_URL="https://your-project.supabase.co"
SUPABASE_KEY="your-supabase-service-or-anon-key"
GROQ_API_KEY="gsk_..."
COHERE_API_KEY="your-cohere-v3-key"

# Institutional Market, News & Macro Gateways
FRED_API_KEY="your-st-louis-fed-key"
ALPACA_API_KEY="PK..."
ALPACA_SECRET="your-alpaca-secret"
FMP_API_KEY="your-fmp-key"
FINNHUB_API_KEY="your-finnhub-key"
POLYGON_API_KEY="your-polygon-key"
```

### 2. Install & Launch the Engine

```bash
# Install pinned dependencies
pip install -r requirements.txt

# Launch the FastAPI Uvicorn server with hot-reload
uvicorn app.main:app --reload --port 8000
```

---

<div align="center">

### 👨‍💻 System Architect

**Amartya Sen**  
*B.Tech in Computer Science & Engineering (Artificial Intelligence & Machine Learning)*  
Architecting fault-tolerant, autonomous AI systems at the intersection of quantitative finance and deep learning.

<p align="center">
  <a href="https://www.linkedin.com/in/amartya-sen"><img src="https://img.shields.io/badge/LinkedIn-Amartya_Sen-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white" alt="LinkedIn" /></a>
  <a href="https://github.com/AmartyaSen23"><img src="https://img.shields.io/badge/GitHub-@AmartyaSen23-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub" /></a>
  <a href="https://socrates-frontend.vercel.app"><img src="https://img.shields.io/badge/Launch-Socrates_Terminal-10B981?style=for-the-badge&logo=vercel&logoColor=white" alt="Live Demo" /></a>
</p>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:04070d,50:064e3b,100:0284c7&height=110&section=footer" width="100%" alt="Footer Wave" />

</div>
