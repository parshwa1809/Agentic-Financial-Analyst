I apologize. You are absolutely right—when I added the **Mermaid Workflow Diagrams** (Section 4), I accidentally **removed the "Directory Structure" section** to save space.

That was a mistake. The detailed file breakdown is critical for understanding the codebase.

Here is the **final, fully consolidated `README.md`**. It now includes **everything**:

1.  The **UI Previews** (Images).
2.  The **System Architecture** (Mermaid Graph).
3.  The **Workflows** (Mermaid Sequence/State Diagrams).
4.  The **Directory Structure** (The detailed file tree you asked for).

<!-- end list -->

````markdown
# 📈 Live Stock Analysis Agent & Agentic RAG

## 1. Project Objective
This project is a modern **Financial AI Platform** that acts as an autonomous 
market analyst. It moves beyond simple scripts into a **containerized 
microservices architecture**, combining real-time data ingestion with an AI 
"Council" that debates investment theses.

It uses an **Event-Driven Architecture** where a central API handles user 
requests while background workers asynchronously process massive amounts of 
financial data.

---

## 2. Project Preview

| **Live Dashboard & Financial Metrics** | **AI Analyst & Council Debate** |
|:---:|:---:|
| ![Dashboard Overview](WhatsApp%20Image%202025-11-29%20at%2011.53.33%20AM.jpeg) | ![AI Analysis](WhatsApp%20Image%202025-11-29%20at%2011.53.33%20AM%20(1).jpg) |

---

## 3. System Architecture

The system is split into **three distinct layers**, decoupled to ensure 
scalability and speed.

### 🏛️ High-Level Architecture
The following diagram illustrates how the React Frontend, FastAPI Backend, and 
Python Workers interact with the TiDB Cloud Database and Local AI.

```mermaid
graph TD
    subgraph Client_Side [Frontend Client]
        UI[React / Vite App]
    end

    subgraph Backend_Services [Backend Containers]
        API[FastAPI Server]
        Worker[RQ Worker Process]
        Redis[(Redis Cache)]
    end

    subgraph Data_Layer [Storage & External]
        TiDB[(TiDB Cloud MySQL)]
        FAISS[(Local Vector DB)]
        Ollama[Ollama / Local LLM]
        Alpaca[Alpaca / Yahoo API]
    end

    UI -->|HTTP Requests| API
    API -->|Read Data| TiDB
    API -->|RAG Search| FAISS
    API -->|Chat Prompt| Ollama
    
    API -.->|Schedule Job| Redis
    Redis -.->|Pick Job| Worker
    
    Worker -->|Fetch Data| Alpaca
    Worker -->|Write Data| TiDB
    Worker -->|Write Embeddings| FAISS
````

### 🟢 Layer 1: The Brain (API & AI)

  * **Core:** FastAPI Server (`app/`)
  * **Role:** Handles user interaction and orchestrates the AI agents.
  * **Logic:** Uses **RAG (Retrieval-Augmented Generation)** to fetch relevant
    news and price history from the vector database before answering user questions.

### 🔵 Layer 2: The Face (Frontend)

  * **Core:** React 18 + TypeScript (`client/`)
  * **Role:** A responsive dashboard for visualizing real-time charts, alerts,
    and the AI chat interface.
  * **Tech:** Shadcn UI, Tailwind CSS, TanStack Query.

### 🔴 Layer 3: The Muscle (Background Services)

  * **Core:** Python Workers (`services/`)
  * **Role:** The heavy lifters. These scripts run continuously in the background,
    managed by **Redis**, to fetch data, calculate indicators, and generate alerts
    without slowing down the user interface.

-----

## 4\. Workflows & Logic

### 🔄 Data Ingestion Loop (The Background Worker)

Every 5 minutes, the `rq_worker.py` executes this pipeline to ensure the dashboard
and AI have the freshest data.

```mermaid
stateDiagram-v2
    [*] --> Scheduled_Job: Every 5 Mins
    Scheduled_Job --> Ingestion: run ingestion_price.py
    
    state Ingestion {
        Fetch_API --> Normalize_Data
        Normalize_Data --> Save_to_TiDB
    }
    
    Ingestion --> Indicators: run indicators.py
    state Indicators {
        Calculate_RSI --> Calculate_MACD
        Calculate_MACD --> Update_DB
    }
    
    Indicators --> Alert_Engine: run alert_engine.py
    state Alert_Engine {
        Check_Thresholds --> |If Breach| Generate_Signal
        Generate_Signal --> Save_Alert
    }
    
    Alert_Engine --> [*]
```

### 💬 RAG Chat Pipeline (The Agent Council)

When a user interacts with the AI Analyst, the system aggregates data from
multiple sources before the LLM generates a response.

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI (Chat Router)
    participant RAG as Context Builder
    participant FAISS as Vector DB
    participant Agent as Agent Council
    participant LLM as Ollama (Phi-3)

    User->>API: "Is AAPL a buy?"
    API->>RAG: Build Context(Query, Ticker)
    
    par Parallel Fetch
        RAG->>TiDB: Get Latest Technicals (RSI/MACD)
        RAG->>FAISS: Search Relevant News
    end
    
    RAG-->>API: Return Structured Context
    API->>Agent: Start Council Debate(Context)
    
    loop Debate Round
        Agent->>LLM: Prompt Persona (Risk Manager)
        LLM-->>Agent: "Too risky, RSI is 80"
        Agent->>LLM: Prompt Persona (Tech Analyst)
        LLM-->>Agent: "Bullish trend strong"
    end
    
    Agent-->>API: Final Verdict
    API-->>User: Display Response
```

