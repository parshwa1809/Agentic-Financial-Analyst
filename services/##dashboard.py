import dash
from dash import dcc, html, Input, Output, State, dash_table, ALL, callback_context, no_update
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
import requests
from datetime import datetime, timedelta
import sys
import os
import logging

# --- CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard")

from db_manager import get_engine, execute_query
sys.path.append(os.path.dirname(__file__))
from indicators import calculate_rsi, calculate_vwap, calculate_bbands

app = dash.Dash(
    __name__, 
    external_stylesheets=[
        dbc.themes.FLATLY, 
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css"
    ], 
    suppress_callback_exceptions=True
)
engine = get_engine()

COLORS = {"bg": "#0b1120", "card": "#1e293b", "text": "#e2e8f0", "border": "#334155"}

def render_chat_bubbles(history):
    if not history: return [html.Div([html.H4("👋 AI Analyst", className="text-center text-light"), html.P("Ready.", className="text-center small text-muted")], className="mt-5")]
    bubbles = []
    for msg in reversed(history):
        is_user = msg['role'] == 'user'
        style = {"backgroundColor": "#2563eb" if is_user else "#334155", "color": "white", "padding": "10px", "borderRadius": "15px", "marginBottom": "10px", "maxWidth": "90%", "alignSelf": "flex-end" if is_user else "flex-start"}
        bubbles.append(html.Div(dcc.Markdown(msg['content']), style=style))
    return bubbles

# --- LAYOUTS ---
def get_monitor_layout(active_ticker, chat_history):
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col(dcc.Dropdown(id="ticker-select", placeholder="Select Active Ticker", value=active_ticker, className="text-dark"), xs=12, lg=3),
                        dbc.Col(dbc.RadioItems(id="timeframe-select", options=[{"label": "1D", "value": "1D"}, {"label": "1W", "value": "1W"}, {"label": "1M", "value": "1M"}, {"label": "3M", "value": "3M"}], value="1D", inline=True, class_name="btn-group", input_class_name="btn-check", label_class_name="btn btn-outline-secondary btn-sm", label_checked_class_name="active"), xs=12, lg=4, className="text-center"),
                        dbc.Col(html.Div(id="stats-panel"), xs=12, lg=5)
                    ])
                ])
            ], style={"backgroundColor": COLORS["card"], "borderColor": COLORS["border"]}, className="mb-3"),
            
            dcc.Graph(id="live-chart", style={"height": "55vh"}),
            dcc.Interval(id="update-interval", interval=5000, n_intervals=0),
            
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardHeader([html.I(className="bi bi-bell-fill me-2 text-warning"), "Live Alerts"], style={"backgroundColor": COLORS["card"], "color": "white"}), dbc.CardBody(html.Div(id="alert-feed"), style={"height": "20vh", "overflowY": "scroll", "backgroundColor": "#0f172a", "color": COLORS["text"]})], style={"borderColor": COLORS["border"]}), xs=12, lg=6),
                dbc.Col(dbc.Card([dbc.CardHeader([html.I(className="bi bi-newspaper me-2 text-info"), "Market News"], style={"backgroundColor": COLORS["card"], "color": "white"}), dbc.CardBody(html.Div(id="news-feed"), style={"height": "20vh", "overflowY": "scroll", "backgroundColor": "#0f172a", "color": COLORS["text"]})], style={"borderColor": COLORS["border"]}), xs=12, lg=6)
            ], className="mt-3")
        ], xs=12, lg=9, className="pe-lg-2 mb-4"),
        
        dbc.Col([
            dbc.Card([
                dbc.CardHeader("🤖 AI Analyst", className="text-center fw-bold", style={"backgroundColor": "#2563eb", "color": "white"}),
                dbc.CardBody([
                    html.Div(id="chat-display", children=render_chat_bubbles(chat_history), style={"height": "75vh", "overflowY": "scroll", "display": "flex", "flexDirection": "column-reverse", "backgroundColor": "#0f172a", "padding": "10px", "border": f"1px solid {COLORS['border']}", "borderRadius": "5px"}),
                    dbc.Button("🏛️ Run Council Debate", id="council-btn", color="warning", className="w-100 mt-2 mb-1", size="sm"),
                    dbc.InputGroup([dbc.Input(id="chat-input", placeholder="Ask AI...", autoFocus=True, className="bg-dark text-white border-secondary"), dbc.Button("➤", id="chat-btn", color="primary")])
                ])
            ], style={"height": "88vh", "backgroundColor": COLORS["card"], "borderColor": COLORS["border"]}) 
        ], xs=12, lg=3, className="ps-lg-0") 
    ], className="g-0")

