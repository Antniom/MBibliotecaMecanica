import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metadata.db")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except Exception:
        pass
    return conn

def init_db():
    """Initializes the SQLite database with the schema."""
    conn = get_db_connection()
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()

def log_api_usage(provider, tokens_used=0):
    """Logs API requests and tokens used for rate limiting and reporting."""
    conn = get_db_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO api_usage_log (provider, date, requests_today, tokens_today)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(date) DO UPDATE SET
            requests_today = requests_today + 1,
            tokens_today = tokens_today + ?
        """,
        (provider, today, tokens_used, tokens_used)
    )
    conn.commit()
    conn.close()

def get_api_usage_today(provider):
    """Returns (requests, tokens) used today for a given provider."""
    conn = get_db_connection()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT requests_today, tokens_today FROM api_usage_log WHERE provider = ? AND date = ?",
        (provider, today)
    )
    row = cursor.fetchone()
    conn.close()
    if row:
        return row["requests_today"], row["tokens_today"]
    return 0, 0

if __name__ == "__main__":
    init_db()
    print("Database initialized at:", DB_PATH)