-----

## 5\. Directory Structure & Service Breakdown

This section details the two core Python modules: `app` (API) and `services`
(Processing).

### 🟢 `app/` Directory (The Brain)

This module handles all HTTP requests and AI orchestration.

```text
app/
├── 🚀 Server Entry
│   └── main.py               # FastAPI Entry: App init, CORS, & Redis connection.
│
├── 📡 Routers (API Endpoints)
│   ├── routers/chat.py       # Chat: Handles user prompts to the LLM.
│   ├── routers/council.py    # Debate: Triggers the multi-agent "Council" workflow.
│   ├── routers/market.py     # Data: Serves live price & indicator JSONs to UI.
│   ├── routers/tickers.py    # Config: Manages the active stock universe.
│   └── routers/debug.py      # System: Health checks & internal diagnostics.
│
└── 🧠 Internal Logic (AI & RAG)
    ├── internal/agent_council.py   # Personas: Defines the "Risk", "Tech", & "Fund" agents.
    └── internal/context_builder.py # RAG: Assembles the prompt context from DB & Vector Store.
```

### 🔴 `services/` Directory (The Muscle)

This module runs in the background to keep data fresh.

```text
services/
├── ⚙️ Orchestration
│   ├── rq_worker.py          # The Manager: Listens to Redis for jobs.
│   ├── redis_manager.py      # The Broker: Handles messaging queues.
│   └── redis_lock.py         # The Traffic Cop: Prevents race conditions.
│
├── 📥 Data Ingestion
│   ├── ingestion_price.py    # Fetches 5-min bar data (Alpaca/Yahoo).
│   ├── ingestion_fund.py     # Fetches fundamental data (P/E, Market Cap).
│   ├── news_fetcher.py       # Scrapes and processes news headlines.
│   └── backfill_alpaca.py    # "Time Machine": Fills historical gaps.
│
├── 🧠 Analysis & Logic
│   ├── indicators.py         # Math: Calculates RSI, MACD, Bollinger Bands.
│   ├── alert_engine.py       # Watchdog: Triggers alerts if signals > threshold.
│   └── relationship_agent.py # Graph: Analyzes correlations between stocks.
│
├── 🚦 Signals Module (AI Pre-processing)
│   ├── signals/technical.py  # Summarizes chart patterns for the AI.
│   ├── signals/sentiment.py  # Summarizes news sentiment for the AI.
│   ├── signals/volume.py     # Analyzes buying/selling pressure.
│   └── signals/calendar.py   # Tracks economic events.
│
└── 🗄️ Database Management
    ├── db_manager.py         # Connection: Manages TiDB Cloud session.
    ├── db_writer.py          # Write: Optimized bulk-insert logic.
    ├── db_pruner.py          # Cleanup: Removes old high-freq data.
    └── setup_db.py           # Init: Creates initial schema/tables.
```

-----

## 6\. Technology Stack

### **Infrastructure**

  * **Docker Compose:** Orchestrates the 4 main containers (API, Client, Worker, Redis).
  * **TiDB Cloud:** Serverless MySQL-compatible database for price/indicator storage.
  * **Redis:** In-memory message broker for the task queue.

### **Backend (Python)**

  * **FastAPI:** High-performance web framework.
  * **Pandas-TA:** Technical Analysis library.
  * **LangChain & Ollama:** Framework for managing the Local LLM (`phi3:mini`).
  * **FAISS:** Vector database for semantic search (RAG).

### **Frontend (TypeScript)**

  * **Vite + React:** Fast build tool and UI library.
  * **Recharts:** For financial charting.

-----

## 7\. Getting Started

### Prerequisites

1.  **Docker & Docker Compose**
2.  **Ollama** running locally (Port 11434)
3.  **TiDB Cloud Account**

### 🚀 Quick Start

**1. Configure Environment**
Create a `.env` file in the root with your credentials:

```env
# Database
DB_URI="mysql+pymysql://USER:PASS@HOST:4000/test?ssl_verify_cert=true"

# APIs
ALPACA_KEY="your_key"
ALPACA_SECRET="your_secret"
NEWS_API_KEY="your_key"

# System
OLLAMA_API_URL="[http://host.docker.internal:11434](http://host.docker.internal:11434)"
BACKFILL_ON_STARTUP=1
```

**2. Launch System**

```bash
docker-compose up --build
```

  * **Frontend:** `http://localhost:3000`
  * **API:** `http://localhost:8000`

-----

## 🔗 Project Resources

  * **▶️ Live Demo:** [Watch on Google Drive](https://drive.google.com/file/d/17CM8klaQCYLM_1woCKoZp3vZIHidr8a6/view?usp=drive_link)
  * **✍️ Medium Article:** [Stop Staring at Charts: Building a Real-Time AI Financial Analyst](https://medium.com/@s.parshwa18/stop-staring-at-charts-building-a-real-time-ai-financial-analyst-with-rag-and-quadratic-context-4de44e67b286?postPublishedType=repub)

<!-- end list -->

```
```