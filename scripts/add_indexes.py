"""Add database indexes for performance optimization.

Run with: uv run python scripts/add_indexes.py

These indexes target the most common query patterns:
- Redirect lookup: urls(short_code, is_active) composite index
- URL filtering: urls(is_active)
- Foreign key lookups: urls(user_id), events(url_id)
- Event type filtering: events(event_type)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from peewee import PostgresqlDatabase

db = PostgresqlDatabase(
    os.environ.get("DATABASE_NAME", "hackathon_db"),
    host=os.environ.get("DATABASE_HOST", "localhost"),
    port=int(os.environ.get("DATABASE_PORT", 5432)),
    user=os.environ.get("DATABASE_USER", "postgres"),
    password=os.environ.get("DATABASE_PASSWORD", "postgres"),
)

INDEXES = [
    ("idx_urls_short_code_is_active", "urls", "short_code, is_active"),
    ("idx_urls_is_active", "urls", "is_active"),
    ("idx_urls_user_id", "urls", "user_id"),
    ("idx_events_url_id", "events", "url_id"),
    ("idx_events_event_type", "events", "event_type"),
]


def add_indexes():
    db.connect()
    for idx_name, table, columns in INDEXES:
        sql = f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({columns})"
        print(f"Creating index: {sql}")
        db.execute_sql(sql)
    db.close()
    print("All indexes created successfully.")


if __name__ == "__main__":
    add_indexes()
