import sys
import os
import time
from datetime import datetime, timedelta
import yfinance as yf
from sqlalchemy import text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.db_manager import get_engine

CHECK_INTERVAL_SECONDS = 60    
UPDATE_THRESHOLD_HOURS = 12    
REQUEST_DELAY = 2              

def get_ecosystem_tickers():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            active_rows = conn.execute(text("SELECT symbol FROM tickers WHERE is_active=1")).fetchall()
            active_set = set(r[0] for r in active_rows)
            
            if not active_set:
                return []

            partner_query = text("""
                SELECT DISTINCT partner_ticker 
                FROM supply_chain 
                WHERE ticker IN (SELECT symbol FROM tickers WHERE is_active=1)
            """)
            partner_rows = conn.execute(partner_query).fetchall()
            partner_set = set(r[0] for r in partner_rows)

            full_universe = list(active_set.union(partner_set))
            blacklist = {"UNKNOWN", "NONE", "NULL", "TBA", "VARIOUS", "N/A"}
            return sorted([t for t in full_universe if t and t.upper() not in blacklist and len(t) < 10])
    except Exception as e:
        print(f"❌ Worker DB Error: {e}")
        return []

def get_tickers_needing_update(target_list):
    if not target_list: return []
    engine = get_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT ticker, last_updated FROM fundamentals")).fetchall()
        db_status = {r[0]: r[1] for r in rows}
        
        to_update = []
        now = datetime.now()
        threshold = timedelta(hours=UPDATE_THRESHOLD_HOURS)
        
        for ticker in target_list:
            last_upd = db_status.get(ticker)
            if not last_upd:
                print(f"   ✨ Found NEW ticker: {ticker}")
                to_update.append(ticker)
                continue
            
            if isinstance(last_upd, str):
                try: last_upd = datetime.strptime(last_upd, "%Y-%m-%d %H:%M:%S")
                except: pass

            if last_upd and (now - last_upd) > threshold:
                print(f"   ⏰ Ticker {ticker} is stale (>12h). Refreshing...")
                to_update.append(ticker)
        return to_update
    except Exception as e:
        print(f"⚠️ Error checking staleness: {e}")
        return target_list

def update_fundamentals(ticker):
    engine = get_engine()
    try:
        print(f"📊 Fetching fundamentals for {ticker}...")
        stock = yf.Ticker(ticker)
        info = stock.info
        
        data = {
            "t": ticker, "mc": info.get("marketCap"), "pe": info.get("trailingPE"),
            "pb": info.get("priceToBook"), "de": info.get("debtToEquity"),
            "pm": info.get("profitMargins"), "dy": info.get("dividendYield"),
            "roa": info.get("returnOnAssets"), "roe": info.get("returnOnEquity"),
            "beta": info.get("beta")
        }

        if data['de']: data['de'] = data['de'] / 100.0

        query = text("""
            INSERT INTO fundamentals 
            (ticker, market_cap, pe_ratio, pb_ratio, debt_to_equity, profit_margin, dividend_yield, roa, roe, beta, last_updated)
            VALUES (:t, :mc, :pe, :pb, :de, :pm, :dy, :roa, :roe, :beta, NOW())
            ON DUPLICATE KEY UPDATE
            market_cap=:mc, pe_ratio=:pe, pb_ratio=:pb, debt_to_equity=:de, 
            profit_margin=:pm, dividend_yield=:dy, roa=:roa, roe=:roe, beta=:beta, last_updated=NOW()
        """)
        
        with engine.begin() as conn:
            conn.execute(query, data)
        print(f"   ✅ Updated {ticker}")
        return True
    except Exception as e:
        print(f"   ❌ Failed {ticker}: {e}")
        return False

def run_worker():
    print("🚀 Fundamentals Worker Started (RELOADED)")
    while True:
        targets = get_ecosystem_tickers()
        if not targets:
            print(f"⚠️ No active tickers found. Sleeping {CHECK_INTERVAL_SECONDS}s...")
        else:
            to_process = get_tickers_needing_update(targets)
            if not to_process:
                print(f"✨ All {len(targets)} tickers are fresh. Sleeping {CHECK_INTERVAL_SECONDS}s...")
            else:
                for ticker in to_process:
                    update_fundamentals(ticker)
                    time.sleep(REQUEST_DELAY)
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    run_worker()