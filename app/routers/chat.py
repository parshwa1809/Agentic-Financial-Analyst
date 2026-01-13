import os
import json
import requests
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import text
from services.db_manager import get_engine
from services.redis_manager import get_redis_client

router = APIRouter()
engine = get_engine()
redis = get_redis_client()

# --- CONFIGURATION ---
# Robust URL handling: Ensures we always hit the correct endpoint
# This fixes the issue where the URL might be missing '/api/generate'
BASE_OLLAMA_URL = os.getenv('OLLAMA_API_URL', 'http://host.docker.internal:11434')
if not BASE_OLLAMA_URL.endswith('/api/generate'):
    if BASE_OLLAMA_URL.endswith('/'):
        BASE_OLLAMA_URL += 'api/generate'
    else:
        BASE_OLLAMA_URL += '/api/generate'

MODEL = os.getenv('OLLAMA_MODEL_NAME', 'llama3')

class ChatRequest(BaseModel):
    message: str
    ticker: Optional[str] = None
    session_id: str = 'default'

# --- CONTEXT BUILDERS ---

def get_supply_chain_context(ticker: str):
    """Fetches discovered supply chain partners from the database."""
    if not ticker: return ''
    try:
        with engine.connect() as conn:
            # Fetch top 8 partners sorted by confidence
            query = text("""
                SELECT partner_ticker, relationship, reason 
                FROM supply_chain 
                WHERE ticker = :t 
                ORDER BY confidence DESC LIMIT 8
            """)
            rows = conn.execute(query, {'t': ticker}).fetchall()
            
            if not rows: return 'No specific supply chain data found in memory.'
            
            text_list = []
            for r in rows:
                # Format: "- TSM (SUPPLIER): Manufactures chips"
                text_list.append(f'- {r[0]} ({r[1]}): {r[2]}')
            
            return 'SUPPLY CHAIN NETWORK:\n' + '\n'.join(text_list)
    except Exception as e:
        print(f'Supply Chain Context Error: {e}')
        return ''

def get_stock_context(ticker: str):
    """Fetches real-time price and latest news."""
    if not ticker: return 'No active ticker. Answer general questions.'
    try:
        with engine.connect() as conn:
            price = conn.execute(text('SELECT close FROM market_data WHERE ticker=:t ORDER BY timestamp DESC LIMIT 1'), {'t': ticker}).fetchone()
            news = conn.execute(text('SELECT headline FROM news_articles WHERE ticker=:t ORDER BY published_at DESC LIMIT 1'), {'t': ticker}).fetchone()

        context = f'REAL-TIME DATA FOR {ticker}:\n'
        context += f'- Price: ${price[0]:.2f}\n' if price else '- Price: N/A\n'
        context += f'- Latest Headline: {news[0]}\n' if news else ''
        return context
    except Exception:
        return 'Market data currently unavailable.'

# --- MAIN ENDPOINT ---

@router.post('/ask')
def chat(request: ChatRequest):
    try:
        # 1. Gather Context
        data_context = get_stock_context(request.ticker)
        sc_context = get_supply_chain_context(request.ticker)
        
        # 2. Build the System Prompt
        # We inject the retrieved supply chain data directly into the prompt
        system_prompt = f"""
        You are an elite financial analyst AI. 
        
        [MARKET DATA]
        {data_context}
        
        [SUPPLY CHAIN INTELLIGENCE]
        {sc_context}
        
        [USER QUESTION]
        {request.message}
        
        INSTRUCTIONS:
        1. Use the 'Supply Chain Intelligence' above to answer questions about suppliers or risks.
        2. If the data lists a partner (e.g. TSM), explicitly mention them.
        3. Be concise, professional, and data-driven.
        """

        # 3. Call Ollama Directly
        payload = {
            'model': MODEL,
            'prompt': system_prompt,
            'stream': False
        }
        
        print(f'Sending Request to: {BASE_OLLAMA_URL} for {request.ticker}')
        
        # High timeout to give the LLM time to think
        res = requests.post(BASE_OLLAMA_URL, json=payload, timeout=90)
        
        if res.status_code == 200:
            # Parse the response (Ollama returns JSON)
            return {'response': res.json().get('response', '')}
        else:
            print(f'Ollama Error: {res.text}')
            return {'response': f'My internal brain returned an error: {res.status_code}'}

    except Exception as e:
        print(f'❌ CHAT FATAL ERROR: {e}')
        return {'response': 'I encountered an internal error processing that request. Please check the server logs.'}