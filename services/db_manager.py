import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(
    os.getenv("DB_URI"), 
    pool_recycle=300, 
    pool_pre_ping=True
)

def get_engine():
    return engine

def execute_query(query, params=None):
    with engine.connect() as conn:
        conn.execute(text(query), params or {})
        conn.commit()


def execute_many(query, params_list):
    """Execute a parametrized query with a list of parameter dicts (executemany).

    Example: execute_many(query, [{...}, {...}])
    """
    if not params_list:
        return
    with engine.begin() as conn:
        conn.execute(text(query), params_list)


def get_connection():
    return engine.connect()