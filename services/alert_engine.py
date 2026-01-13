import time
import logging
from datetime import datetime, timedelta
from services.db_manager import execute_query, get_engine
import pandas as pd
import numpy as np

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alert_engine")

def check_supply_chain_contagion(ticker):
    """
    The 'Kill Switch': Checks if a key supplier/customer is crashing.
    """
    try:
        # 1. Find partners (Suppliers/Customers)
        # FIX: Table name 'supply_chain' (was supply_chain_links)
        query = """
            SELECT partner_ticker, relationship 
            FROM supply_chain 
            WHERE ticker = :t
        """
        partners = execute_query(query, {"t": ticker})
        
        if not partners: return []

        alerts = []
        for p in partners:
            partner_ticker = p[0]
            relation = p[1]
            
            # 2. Check partner's performance today
            # FIX: Table 'market_data' (was stock_prices)
            price_query = """
                SELECT close 
                FROM market_data 
                WHERE ticker = :t 
                ORDER BY timestamp DESC LIMIT 2
            """
            prices = execute_query(price_query, {"t": partner_ticker})
            
            if prices and len(prices) >= 2:
                current = prices[0][0]
                prev = prices[1][0]
                pct_change = ((current - prev) / prev) * 100
                
                # 3. TRIGGER: If a Supplier crashes > 3%, warn the user
                if pct_change < -3.0:
                    alerts.append({
                        "type": "Supply Chain Risk",
                        "severity": "high",
                        "message": f"Contagion Warning: Key {relation} {partner_ticker} is down {pct_change:.1f}%. Monitor {ticker} impact."
                    })
        return alerts
    except Exception as e:
        logger.error(f"Error checking supply chain for {ticker}: {e}")
        return []

def check_sentiment_divergence(ticker, price_change):
    """
    The 'Bull Trap': Price is rising, but AI Sentiment is negative.
    """
    try:
        # Get average sentiment from news in last 24h
        query = """
            SELECT AVG(sentiment_score) as avg_sent 
            FROM news_articles 
            WHERE ticker = :t 
            AND published_at >= NOW() - INTERVAL 1 DAY
        """
        result = execute_query(query, {"t": ticker})
        
        avg_sentiment = result[0][0] if result and result[0][0] else 0
        
        # TRIGGER: Price Up (>1%) AND Sentiment Bad (<-0.2)
        if price_change > 1.0 and avg_sentiment < -0.2:
            return [{
                "type": "Sentiment Divergence",
                "severity": "medium",
                "message": f"Bull Trap Warning: {ticker} price rising (+{price_change:.1f}%) but AI sentiment is negative ({avg_sentiment:.2f})."
            }]
        return []
    except Exception as e:
        logger.error(f"Error checking sentiment for {ticker}: {e}")
        return []

def generate_alerts():
    """Main loop to check all active tickers."""
    logger.info("⚡ Alert Engine Cycle Started...")
    
    # FIX: Table 'tickers' (was assets)
    rows = execute_query("SELECT symbol FROM tickers WHERE is_active=1")
    if not rows: return

    for row in rows:
        t = row[0] 
        
        # Get recent price data
        # FIX: Table 'market_data' (was stock_prices)
        prices = execute_query(
            "SELECT close FROM market_data WHERE ticker = :t ORDER BY timestamp DESC LIMIT 14", 
            {"t": t}
        )
        
        if not prices or len(prices) < 2:
            continue
            
        current_price = prices[0][0]
        prev_price = prices[1][0]
        pct_change = ((current_price - prev_price) / prev_price) * 100
        
        new_alerts = []
        
        # --- 1. Technical Alerts (Placeholder for RSI logic) ---
        if pct_change > 5.0:
             new_alerts.append({"type": "Price Spike", "severity": "low", "message": f"{t} is up {pct_change:.1f}% in short term."})

        # --- 2. NEW: Supply Chain Contagion ---
        new_alerts.extend(check_supply_chain_contagion(t))
        
        # --- 3. NEW: Sentiment Divergence ---
        new_alerts.extend(check_sentiment_divergence(t, pct_change))
        
        # Save Alerts to DB
        for alert in new_alerts:
            # Check for duplicates in last 10 mins
            # FIX: Table 'active_alerts' (was alerts)
            dup_check = execute_query("""
                SELECT id FROM active_alerts 
                WHERE ticker=:t AND message=:m 
                AND created_at >= NOW() - INTERVAL 10 MINUTE
            """, {"t": t, "m": alert['message']})
            
            if not dup_check:
                execute_query("""
                    INSERT INTO active_alerts (ticker, message, created_at)
                    VALUES (:t, :m, NOW())
                """, {"t": t, "m": alert['message']})
                logger.info(f"🚨 ALERT GENERATED: {t} - {alert['type']}")

if __name__ == "__main__":
    while True:
        try:
            generate_alerts()
        except Exception as e:
            logger.error(f"Cycle crashed: {e}")
        time.sleep(60)