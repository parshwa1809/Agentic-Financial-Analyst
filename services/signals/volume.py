import pandas as pd
import sys
import os

from services.indicators import calculate_vwap

def compute_signals(df: pd.DataFrame, ticker: str):
    alerts = []
    if len(df) < 20: return alerts
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    avg_vol = df['volume'].rolling(10).mean().iloc[-1]
    if avg_vol > 0 and latest['volume'] > (avg_vol * 2.5):
        alerts.append(f"Volume Spike: {latest['volume']/avg_vol:.1f}x Avg")
        
    df['VWAP'] = calculate_vwap(df)
    vwap = df['VWAP'].iloc[-1]
    prev_vwap = df['VWAP'].iloc[-2]
    
    if not pd.isna(vwap):
        if prev['close'] <= prev_vwap and latest['close'] > vwap:
            alerts.append("Bullish VWAP Cross")
        elif prev['close'] >= prev_vwap and latest['close'] < vwap:
            alerts.append("Bearish VWAP Cross")

    return alerts