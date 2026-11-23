import os
import sqlite3
import pandas as pd
import streamlit as st

def get_database_url() -> str | None:
    """Retrieves Supabase PostgreSQL connection string from Streamlit Secrets or environment."""
    try:
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass
    return os.environ.get("DATABASE_URL")

class HybridDBConnection:
    """Unified wrapper supporting both Supabase PostgreSQL and local SQLite."""
    def __init__(self, sqlite_path="hospital_v2.db"):
        self.db_url = get_database_url()
        self.is_postgres = bool(self.db_url)
        if self.is_postgres:
            import psycopg2
            self.conn = psycopg2.connect(self.db_url, sslmode="require")
        else:
            self.conn = sqlite3.connect(sqlite_path)

    def _adapt_sql(self, query: str) -> str:
        if not self.is_postgres:
            return query
        # Convert SQLite AUTOINCREMENT & ? placeholders to PostgreSQL syntax
        adapted = query.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        adapted = adapted.replace("?", "%s")
        return adapted

    def execute(self, query: str, params: tuple = ()):
        cur = self.conn.cursor()
        cur.execute(self._adapt_sql(query), params)
        return cur

    def read_df(self, query: str, params: tuple = ()) -> pd.DataFrame:
        return pd.read_sql_query(self._adapt_sql(query), self.conn, params=params)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db_connection(sqlite_path="hospital_v2.db") -> HybridDBConnection:
    return HybridDBConnection(sqlite_path)

def get_storage_status() -> str:
    return "☁️ Supabase PostgreSQL (Persistent Cloud DB)" if get_database_url() else "💾 Local SQLite (Ephemeral Sandbox)"
