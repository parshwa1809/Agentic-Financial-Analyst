from fastapi import APIRouter
from services.db_manager import get_engine
from sqlalchemy import text
import traceback

router = APIRouter()
engine = get_engine()


@router.get("/db-status")
def db_status():
    """Return DB connection status and counts for key tables. Useful for debugging broken DB state."""
    resp = {"ok": False, "details": {}}
    try:
        with engine.connect() as conn:
            # simple connectivity
            r = conn.execute(text('SELECT 1')).fetchone()
            resp['details']['connect_test'] = bool(r)

            # counts
            tables = ['tickers', 'market_data', 'news_articles', 'active_alerts', 'backfill_jobs']
            for t in tables:
                try:
                    cnt = conn.execute(text(f"SELECT COUNT(*) as c FROM {t}")).fetchone()
                    # Some DB drivers return positional tuples
                    if isinstance(cnt, dict) or hasattr(cnt, '__getitem__'):
                        # prefer column name
                        try:
                            cval = cnt['c']
                        except Exception:
                            # fallback to first column
                            cval = list(cnt)[0]
                    else:
                        cval = cnt[0] if cnt is not None else 0
                    resp['details'][t] = int(cval) if cval is not None else 0
                except Exception as e:
                    resp['details'][t] = f"error: {str(e)}"

        resp['ok'] = True
    except Exception as e:
        tb = traceback.format_exc()
        resp['error'] = str(e)
        resp['traceback'] = tb

    return resp
