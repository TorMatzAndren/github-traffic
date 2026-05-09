#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_DB = Path.home() / "github-traffic" / "github-traffic.sqlite3"
DEFAULT_OWNER = "TorMatzAndren"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def expand_path(raw: str | Path) -> Path:
    return Path(raw).expanduser().resolve()


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS promotion_events (
            id INTEGER PRIMARY KEY,
            event_time_utc TEXT NOT NULL,
            owner TEXT NOT NULL,
            repo TEXT NOT NULL,
            event_type TEXT NOT NULL,
            platform TEXT NOT NULL,
            location TEXT,
            url TEXT,
            title TEXT NOT NULL,
            notes TEXT,
            framework TEXT,
            trail_days INTEGER NOT NULL DEFAULT 3,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT
        )
        """
    )

    ensure_column(conn, "promotion_events", "framework", "TEXT")
    ensure_column(conn, "promotion_events", "trail_days", "INTEGER NOT NULL DEFAULT 3")
    ensure_column(conn, "promotion_events", "updated_at_utc", "TEXT")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_promotion_events_repo_time
        ON promotion_events(owner, repo, event_time_utc)
        """
    )
    conn.commit()


def insert_event(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO promotion_events (
            event_time_utc,
            owner,
            repo,
            event_type,
            platform,
            location,
            url,
            title,
            notes,
            framework,
            trail_days,
            created_at_utc,
            updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            args.event_time_utc or now,
            args.owner,
            args.repo,
            args.event_type,
            args.platform,
            args.location,
            args.url,
            args.title,
            args.notes,
            args.framework,
            args.trail_days,
            now,
            now,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_event(conn: sqlite3.Connection, args: argparse.Namespace) -> bool:
    existing = conn.execute(
        "SELECT * FROM promotion_events WHERE id = ?",
        (args.update_id,),
    ).fetchone()

    if existing is None:
        return False

    fields = {
        "event_time_utc": args.event_time_utc,
        "owner": args.owner if args.owner != DEFAULT_OWNER else None,
        "repo": args.repo,
        "event_type": args.event_type,
        "platform": args.platform,
        "location": args.location,
        "url": args.url,
        "title": args.title,
        "notes": args.notes,
        "framework": args.framework,
        "trail_days": args.trail_days if args.trail_days is not None else None,
    }

    updates = []
    values = []

    for key, value in fields.items():
        if value is not None:
            updates.append(f"{key} = ?")
            values.append(value)

    if not updates:
        return True

    updates.append("updated_at_utc = ?")
    values.append(utc_now_iso())
    values.append(args.update_id)

    conn.execute(
        f"UPDATE promotion_events SET {', '.join(updates)} WHERE id = ?",
        values,
    )
    conn.commit()
    return True


def list_events(conn: sqlite3.Connection, owner: str | None, repo: str | None, limit: int) -> list[sqlite3.Row]:
    params: list[object] = []
    where: list[str] = []

    if owner:
        where.append("owner = ?")
        params.append(owner)

    if repo:
        where.append("repo = ?")
        params.append(repo)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    return conn.execute(
        f"""
        SELECT
            id,
            event_time_utc,
            owner,
            repo,
            event_type,
            platform,
            location,
            url,
            title,
            notes,
            framework,
            trail_days,
            created_at_utc,
            updated_at_utc
        FROM promotion_events
        {where_sql}
        ORDER BY event_time_utc DESC, id DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()


def delete_event(conn: sqlite3.Connection, event_id: int) -> bool:
    cur = conn.execute("DELETE FROM promotion_events WHERE id = ?", (event_id,))
    conn.commit()
    return cur.rowcount > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add, update, list, or delete GitHub traffic intelligence events.")

    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite database path. Default: {DEFAULT_DB}")
    parser.add_argument("--owner", default=DEFAULT_OWNER, help=f"GitHub owner/org. Default: {DEFAULT_OWNER}")
    parser.add_argument("--repo", help="Repository name.")
    parser.add_argument("--event-type", help="Event type, e.g. reddit_post, facebook_post, release, readme_rewrite.")
    parser.add_argument("--platform", help="Platform/source, e.g. reddit, facebook, github, blog, discord.")
    parser.add_argument("--location", help="Location/context, e.g. /r/vibecoding, Facebook group name.")
    parser.add_argument("--url", help="URL for the event.")
    parser.add_argument("--title", help="Short event title.")
    parser.add_argument("--notes", help="Optional notes.")
    parser.add_argument("--framework", help="Main framework/context, e.g. reddit_launch, facebook_group_test, release_push.")
    parser.add_argument("--trail-days", type=int, default=3, help="Dashboard impact trail days. Default: 3.")
    parser.add_argument("--event-time-utc", help="Event time in UTC ISO format. Default: now.")

    parser.add_argument("--list", action="store_true", help="List events.")
    parser.add_argument("--limit", type=int, default=50, help="List limit. Default: 50.")
    parser.add_argument("--delete-id", type=int, help="Delete event by id.")
    parser.add_argument("--update-id", type=int, help="Update event by id. Only supplied fields are changed.")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = expand_path(args.db)

    conn = connect_db(db_path)
    init_schema(conn)

    try:
        if args.delete_id is not None:
            deleted = delete_event(conn, args.delete_id)
            if deleted:
                print(f"Deleted event id {args.delete_id}")
                return 0
            print(f"Event id not found: {args.delete_id}", file=sys.stderr)
            return 1

        if args.update_id is not None:
            updated = update_event(conn, args)
            if updated:
                print(f"Updated promotion event id {args.update_id}")
                return 0
            print(f"Event id not found: {args.update_id}", file=sys.stderr)
            return 1

        if args.list:
            rows = list_events(conn, args.owner, args.repo, args.limit)
            for row in rows:
                print(
                    f"{row['id']} | {row['event_time_utc']} | {row['repo']} | "
                    f"{row['event_type']} | {row['platform']} | {row['location'] or ''} | "
                    f"trail={row['trail_days']} | framework={row['framework'] or ''} | {row['title']}"
                )
            return 0

        required = {
            "--repo": args.repo,
            "--event-type": args.event_type,
            "--platform": args.platform,
            "--title": args.title,
        }

        missing = [name for name, value in required.items() if not value]
        if missing:
            print(f"ERROR: missing required fields: {', '.join(missing)}", file=sys.stderr)
            return 2

        event_id = insert_event(conn, args)
        print(f"Inserted promotion event id {event_id}")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
