import sys
import os
# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import time
import yfinance as yf
from services.db_manager import get_engine, execute_query
import pandas as pd

engine = get_engine()

def nightly_job():
    print("🌙 Fetching Ratios...")
    try:
        tickers = pd.read_sql("SELECT symbol FROM tickers", engine)['symbol'].tolist()
    except: tickers = []

    for t in tickers:
        try:
            info = yf.Ticker(t).info
            execute_query(
                """
                INSERT INTO fundamentals 
                (ticker, market_cap, pe_ratio, pb_ratio, ps_ratio, debt_to_equity, profit_margin, dividend_yield, eps_ttm, last_updated) 
                VALUES (:t, :mc, :pe, :pb, :ps, :de, :pm, :div, :eps, NOW()) 
                ON DUPLICATE KEY UPDATE 
                    market_cap=:mc, pe_ratio=:pe, pb_ratio=:pb, ps_ratio=:ps, debt_to_equity=:de, 
                    profit_margin=:pm, dividend_yield=:div, eps_ttm=:eps, last_updated=NOW()
                """,
                {
                    "t": t, 
                    "mc": info.get('marketCap'), "pe": info.get('trailingPE'),
                    "pb": info.get('priceToBook'), "ps": info.get('priceToSalesTrailing12Months'),
                    "de": info.get('debtToEquity'), "pm": info.get('profitMargins'),
                    "div": info.get('dividendYield'), "eps": info.get('trailingEps')
                }
            )
            time.sleep(1)
        except Exception as e:
            print(f"❌ Error fetching fundamentals for {t}: {e}")

if __name__ == "__main__":
    while True:
        nightly_job()
        time.sleep(86400)