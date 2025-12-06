import pandas as pd
import sys
import os

from services.indicators import calculate_rsi, calculate_macd, calculate_bbands

def compute_signals(df: pd.DataFrame, ticker: str):
    alerts = []
    if len(df) < 21: return alerts
    
    # Using our custom indicators
    df['RSI'] = calculate_rsi(df['close'], 14)
    upper, mid, lower = calculate_bbands(df['close'])
    macd_line, sig_line = calculate_macd(df['close'])
    
    latest = df.iloc[-1]
    latest_rsi = df['RSI'].iloc[-1]
    latest_upper = upper.iloc[-1]
    latest_lower = lower.iloc[-1]
    
    if latest_rsi >= 70: alerts.append(f"RSI Overbought ({latest_rsi:.1f})")
    elif latest_rsi <= 30: alerts.append(f"RSI Oversold ({latest_rsi:.1f})")

    if latest['close'] > latest_upper: alerts.append("Price Breakout > Upper BB")
    elif latest['close'] < latest_lower: alerts.append("Price Breakdown < Lower BB")

    return alerts