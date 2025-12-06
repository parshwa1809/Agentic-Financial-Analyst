import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.db_manager import execute_query

def init_db():
    print("🛠️ Initializing TiDB Schema...")
    
    # 1. Create Tables
    execute_query("CREATE TABLE IF NOT EXISTS tickers (symbol VARCHAR(20) PRIMARY KEY, name VARCHAR(255), is_active BOOLEAN, priority VARCHAR(10))")
    execute_query("CREATE TABLE IF NOT EXISTS market_data (ticker VARCHAR(20), timestamp DATETIME, open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume BIGINT, PRIMARY KEY (ticker, timestamp))")
    execute_query("CREATE TABLE IF NOT EXISTS active_alerts (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), message TEXT, created_at DATETIME)")
    execute_query("CREATE TABLE IF NOT EXISTS news_articles (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), headline TEXT, url VARCHAR(512) UNIQUE, published_at DATETIME, sentiment_score FLOAT)")
    execute_query("""
        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker VARCHAR(20) PRIMARY KEY, market_cap BIGINT, pe_ratio FLOAT, pb_ratio FLOAT, ps_ratio FLOAT, 
            debt_to_equity FLOAT, profit_margin FLOAT, dividend_yield FLOAT, eps_ttm FLOAT, last_updated DATETIME
        )
    """)
    execute_query("CREATE TABLE IF NOT EXISTS political_risk (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), risk_score INT, risk_factor VARCHAR(50), headline VARCHAR(255), detected_at DATETIME)")
    execute_query("CREATE TABLE IF NOT EXISTS supply_chain (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), partner_ticker VARCHAR(20), relationship VARCHAR(20), confidence FLOAT DEFAULT 1.0)")
    execute_query("CREATE TABLE IF NOT EXISTS backfill_jobs (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), status VARCHAR(50), started_at DATETIME, finished_at DATETIME, rows_inserted INT DEFAULT 0, message TEXT)")
    
    # 2. Seed Data (STOCKS ONLY - NO CRYPTO)
    execute_query("INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES ('AAPL', 'Apple', 1), ('TSLA', 'Tesla', 1), ('SPY', 'S&P 500', 1)")
    
    print("✅ Database Ready (Clean).")

if __name__ == "__main__":
    init_db()