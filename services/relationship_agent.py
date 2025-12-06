import time
import json
import os
import pandas as pd
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage

from services.db_manager import get_engine, execute_query
from services.redis_manager import get_redis_client

engine = get_engine()
r = get_redis_client() # Added Redis client to track state

LLM_MODEL = os.getenv("OLLAMA_MODEL_NAME", "phi3:mini")
LLM_URL = os.getenv("OLLAMA_API_URL", "http://host.docker.internal:11434")

class AgentState(TypedDict):
    text: str
    relationships: List[dict]
    article_id: str # Track ID to avoid duplicates

def load_node(state: AgentState):
    # Fetch latest news
    df = pd.read_sql("SELECT id, headline FROM news_articles ORDER BY published_at DESC LIMIT 1", engine)
    
    if df.empty: 
        return {"text": "NO_DATA"}
    
    current_id = str(df.iloc[0]['id'])
    headline = df.iloc[0]['headline']
    
    # Check if we already processed this ID
    last_processed_id = r.get("agent:last_news_id")
    if last_processed_id and last_processed_id.decode('utf-8') == current_id:
        return {"text": "NO_DATA"}
    
    return {"text": headline, "article_id": current_id}

def extract_node(state: AgentState):
    if state["text"] == "NO_DATA": 
        return {"relationships": []}
    
    llm = ChatOllama(base_url=LLM_URL, model=LLM_MODEL, format="json")
    prompt = f"Extract business relationship from: '{state['text']}'. JSON format: {{'source':'AAPL', 'target':'TSM', 'type':'SUPPLIER'}}."
    
    try:
        res = llm.invoke([SystemMessage(content="Extractor Bot"), HumanMessage(content=prompt)])
        # Handle potential string/markdown wrapping in response
        content = res.content
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
            
        data = json.loads(content)
        
        if isinstance(data, dict) and "source" in data: 
            return {"relationships": [data]}
        elif isinstance(data, list):
            return {"relationships": data}
        elif "relationships" in data:
            return {"relationships": data["relationships"]}
    except Exception as e: 
        print(f"Extraction Error: {e}")
        
    return {"relationships": []}

def save_node(state: AgentState):
    # If we had data, mark this ID as processed in Redis
    if "article_id" in state and state["text"] != "NO_DATA":
        r.set("agent:last_news_id", state["article_id"])

    for relation in state["relationships"]:
        if "source" in relation and "target" in relation:
            print(f"🔗 New Link: {relation.get('source')} -> {relation.get('target')}")
            try:
                execute_query(
                    "INSERT IGNORE INTO supply_chain (ticker, partner_ticker, relationship) VALUES (:s, :p, :r)", 
                    {"s": relation.get('source'), "p": relation.get('target'), "r": relation.get('type', 'PARTNER')}
                )
            except: pass
    return state

workflow = StateGraph(AgentState)
workflow.add_node("load", load_node)
workflow.add_node("extract", extract_node)
workflow.add_node("save", save_node)

workflow.set_entry_point("load")
workflow.add_edge("load", "extract")
workflow.add_edge("extract", "save")
workflow.add_edge("save", END)

app = workflow.compile()

if __name__ == "__main__":
    print("🕵️ Relationship Agent Active (LangGraph)...")
    while True:
        try: 
            app.invoke({"text": "", "relationships": [], "article_id": ""})
        except Exception as e: 
            print(f"Agent Loop Error: {e}")
        time.sleep(60)