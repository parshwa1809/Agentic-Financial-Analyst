from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
# Wrap imports in try/except to prevent crashes if libraries are missing
try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import SystemMessage, HumanMessage
except ImportError:
    print("⚠️ Warning: LangChain/Ollama libraries not found. Chat will be disabled.")
    ChatOllama = None

from sqlalchemy import text
from services.db_manager import get_engine
import os
import traceback

router = APIRouter()
engine = get_engine()

# Configuration
LLM_MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")
LLM_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")

# Global variable for lazy loading
_llm_instance = None

def get_llm():
    """Lazy load the LLM connection to prevent startup crashes."""
    global _llm_instance
    if _llm_instance is None:
        if ChatOllama is None:
            raise Exception("LangChain library missing.")
        print(f"🔌 Connecting to Ollama at {LLM_URL}...")
        _llm_instance = ChatOllama(base_url=LLM_URL, model=LLM_MODEL, temperature=0.3)
    return _llm_instance

class ChatRequest(BaseModel):
    message: str
    ticker: str = None

def get_stock_context(ticker: str):
    if not ticker: return "No active ticker selected. Answer general questions."
    
    try:
        with engine.connect() as conn:
            # 1. Get Latest Price
            price_row = conn.execute(text(
                "SELECT close, volume FROM market_data WHERE ticker=:t ORDER BY timestamp DESC LIMIT 1"
            ), {"t": ticker}).fetchone()
            
            # 2. Get Recent News
            news_rows = conn.execute(text(
                "SELECT headline, sentiment_score FROM news_articles WHERE ticker=:t ORDER BY published_at DESC LIMIT 2"
            ), {"t": ticker}).fetchall()
            
            # 3. Get Risk Score
            risk_row = conn.execute(text(
                "SELECT AVG(risk_score) FROM political_risk WHERE ticker=:t"
            ), {"t": ticker}).fetchone()

        context = f"REAL-TIME DATA FOR {ticker}:\n"
        if price_row:
            context += f"- Price: ${price_row[0]:.2f} | Vol: {price_row[1]}\n"
        else:
            context += "- Price: Data Unavailable\n"
        
        if risk_row and risk_row[0] is not None:
            context += f"- Risk Score: {float(risk_row[0]):.1f}/100\n"
            
        if news_rows:
            context += "- Headlines:\n"
            for n in news_rows:
                context += f"  * {n[0]} (Score: {n[1]})\n"
        return context

    except Exception as e:
        print(f"⚠️ Context Fetch Error: {e}")
        return "Market data unavailable."

@router.post("/ask")
def chat(request: ChatRequest):
    try:
        # 1. Get LLM (Lazy Load)
        llm = get_llm()
        
        # 2. Build Context
        context_data = get_stock_context(request.ticker)
        
        # 3. Define Prompt
        system_prompt = (
            "You are a helpful Financial Analyst AI. "
            "Use the provided DATA CONTEXT to answer. "
            "If the user asks about price/news/risk, quote the context. "
            "Keep answers concise (under 3 sentences)."
        )
        
        user_prompt = f"DATA CONTEXT:\n{context_data}\n\nUSER QUESTION:\n{request.message}"
        
        # 4. Invoke
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ])
        
        return {"response": response.content}

    except Exception as e:
        print(f"❌ CHAT ERROR: {e}")
        traceback.print_exc()
        return {"response": "I am currently offline or cannot connect to the brain. Please check the server logs."}