def get_watchlist_layout():
    return dbc.Container([
        html.H2("🌍 Watchlist Manager", className="mb-4 mt-3 text-light"),
        dbc.Row([
            # LEFT: Active Stream
            dbc.Col(dbc.Card([
                dbc.CardHeader("📡 Active Stream (Click X to Remove)", style={"backgroundColor": COLORS["card"], "color": "white"}), 
                dbc.CardBody(html.Div(id="active-stream-list", style={"height": "600px", "overflowY": "scroll", "color": COLORS["text"]}), style={"backgroundColor": "#0f172a"})
            ], style={"borderColor": COLORS["border"]}), xs=12, lg=4),
            
            # RIGHT: Universe Browser
            dbc.Col(dbc.Card([
                dbc.CardHeader("🔍 Universe Browser", style={"backgroundColor": COLORS["card"], "color": "white"}), 
                dbc.CardBody([
                    # SEARCH BAR
                    dbc.Row([
                        dbc.Col(dbc.Input(id="universe-search-input", placeholder="Search Symbol or Name (e.g. MSFT)", className="bg-dark text-white border-secondary"), width=9),
                        dbc.Col(dbc.Button("Search", id="universe-search-btn", color="primary", className="w-100"), width=3)
                    ], className="mb-3"),
                    
                    dbc.Button("Activate Selected", id="batch-add-btn", color="success", className="mb-3 w-100"),
                    html.Div(id="batch-status"),
                    
                    dash_table.DataTable(
                        id='universe-table',
                        columns=[{"name": "Symbol", "id": "symbol"}, {"name": "Name", "id": "name"}, {"name": "Status", "id": "status"}],
                        data=[], 
                        page_size=15, 
                        row_selectable="multi",
                        style_table={'overflowX': 'auto'}, 
                        style_cell={'textAlign': 'left', 'padding': '10px', 'backgroundColor': '#1e293b', 'color': 'white', 'border': '1px solid #334155'},
                        style_header={'backgroundColor': '#0f172a', 'fontWeight': 'bold', 'color': 'white'},
                        selected_rows=[]
                    )
                ])
            ], style={"borderColor": COLORS["border"], "backgroundColor": COLORS["card"]}), xs=12, lg=8)
        ])
    ], fluid=True)

def get_deep_dive_layout():
    return dbc.Container([
        html.H2("🔬 Deep Dive", className="mb-4 mt-3 text-light"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Target Asset", style={"backgroundColor": COLORS["card"], "color": "white"}),
                    dbc.CardBody([
                        dcc.Dropdown(id="dd-ticker", placeholder="Select Ticker", options=[], value="AAPL", className="text-dark"),
                        html.Hr(),
                        html.H5("Political Risk Score", className="text-center text-light"),
                        dcc.Graph(id="risk-gauge", style={"height": "250px", "backgroundColor": COLORS["card"]})
                    ], style={"backgroundColor": COLORS["card"]})
                ], style={"borderColor": COLORS["border"]})
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("⛓️ Supply Chain Map", style={"backgroundColor": COLORS["card"], "color": "white"}),
                    dbc.CardBody([
                        dcc.Graph(id="supply-chain-graph", style={"height": "400px", "backgroundColor": COLORS["card"]})
                    ], style={"backgroundColor": COLORS["card"]})
                ], style={"borderColor": COLORS["border"]})
            ], width=8)
        ])
    ], fluid=True)

def get_gym_layout():
    return html.Div([html.H2("Trading Gym", className="text-light"), html.P("Phase 4 Feature", className="text-muted")], className="p-5")

