import pandas as pd
from services.db_manager import get_engine
# NEW IMPORT: Use custom indicator
from services.indicators import calculate_rsi 

engine = get_engine()

def get_political_risk_context(ticker):
    try:
        df = pd.read_sql(f"SELECT * FROM political_risk WHERE ticker='{ticker}' OR ticker='MARKET' ORDER BY detected_at DESC LIMIT 3", engine)
        if df.empty: return ""
        text = "**⚠️ Political/Regulatory Risks:**\n"
        for _, row in df.iterrows():
            text += f"- {row['risk_factor']} ({row['risk_score']}): {row['headline']}\n"
        return text
    except: return ""

def get_supply_chain_context(ticker):
    try:
        df = pd.read_sql(f"SELECT * FROM supply_chain WHERE ticker='{ticker}'", engine)
        if df.empty: return ""
        suppliers = df[df['relationship'] == 'SUPPLIER']['partner_ticker'].tolist()
        customers = df[df['relationship'] == 'CUSTOMER']['partner_ticker'].tolist()
        text = "**⛓️ Supply Chain:**\n"
        if suppliers: text += f"- Suppliers: {', '.join(suppliers)}\n"
        if customers: text += f"- Customers: {', '.join(customers)}\n"
        return text
    except: return ""

def get_smart_context(ticker):
    context = f"**Analysis for {ticker}:**\n\n"
    try:
        df = pd.read_sql(f"SELECT * FROM market_data WHERE ticker='{ticker}' ORDER BY timestamp DESC LIMIT 50", engine)
        if not df.empty:
            df = df.sort_values('timestamp')
            latest = df.iloc[-1]
            
            # FIX: Use custom calculate_rsi instead of ta.rsi()
            rsi_series = calculate_rsi(df['close'])
            rsi = rsi_series.iloc[-1]
            
            context += f"Price: ${latest['close']:.2f} | RSI: {rsi:.1f}\n"
    except: pass
    
    context += get_political_risk_context(ticker)
    context += get_supply_chain_context(ticker)
    
    # Recent Alerts
    try:
        alerts = pd.read_sql(f"SELECT message, created_at FROM active_alerts WHERE ticker='{ticker}' ORDER BY created_at DESC LIMIT 3", engine)
        if not alerts.empty:
            context += f"\n**Recent Signals:**\n"
            for _, row in alerts.iterrows():
                context += f"- {row['message']}\n"
    except: pass
    
    # Recent News
    try:
        news = pd.read_sql(f"SELECT headline FROM news_articles WHERE ticker='{ticker}' ORDER BY published_at DESC LIMIT 2", engine)
        if not news.empty:
            context += f"\n**Recent News:**\n"
            for _, row in news.iterrows():
                context += f"- {row['headline']}\n"
    except: pass

    return context