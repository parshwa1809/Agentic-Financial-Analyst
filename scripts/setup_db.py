"""Create / migrate the database schema. Safe to run repeatedly (idempotent).

Runs automatically when the `api` container starts. Manual run:
    docker compose exec api python scripts/setup_db.py
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402
from services.db_manager import execute_query, get_engine  # noqa: E402

TABLES = [
    """CREATE TABLE IF NOT EXISTS tickers (
        symbol VARCHAR(20) PRIMARY KEY,
        name VARCHAR(255),
        is_active BOOLEAN DEFAULT 0,
        priority VARCHAR(10)
    )""",
    """CREATE TABLE IF NOT EXISTS market_data (
        ticker VARCHAR(20),
        timestamp DATETIME,
        open FLOAT, high FLOAT, low FLOAT, close FLOAT, volume BIGINT,
        PRIMARY KEY (ticker, timestamp)
    )""",
    """CREATE TABLE IF NOT EXISTS active_alerts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(20),
        message TEXT,
        created_at DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS news_articles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(20),
        headline TEXT,
        url VARCHAR(512) UNIQUE,
        published_at DATETIME,
        sentiment_score FLOAT
    )""",
    """CREATE TABLE IF NOT EXISTS fundamentals (
        ticker VARCHAR(20) PRIMARY KEY,
        market_cap BIGINT, pe_ratio FLOAT, pb_ratio FLOAT, ps_ratio FLOAT,
        debt_to_equity FLOAT, profit_margin FLOAT, dividend_yield FLOAT, eps_ttm FLOAT,
        roa FLOAT, roe FLOAT, beta FLOAT,
        last_updated DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS political_risk (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(20),
        risk_score INT,
        risk_factor VARCHAR(50),
        headline TEXT,
        detected_at DATETIME
    )""",
    """CREATE TABLE IF NOT EXISTS supply_chain (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(20),
        partner_ticker VARCHAR(20),
        relationship VARCHAR(20),
        confidence FLOAT DEFAULT 1.0,
        reason TEXT,
        UNIQUE (ticker, partner_ticker)
    )""",
    """CREATE TABLE IF NOT EXISTS council_verdicts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        ticker VARCHAR(20),
        verdict VARCHAR(10),
        confidence FLOAT,
        time_horizon VARCHAR(50),
        reasoning TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
]

# (table, column, definition) — added if an older database is missing them
COLUMN_MIGRATIONS = [
    ("supply_chain", "reason", "TEXT"),
    ("supply_chain", "confidence", "FLOAT DEFAULT 1.0"),
    ("fundamentals", "roa", "FLOAT"),
    ("fundamentals", "roe", "FLOAT"),
    ("fundamentals", "beta", "FLOAT"),
]


def _existing_columns(conn, table):
    rows = conn.execute(
        text("SELECT COLUMN_NAME FROM information_schema.COLUMNS "
             "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t"),
        {"t": table},
    ).fetchall()
    return {r[0].lower() for r in rows}


def init_db():
    print("🛠️ Initializing database schema...")
    for ddl in TABLES:
        execute_query(ddl)

    engine = get_engine()
    with engine.begin() as conn:
        for table, col, definition in COLUMN_MIGRATIONS:
            if col not in _existing_columns(conn, table):
                print(f"   ➕ Adding {table}.{col}")
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
        # Long headlines overflowed the old VARCHAR(255)
        cols = conn.execute(
            text("SELECT DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                 "AND TABLE_NAME = 'political_risk' AND COLUMN_NAME = 'headline'")
        ).fetchone()
        if cols and cols[0].lower() == "varchar":
            conn.execute(text("ALTER TABLE political_risk MODIFY headline TEXT"))

    # Seed a starter watchlist only when the table is empty
    rows = execute_query("SELECT COUNT(*) FROM tickers")
    if rows and rows[0][0] == 0:
        execute_query(
            "INSERT IGNORE INTO tickers (symbol, name, is_active) VALUES "
            "('AAPL', 'Apple', 1), ('TSLA', 'Tesla', 1), ('NVDA', 'Nvidia', 1)"
        )
    print("✅ Database ready.")


if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        # Don't block the API from starting; the error is visible in the logs
        print(f"❌ Database setup failed: {e}")
