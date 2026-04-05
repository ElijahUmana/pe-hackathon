"""Load seed data from CSV files into the database."""

import csv
import json
import os
import sys

from peewee import chunked

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.database import db
from app.models.event import Event
from app.models.url import URL
from app.models.user import User


def parse_bool(value):
    """Convert Python-style boolean string to actual boolean."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def parse_details(raw):
    """Parse the details JSON field, handling CSV double-quote escaping."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def load_users(filepath):
    """Load users from CSV."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "id": int(row["id"]),
                "username": row["username"],
                "email": row["email"],
                "created_at": row["created_at"],
            })

    with db.atomic():
        for batch in chunked(rows, 100):
            User.insert_many(batch).execute()

    print(f"Loaded {len(rows)} users")


def load_urls(filepath):
    """Load URLs from CSV."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({
                "id": int(row["id"]),
                "user_id": int(row["user_id"]),
                "short_code": row["short_code"],
                "original_url": row["original_url"],
                "title": row["title"],
                "is_active": parse_bool(row["is_active"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })

    with db.atomic():
        for batch in chunked(rows, 100):
            URL.insert_many(batch).execute()

    print(f"Loaded {len(rows)} URLs")


def load_events(filepath):
    """Load events from CSV."""
    with open(filepath, newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            # Details is already properly parsed by csv.DictReader
            # (handles the double-quote escaping automatically)
            details_raw = row["details"]
            # Ensure it's valid JSON string for storage
            try:
                parsed = json.loads(details_raw)
                details_str = json.dumps(parsed)
            except (json.JSONDecodeError, TypeError):
                details_str = details_raw

            rows.append({
                "id": int(row["id"]),
                "url_id": int(row["url_id"]),
                "user_id": int(row["user_id"]),
                "event_type": row["event_type"],
                "timestamp": row["timestamp"],
                "details": details_str,
            })

    with db.atomic():
        for batch in chunked(rows, 100):
            Event.insert_many(batch).execute()

    print(f"Loaded {len(rows)} events")


def seed_all(data_dir=None):
    """Load all seed data."""
    if data_dir is None:
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "seed_data",
        )

    users_csv = os.path.join(data_dir, "users.csv")
    urls_csv = os.path.join(data_dir, "urls.csv")
    events_csv = os.path.join(data_dir, "events.csv")

    for f in [users_csv, urls_csv, events_csv]:
        if not os.path.exists(f):
            print(f"ERROR: Seed file not found: {f}")
            sys.exit(1)

    print("Dropping existing tables...")
    db.drop_tables([Event, URL, User], safe=True)
    print("Creating tables...")
    db.create_tables([User, URL, Event])

    print("Loading seed data...")
    load_users(users_csv)
    load_urls(urls_csv)
    load_events(events_csv)
    print("Seed complete!")


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        db.connect(reuse_if_open=True)
        seed_all()
        db.close()
