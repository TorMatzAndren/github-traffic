#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_DB = Path.home() / "github-traffic" / "github-traffic.sqlite3"
DEFAULT_PROJECT_DIR = Path(__file__).resolve().parent


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


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def require_text(payload: dict[str, Any], key: str) -> str:
    value = clean_text(payload.get(key))
    if not value:
        raise ValueError(f"missing required field: {key}")
    return value


def parse_trail_days(value: Any) -> int:
    if value is None or value == "":
        return 3
    trail_days = int(value)
    if trail_days < 0 or trail_days > 365:
        raise ValueError("trail_days must be between 0 and 365")
    return trail_days


def upsert_event(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    owner = clean_text(payload.get("owner")) or "TorMatzAndren"
    repo = require_text(payload, "repo")
    event_type = require_text(payload, "event_type")
    platform = require_text(payload, "platform")
    title = require_text(payload, "title")
    event_time_utc = clean_text(payload.get("event_time_utc")) or utc_now_iso()
    trail_days = parse_trail_days(payload.get("trail_days"))

    location = clean_text(payload.get("location"))
    url = clean_text(payload.get("url"))
    notes = clean_text(payload.get("notes"))
    framework = clean_text(payload.get("framework"))

    event_id_raw = payload.get("id")
    event_id = int(event_id_raw) if event_id_raw not in (None, "", 0, "0") else None

    conn = connect_db(db_path)
    init_schema(conn)

    try:
        now = utc_now_iso()

        if event_id is not None:
            existing = conn.execute(
                "SELECT id FROM promotion_events WHERE id = ?",
                (event_id,),
            ).fetchone()

            if existing is None:
                raise ValueError(f"event id not found: {event_id}")

            conn.execute(
                """
                UPDATE promotion_events
                SET
                    event_time_utc = ?,
                    owner = ?,
                    repo = ?,
                    event_type = ?,
                    platform = ?,
                    location = ?,
                    url = ?,
                    title = ?,
                    notes = ?,
                    framework = ?,
                    trail_days = ?,
                    updated_at_utc = ?
                WHERE id = ?
                """,
                (
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
                    now,
                    event_id,
                ),
            )
            conn.commit()
            return {"ok": True, "action": "updated", "id": event_id}

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
                now,
                now,
            ),
        )
        conn.commit()
        return {"ok": True, "action": "inserted", "id": int(cur.lastrowid)}

    finally:
        conn.close()


def delete_event(db_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = int(require_text(payload, "id"))

    conn = connect_db(db_path)
    init_schema(conn)

    try:
        cur = conn.execute("DELETE FROM promotion_events WHERE id = ?", (event_id,))
        conn.commit()
        return {"ok": cur.rowcount > 0, "deleted": cur.rowcount, "id": event_id}
    finally:
        conn.close()


def regenerate_dashboard(project_dir: Path, db_path: Path) -> dict[str, Any]:
    script = project_dir / "generate_static_dashboard.py"

    if not script.exists():
        raise FileNotFoundError(f"dashboard generator not found: {script}")

    cmd = [
        sys.executable,
        str(script),
        "--db",
        str(db_path),
    ]

    result = subprocess.run(
        cmd,
        cwd=str(project_dir),
        text=True,
        capture_output=True,
        check=False,
    )

    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


class ApiHandler(BaseHTTPRequestHandler):
    server_version = "GitHubTrafficLocalAPI/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", file=sys.stderr)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")

        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_json(200, {"ok": True})

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(
                200,
                {
                    "ok": True,
                    "service": "github_traffic_local_api",
                    "mode": "localhost-only",
                    "allowed_actions": [
                        "events/upsert",
                        "events/delete",
                        "dashboard/regenerate",
                    ],
                },
            )
            return

        self.send_json(404, {"ok": False, "error": "not found"})

    def read_payload(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
        return payload

    def do_POST(self) -> None:
        try:
            payload = self.read_payload()
            db_path = self.server.db_path
            project_dir = self.server.project_dir

            if self.path == "/events/upsert":
                result = upsert_event(db_path, payload)
                regen = regenerate_dashboard(project_dir, db_path)
                result["dashboard"] = regen
                self.send_json(200 if result.get("ok") else 500, result)
                return

            if self.path == "/events/delete":
                result = delete_event(db_path, payload)
                regen = regenerate_dashboard(project_dir, db_path)
                result["dashboard"] = regen
                self.send_json(200 if result.get("ok") else 404, result)
                return

            if self.path == "/dashboard/regenerate":
                result = regenerate_dashboard(project_dir, db_path)
                self.send_json(200 if result.get("ok") else 500, result)
                return

            self.send_json(404, {"ok": False, "error": "not found"})

        except Exception as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})


class GitHubTrafficServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_class: type[BaseHTTPRequestHandler], db_path: Path, project_dir: Path):
        super().__init__(server_address, handler_class)
        self.db_path = db_path
        self.project_dir = project_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Localhost-only API for the GitHub Traffic dashboard.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host. Default: 127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port. Default: 8765")
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite database path. Default: {DEFAULT_DB}")
    parser.add_argument("--project-dir", default=str(DEFAULT_PROJECT_DIR), help=f"Project dir. Default: {DEFAULT_PROJECT_DIR}")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        print("ERROR: public API only supports localhost binding.", file=sys.stderr)
        return 2

    host = "127.0.0.1"
    port = args.port
    db_path = expand_path(args.db)
    project_dir = expand_path(args.project_dir)

    server = GitHubTrafficServer((host, port), ApiHandler, db_path, project_dir)

    print(f"GitHub Traffic local API listening on http://{host}:{port}")
    print("Allowed actions: /events/upsert, /events/delete, /dashboard/regenerate")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("Stopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
