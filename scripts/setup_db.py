docker-compose exec -T api bash -c "cat <<EOF > /app/services/setup_db.py
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from services.db_manager import execute_query, get_engine
from sqlalchemy import text

def init_db():
    print('🛠️ Initializing Database Schema (MySQL/TiDB Compatible)...')
    
    # 1. Tickers
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS tickers (
            symbol VARCHAR(20) PRIMARY KEY, 
            name VARCHAR(255), 
            is_active BOOLEAN, 
            priority VARCHAR(10)
        )
    \"\"\")
    
    # 2. Market Data
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS market_data (
            ticker VARCHAR(20), 
            timestamp DATETIME, 
            open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume BIGINT, 
            PRIMARY KEY (ticker, timestamp)
        )
    \"\"\")
    
    # 3. News & Alerts (Fixed AUTO_INCREMENT)
    execute_query(\"CREATE TABLE IF NOT EXISTS active_alerts (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), message TEXT, created_at DATETIME)\")
    execute_query(\"CREATE TABLE IF NOT EXISTS news_articles (id INT AUTO_INCREMENT PRIMARY KEY, ticker VARCHAR(20), headline TEXT, url VARCHAR(512) UNIQUE, published_at DATETIME, sentiment_score FLOAT)\")
    
    # 4. Fundamentals
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker VARCHAR(20) PRIMARY KEY, 
            market_cap BIGINT, pe_ratio FLOAT, pb_ratio FLOAT, ps_ratio FLOAT, 
            debt_to_equity FLOAT, profit_margin FLOAT, dividend_yield FLOAT, eps_ttm FLOAT, 
            last_updated DATETIME
        )
    \"\"\")
    
    # 5. Risk Engine (Fixed AUTO_INCREMENT)
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS political_risk (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            ticker VARCHAR(20), 
            risk_score INT, 
            risk_factor VARCHAR(50), 
            headline VARCHAR(255), 
            detected_at DATETIME
        )
    \"\"\")
    
    # 6. Supply Chain (Fixed AUTO_INCREMENT)
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS supply_chain (
            id INT AUTO_INCREMENT PRIMARY KEY, 
            ticker VARCHAR(20), 
            partner_ticker VARCHAR(20), 
            relationship VARCHAR(20), 
            confidence FLOAT DEFAULT 1.0, 
            reason TEXT,
            UNIQUE(ticker, partner_ticker)
        )
    \"\"\")

    # 7. Agent Memory (Fixed AUTO_INCREMENT)
    execute_query(\"\"\"
        CREATE TABLE IF NOT EXISTS council_verdicts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticker VARCHAR(20),
            verdict VARCHAR(10),      
            confidence FLOAT,         
            time_horizon VARCHAR(50), 
            reasoning TEXT,           
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    \"\"\")
    
    # 8. Seed Data
    execute_query(\"INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES ('AAPL', 'Apple', 1), ('TSLA', 'Tesla', 1), ('NVDA', 'Nvidia', 1)\")
    
    # 9. Migration Helper
    engine = get_engine()
    with engine.connect() as conn:
        try:
            conn.execute(text(\"SELECT reason FROM supply_chain LIMIT 1\"))
        except Exception:
            print('⚠️ Migration: Adding missing reason column...')
            conn.execute(text(\"ALTER TABLE supply_chain ADD COLUMN reason TEXT\"))
            conn.commit()

    print('✅ Database Ready.')

if __name__ == \"__main__\":
    init_db()
EOF"