# --- SHELL ---
app.layout = html.Div([
    dcc.Location(id="url"), 
    dcc.Store(id="chat-history", data=[]), 
    dcc.Store(id="last-ticker", data=None),
    # Central Store for Active Tickers
    dcc.Store(id="active-tickers-store", data=[]), 
    # Trigger for forcing refresh
    dcc.Store(id="refresh-trigger", data=0),
    
    dbc.Offcanvas([
        html.H4("Menu", className="mb-4 text-light"), 
        dbc.Nav([
            dbc.NavLink([html.I(className="bi bi-graph-up me-2"), "Live Monitor"], href="/", active="exact"),
            dbc.NavLink([html.I(className="bi bi-list-ul me-2"), "Watchlist"], href="/watchlist", active="exact"),
            dbc.NavLink([html.I(className="bi bi-diagram-3 me-2"), "Deep Dive"], href="/deep-dive", active="exact"),
            dbc.NavLink([html.I(className="bi bi-joystick me-2"), "Trading Gym"], href="/gym", active="exact"),
        ], vertical=True, pills=True)
    ], id="sidebar", is_open=False, style={"backgroundColor": "#1e293b", "color": "white"}),

    dbc.Navbar([
        html.Div([
            dbc.Button(html.I(className="bi bi-list"), id="open-sidebar", color="link", style={"fontSize": "1.8rem", "color": "white", "textDecoration": "none"}),
            html.Div(dbc.NavbarBrand("🚀 AI Stock Agent", className="fw-bold fs-4 text-white"), style={"position": "absolute", "left": "50%", "transform": "translateX(-50%)"}),
        ], className="d-flex w-100 align-items-center position-relative")
    ], color="#0f172a", dark=True, style={"borderBottom": "1px solid #334155", "height": "60px"}),

    html.Div(id="page-content", className="p-0", style={"backgroundColor": COLORS["bg"], "minHeight": "calc(100vh - 60px)"})
])

# =========================================================
# 4. DECOUPLED CALLBACKS (THE FIX)
# =========================================================

@app.callback(Output("sidebar", "is_open"), Input("open-sidebar", "n_clicks"), State("sidebar", "is_open"))
def toggle_sidebar(n, is_open): return not is_open if n else is_open

@app.callback(Output("page-content", "children"), Input("url", "pathname"), State("chat-history", "data"), State("last-ticker", "data"))
def render_page(path, chat, ticker):
    if path == "/watchlist": return get_watchlist_layout()
    elif path == "/deep-dive": return get_deep_dive_layout()
    elif path == "/gym": return get_gym_layout()
    else: return get_monitor_layout(ticker, chat)

# --- A. READ: Fetch Data (Depends ONLY on Timer or Refresh Trigger) ---
@app.callback(
    Output("active-tickers-store", "data"),
    Input("update-interval", "n_intervals"),
    Input("refresh-trigger", "data")
)
def fetch_active_tickers(n, trig):
    try:
        df = pd.read_sql("SELECT symbol, name FROM tickers WHERE is_active=1 ORDER BY symbol", engine)
        return df.to_dict('records')
    except: return []

# --- B. WRITE: Add Tickers (Only fires on Add Button) ---
@app.callback(
    Output("batch-status", "children"),
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input("batch-add-btn", "n_clicks"),
    State("universe-table", "selected_rows"),
    State("universe-table", "data"),
    prevent_initial_call=True
)
def batch_add(n, idx, data):
    if not n or not idx: return no_update, no_update
    count = 0
    for i in idx:
        try: 
            execute_query("UPDATE tickers SET is_active=1 WHERE symbol=:s", {"s": data[i]['symbol']})
            count += 1
        except: pass
    return f"Activated {count} tickers.", datetime.now().timestamp()

