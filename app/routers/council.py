from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.internal.agent_council import run_council
import traceback

router = APIRouter()

class CouncilRequest(BaseModel):
    ticker: str

@router.post("/run")
def run_debate(req: CouncilRequest): # <--- REMOVED 'async'
    """
    Trigger the AI Council Debate.
    Synchronous version to match the robust agent_council.py
    """
    try:
        ticker = req.ticker.upper()
        print(f"🏛️ Council Request Received for: {ticker}")
        
        # <--- REMOVED 'await'
        result = run_council(ticker)
        
        return {"result": result}
        
    except Exception as e:
        print(f"❌ Council API Error: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))