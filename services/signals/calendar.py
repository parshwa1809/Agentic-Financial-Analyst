import pandas as pd
from datetime import datetime, time, timedelta
import pytz 
import os
from dotenv import load_dotenv

load_dotenv()

TZ = os.getenv("MARKET_TIMEZONE", "America/New_York")
OPEN = os.getenv("MARKET_OPEN_TIME", "09:30")
CLOSE = os.getenv("MARKET_CLOSE_TIME", "16:00")

h_o, m_o = map(int, OPEN.split(':'))
h_c, m_c = map(int, CLOSE.split(':'))

MARKET_TZ = pytz.timezone(TZ)
RTH_OPEN = time(h_o, m_o)
RTH_CLOSE = time(h_c, m_c)

def compute_signals(df: pd.DataFrame, ticker: str) -> list:
    alerts = []
    if df.empty: return alerts 

    ts = pd.to_datetime(df.iloc[-1]['timestamp'])
    if ts.tzinfo is None: ts = ts.tz_localize('UTC')
    local_ts = ts.tz_convert(MARKET_TZ)
    t = local_ts.time()
    d = local_ts.weekday()
    
    dummy = datetime.now().date()
    open_end = (datetime.combine(dummy, RTH_OPEN) + timedelta(minutes=30)).time()
    close_start = (datetime.combine(dummy, RTH_CLOSE) - timedelta(minutes=30)).time()
    
    if RTH_OPEN <= t <= open_end: alerts.append("Market Open Volatility Period")
    elif close_start <= t <= RTH_CLOSE: alerts.append("Market Close Volatility Period")

    if d == 0: alerts.append("Monday Trading Context")
    elif d == 4: alerts.append("Friday Trading Context")

    return alerts