# --- C. WRITE: Delete Tickers (Only fires on X Button) ---
@app.callback(
    Output("refresh-trigger", "data", allow_duplicate=True),
    Input({'type': 'del-btn', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def delete_ticker(n):
    ctx = callback_context
    if ctx.triggered:
        try:
            import json
            # Extract ticker from the button ID
            button_id = json.loads(ctx.triggered[0]['prop_id'].split('.')[0])
            ticker = button_id['index']
            execute_query("UPDATE tickers SET is_active=0 WHERE symbol=:s", {"s": ticker})
            return datetime.now().timestamp() # Trigger Refresh
        except: pass
    return no_update

# --- D. UI UPDATE: Dropdowns (Depends on Store) ---
@app.callback(Output("ticker-select", "options"), Output("dd-ticker", "options"), Input("active-tickers-store", "data"))
def update_dropdowns(data):
    if not data: return [], []
    opts = [{"label": row['symbol'], "value": row['symbol']} for row in data]
    return opts, opts

# --- E. UI UPDATE: Active List (Depends on Store) ---
@app.callback(Output("active-stream-list", "children"), Input("active-tickers-store", "data"))
def update_list(data):
    if not data: return html.P("No active tickers.", className="text-muted")
    return [dbc.ListGroupItem([
        html.Span([html.B(r['symbol'], className="text-white"), html.Span(f" {r['name'][:15]}..", className="text-muted ms-2 small")]), 
        dbc.Button("✕", id={'type':'del-btn', 'index':r['symbol']}, color="danger", size="sm", outline=True, className="float-end py-0")
    ], className="d-flex justify-content-between bg-dark border-secondary") for r in data]

# --- F. Universe Search ---
@app.callback(
    Output("universe-table", "data"), 
    Input("universe-search-btn", "n_clicks"),
    State("universe-search-input", "value")
)
def search_universe(n_search, query):
    # Always load top 50 on init (n_search is None)
    if not query:
        sql = "SELECT symbol, name, is_active FROM tickers ORDER BY is_active DESC, symbol ASC LIMIT 50"
    else:
        clean_q = query.replace("'", "").upper()
        sql = f"SELECT symbol, name, is_active FROM tickers WHERE symbol LIKE '%%{clean_q}%%' OR UPPER(name) LIKE '%%{clean_q}%%' LIMIT 50"
    
    try:
        df = pd.read_sql(sql, engine)
        if df.empty: return []
        df['status'] = df['is_active'].apply(lambda x: "🟢 Active" if x==1 else "⚪ Inactive")
        return df.to_dict('records')
    except: return []

# --- MONITOR, CHAT, DEEP DIVE (Unchanged) ---
@app.callback(Output("chat-history", "data"), Output("chat-display", "children"), Output("chat-input", "value"), Input("chat-btn", "n_clicks"), Input("council-btn", "n_clicks"), State("chat-input", "value"), State("chat-history", "data"), State("ticker-select", "value"))
def handle_chat(n_chat, n_council, query, history, active_ticker):
    ctx = callback_context
    if not ctx.triggered: return dash.no_update, render_chat_bubbles(history), dash.no_update
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    history = history or []
    if button_id == "chat-btn" and query:
        history.append({"role": "user", "content": query})
        try: 
            res = requests.post("http://rag-engine:5000/chat", json={"query": query})
            history.append({"role": "ai", "content": res.json().get("response", "Error")})
        except: history.append({"role": "ai", "content": "⚠️ AI Offline"})
    elif button_id == "council-btn" and active_ticker:
        history.append({"role": "user", "content": f"Debating {active_ticker}..."})
        try:
            res = requests.post("http://rag-engine:5000/debate", json={"ticker": active_ticker})
            history.append({"role": "ai", "content": res.json().get("response", "Error")})
        except Exception as e: history.append({"role": "ai", "content": f"Council Error: {e}"})
    return history, render_chat_bubbles(history), ""

@app.callback(Output("live-chart", "figure"), Output("stats-panel", "children"), Output("alert-feed", "children"), Output("news-feed", "children"), Output("last-ticker", "data"), Input("update-interval", "n_intervals"), Input("ticker-select", "value"), Input("timeframe-select", "value"))
def monitor(n, ticker, timeframe):
    if not ticker: return go.Figure().update_layout(template="plotly_dark", paper_bgcolor=COLORS['card'], plot_bgcolor=COLORS['card']), "", [], [], None
    now = datetime.utcnow()
    days = 90 if timeframe=='3M' else 30 if timeframe=='1M' else 7 if timeframe=='1W' else 1
    cutoff = now - timedelta(days=days)
    resample = '1D' if timeframe=='3M' else '2H' if timeframe=='1M' else '30min' if timeframe=='1W' else None
    df = pd.read_sql(f"SELECT * FROM market_data WHERE ticker='{ticker}' AND timestamp >= '{cutoff}' ORDER BY timestamp ASC", engine)
    if df.empty: return go.Figure().update_layout(template="plotly_dark", paper_bgcolor=COLORS['card'], plot_bgcolor=COLORS['card']), "No Data", [], [], ticker
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    if resample: df = df.resample(resample).agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna()
    if len(df) > 14:
        df['RSI'] = calculate_rsi(df['close'])
        df['VWAP'] = calculate_vwap(df)
        upper, mid, lower = calculate_bbands(df['close'])
        df['BBU_20_2.0'] = upper
        df['BBL_20_2.0'] = lower
        df['BBM_20_2.0'] = mid
        df['BBW'] = (df['BBU_20_2.0'] - df['BBL_20_2.0']) / df['BBM_20_2.0'] * 100
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=df.index, open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="Price"), row=1, col=1)
    if 'BBU_20_2.0' in df.columns:
        fig.add_trace(go.Scatter(x=df.index, y=df['BBU_20_2.0'], line=dict(width=0), showlegend=False), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df['BBL_20_2.0'], line=dict(width=0), fill='tonexty', fillcolor='rgba(0,255,255,0.05)', name="BBands"), row=1, col=1)
    if 'VWAP' in df.columns: fig.add_trace(go.Scatter(x=df.index, y=df['VWAP'], line=dict(color='#facc15', width=1), name="VWAP"), row=1, col=1)
    fig.add_trace(go.Bar(x=df.index, y=df['volume'], marker_color='#475569', name="Vol"), row=2, col=1)
    fig.update_layout(template="plotly_dark", paper_bgcolor=COLORS['bg'], plot_bgcolor=COLORS['bg'], margin=dict(l=10, r=10, t=10, b=10), height=450, showlegend=False, font=dict(color=COLORS['text']))
    latest = df.iloc[-1]
    rsi = latest.get('RSI', 50); bbw = latest.get('BBW', 0)
    col = "success" if rsi < 30 else "danger" if rsi > 70 else "secondary"
    fund = pd.read_sql(f"SELECT pe_ratio FROM fundamentals WHERE ticker='{ticker}'", engine)
    pe = fund.iloc[0]['pe_ratio'] if not fund.empty else 0
    stats = dbc.Row([dbc.Col(html.H3(f"${latest['close']:.2f}", className="fw-bold m-0 text-white"), width="auto"), dbc.Col(dbc.Badge(f"RSI: {rsi:.1f}", color=col, className="p-2 border border-light"), width="auto"), dbc.Col(dbc.Badge(f"BBW: {bbw:.1f}%", color="secondary", className="p-2"), width="auto"), dbc.Col(dbc.Badge(f"P/E: {pe:.1f}", color="info", className="p-2"), width="auto")], className="align-items-center justify-content-end g-2")
    try:
        alert_df = pd.read_sql(f"SELECT message, created_at FROM active_alerts WHERE ticker='{ticker}' ORDER BY created_at DESC LIMIT 10", engine)
        alerts = [html.Div([html.Span(f"⏰ {r['created_at'].strftime('%H:%M')}", className="text-warning me-2 small"), html.Span(r['message'], className="text-light")], className="border-bottom border-secondary p-2 small") for _, r in alert_df.iterrows()]
        news_df = pd.read_sql(f"SELECT headline, url FROM news_articles WHERE ticker='{ticker}' OR ticker='MARKET' ORDER BY published_at DESC LIMIT 5", engine)
        news = [html.Div(html.A(r['headline'], href=r['url'], target="_blank", className="text-decoration-none text-info fw-bold small"), className="border-bottom border-secondary p-2") for _, r in news_df.iterrows()]
    except: alerts = []; news = []
    return fig, stats, alerts, news, ticker

