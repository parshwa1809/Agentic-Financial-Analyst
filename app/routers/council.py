from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from services.db_manager import get_engine
# We still import run_council as a fallback just in case
from app.internal.agent_council import run_council
import traceback

router = APIRouter()
engine = get_engine()

class CouncilRequest(BaseModel):
    ticker: str

@router.post("/run")
def get_latest_verdict(req: CouncilRequest): 
    """
    INSTANTLY returns the latest Council Verdict from the background worker.
    Only triggers a manual run if no data exists.
    """
    try:
        ticker = req.ticker.upper()
        
        # 1. Try to fetch from Database (Instant)
        with engine.connect() as conn:
            # Get the most recent verdict
            query = text("""
                SELECT verdict, confidence, time_horizon, reasoning, created_at 
                FROM council_verdicts 
                WHERE ticker = :t 
                ORDER BY created_at DESC LIMIT 1
            """)
            row = conn.execute(query, {"t": ticker}).fetchone()
            
        if row:
            # Convert DB row back to the JSON format the UI expects
            # We use the "Shotgun" format here too just to be safe
            verdict = row[0]
            conf = row[1]
            horizon = row[2]
            analysis = row[3]
            
            print(f"🚀 Serving cached verdict for {ticker} (from {row[4]})")
            
            result = {
                "verdict": verdict, "decision": verdict, "Verdict": verdict,
                "confidence": conf, "Confidence": conf,
                "horizon": horizon, "Horizon": horizon, "time_horizon": horizon,
                "analysis": analysis, "Analysis": analysis, "reasoning": analysis,
                "bull_case": "See full analysis.", "bear_case": "See full analysis."
            }
            return {"result": result}

        # 2. Fallback: If no data exists yet, run it now (Slow)
        print(f"⚠️ No cached verdict for {ticker}. Running manual session...")
        result = run_council(ticker)
        return {"result": result}
        
    except Exception as e:
        print(f"❌ Council API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))