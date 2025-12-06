import pandas as pd

def compute_signals(df, ticker, spy_df=None, vix_df=None):
    alerts = []
    if df.empty: return alerts
    
    # Relative Strength
    if spy_df is not None and len(spy_df) >= 5:
        stock_ret = df['close'].pct_change(5).iloc[-1]
        spy_ret = spy_df['close'].pct_change(5).iloc[-1]
        diff = stock_ret - spy_ret
        
        if diff > 0.01: alerts.append(f"Outperforming Market (Alpha +{diff*100:.1f}%)")
        elif diff < -0.01: alerts.append(f"Underperforming Market (Alpha {diff*100:.1f}%)")

    # VIX Fear
    if vix_df is not None and len(vix_df) >= 2:
        vix_curr = vix_df.iloc[-1]['close']
        vix_prev = vix_df.iloc[-2]['close']
        change = (vix_curr - vix_prev) / vix_prev
        
        if change > 0.05: alerts.append(f"Market Fear Spiking (VIX +{change*100:.1f}%)")

    return alerts