@app.callback(Output("supply-chain-graph", "figure"), Output("risk-gauge", "figure"), Input("dd-ticker", "value"))
def update_deep_dive(ticker):
    if not ticker: return go.Figure().update_layout(template="plotly_dark", paper_bgcolor=COLORS['card']), go.Figure().update_layout(template="plotly_dark", paper_bgcolor=COLORS['card'])
    chain_df = pd.read_sql(f"SELECT * FROM supply_chain WHERE ticker='{ticker}'", engine)
    node_x, node_y, text, color = [0], [0], [ticker], ["#2563eb"]
    edge_x, edge_y = [], []
    if not chain_df.empty:
        for i, row in chain_df.iterrows():
            x = -1 if row['relationship'] == 'SUPPLIER' else 1
            node_x.append(x); node_y.append(i%3 - 1); text.append(f"{row['partner_ticker']}")
            color.append(COLORS["green"])
            edge_x.extend([0, x, None]); edge_y.extend([0, i%3 - 1, None])
    fig_chain = go.Figure()
    fig_chain.add_trace(go.Scatter(x=edge_x, y=edge_y, line=dict(width=1, color='#64748b'), mode='lines'))
    fig_chain.add_trace(go.Scatter(x=node_x, y=node_y, mode='markers+text', text=text, textfont=dict(color="white"), marker=dict(size=30, color=color)))
    fig_chain.update_layout(title=f"{ticker} Network", template="plotly_dark", paper_bgcolor=COLORS['card'], plot_bgcolor=COLORS['card'], xaxis=dict(showgrid=False), yaxis=dict(showgrid=False))
    risk_df = pd.read_sql(f"SELECT AVG(risk_score) as s FROM political_risk WHERE ticker='{ticker}' OR ticker='MARKET'", engine)
    score = risk_df.iloc[0]['s'] if not risk_df.empty and risk_df.iloc[0]['s'] else 0
    fig_gauge = go.Figure(go.Indicator(mode="gauge+number", value=score, title={'text': "Risk Score"}, gauge={'axis': {'range': [0, 100]}, 'bar': {'color': COLORS["red"] if score>70 else COLORS["green"]}}))
    fig_gauge.update_layout(template="plotly_dark", paper_bgcolor=COLORS['card'])
    return fig_chain, fig_gauge

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8050)