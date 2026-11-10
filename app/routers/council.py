"""Specialist briefing endpoint: serves the latest stored briefing, or builds one."""
import traceback

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.internal.agent_council import latest_briefing, run_council

router = APIRouter()


class CouncilRequest(BaseModel):
    ticker: str
    refresh: bool = False   # True = build a new briefing now (one AI call) instead of serving the stored one


@router.post("/run")
def briefing(req: CouncilRequest):
    try:
        ticker = req.ticker.upper()
        if not req.refresh:
            last = latest_briefing(ticker)
            if last:
                return {"result": last}
        return {"result": run_council(ticker, force=req.refresh)}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
