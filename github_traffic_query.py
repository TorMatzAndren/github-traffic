#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path.home() / "github-traffic" / "github-traffic.sqlite3"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def expand_path(raw: str | Path) -> Path:
    return Path(raw).expanduser().resolve()


def connect_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def date_filter_sql(alias: str, days: int | None) -> tuple[str, list[Any]]:
    if days is None:
        return "", []
    return f"WHERE {alias} >= date('now', ?)", [f"-{days - 1} days"]


def latest_run(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, run_uuid, collected_at_utc, owner, dry_run, status, created_at_utc
        FROM collection_runs
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return dict(row) if row else None


def history_bounds(conn: sqlite3.Connection) -> dict[str, Any]:
    row = conn.execute(
        """
        WITH all_days AS (
            SELECT day_utc FROM traffic_views_daily
            UNION
            SELECT day_utc FROM traffic_clones_daily
        )
        SELECT MIN(day_utc) AS first_day, MAX(day_utc) AS last_day, COUNT(DISTINCT day_utc) AS stored_days
        FROM all_days
        """
    ).fetchone()
    return dict(row) if row else {"first_day": None, "last_day": None, "stored_days": 0}


def repositories(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT
                id,
                owner,
                repo,
                github_id,
                full_name,
                private,
                fork,
                archived,
                disabled,
                default_branch,
                html_url,
                pushed_at,
                github_updated_at,
                updated_at_utc
            FROM repositories
            ORDER BY owner, repo
            """
        ).fetchall()
    )


def totals_by_repo(conn: sqlite3.Connection, days: int | None) -> list[dict[str, Any]]:
    view_where, view_params = date_filter_sql("day_utc", days)
    clone_where, clone_params = date_filter_sql("day_utc", days)

    return rows_to_dicts(
        conn.execute(
            f"""
            WITH recent_views AS (
                SELECT repository_id, SUM(count) AS views, SUM(uniques) AS unique_viewers
                FROM traffic_views_daily
                {view_where}
                GROUP BY repository_id
            ),
            recent_clones AS (
                SELECT repository_id, SUM(count) AS clones, SUM(uniques) AS unique_cloners
                FROM traffic_clones_daily
                {clone_where}
                GROUP BY repository_id
            )
            SELECT
                r.owner,
                r.repo,
                COALESCE(v.views, 0) AS views,
                COALESCE(v.unique_viewers, 0) AS unique_viewers,
                COALESCE(c.clones, 0) AS clones,
                COALESCE(c.unique_cloners, 0) AS unique_cloners
            FROM repositories r
            LEFT JOIN recent_views v ON v.repository_id = r.id
            LEFT JOIN recent_clones c ON c.repository_id = r.id
            ORDER BY views DESC, clones DESC, r.repo
            """,
            view_params + clone_params,
        ).fetchall()
    )


def daily_series(conn: sqlite3.Connection, repo: str | None, days: int | None) -> list[dict[str, Any]]:
    view_where, view_params = date_filter_sql("day_utc", days)
    clone_where, clone_params = date_filter_sql("day_utc", days)

    params: list[Any] = view_params + clone_params
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    return rows_to_dicts(
        conn.execute(
            f"""
            WITH days AS (
                SELECT day_utc, repository_id FROM traffic_views_daily
                {view_where}
                UNION
                SELECT day_utc, repository_id FROM traffic_clones_daily
                {clone_where}
            )
            SELECT
                r.owner,
                r.repo,
                d.day_utc,
                COALESCE(v.count, 0) AS views,
                COALESCE(v.uniques, 0) AS unique_viewers,
                COALESCE(c.count, 0) AS clones,
                COALESCE(c.uniques, 0) AS unique_cloners
            FROM days d
            JOIN repositories r ON r.id = d.repository_id
            LEFT JOIN traffic_views_daily v
                ON v.repository_id = d.repository_id
               AND v.day_utc = d.day_utc
            LEFT JOIN traffic_clones_daily c
                ON c.repository_id = d.repository_id
               AND c.day_utc = d.day_utc
            {repo_filter}
            ORDER BY r.repo, d.day_utc
            """,
            params,
        ).fetchall()
    )


def latest_paths(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "AND r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(
        conn.execute(
            f"""
            WITH latest_snapshot AS (
                SELECT MAX(snapshot_date_utc) AS snapshot_date_utc
                FROM popular_paths_snapshot
            )
            SELECT
                r.owner,
                r.repo,
                p.snapshot_date_utc,
                p.path,
                p.title,
                p.count,
                p.uniques
            FROM popular_paths_snapshot p
            JOIN latest_snapshot ls ON ls.snapshot_date_utc = p.snapshot_date_utc
            JOIN repositories r ON r.id = p.repository_id
            WHERE 1 = 1
            {repo_filter}
            ORDER BY p.count DESC, p.uniques DESC, r.repo, p.path
            LIMIT ?
            """,
            params,
        ).fetchall()
    )


def latest_referrers(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "AND r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(
        conn.execute(
            f"""
            WITH latest_snapshot AS (
                SELECT MAX(snapshot_date_utc) AS snapshot_date_utc
                FROM popular_referrers_snapshot
            )
            SELECT
                r.owner,
                r.repo,
                pr.snapshot_date_utc,
                pr.referrer,
                pr.count,
                pr.uniques
            FROM popular_referrers_snapshot pr
            JOIN latest_snapshot ls ON ls.snapshot_date_utc = pr.snapshot_date_utc
            JOIN repositories r ON r.id = pr.repository_id
            WHERE 1 = 1
            {repo_filter}
            ORDER BY pr.count DESC, pr.uniques DESC, r.repo, pr.referrer
            LIMIT ?
            """,
            params,
        ).fetchall()
    )


def promotion_events(conn: sqlite3.Connection, repo: str | None, limit: int | None) -> list[dict[str, Any]]:
    if not has_table(conn, "promotion_events"):
        return []

    params: list[Any] = []
    repo_filter = ""
    limit_sql = ""

    if repo:
        repo_filter = "WHERE repo = ?"
        params.append(repo)

    if limit is not None:
        limit_sql = "LIMIT ?"
        params.append(limit)

    return rows_to_dicts(
        conn.execute(
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
            {repo_filter}
            ORDER BY event_time_utc DESC, id DESC
            {limit_sql}
            """,
            params,
        ).fetchall()
    )


def raw_failures(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return rows_to_dicts(
        conn.execute(
            """
            SELECT
                cr.id AS run_id,
                cr.collected_at_utc,
                r.owner,
                r.repo,
                raw.endpoint,
                raw.status_code,
                raw.error
            FROM raw_api_responses raw
            JOIN repositories r ON r.id = raw.repository_id
            JOIN collection_runs cr ON cr.id = raw.run_id
            WHERE raw.ok = 0
            ORDER BY raw.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    )


def payload(conn: sqlite3.Connection, repo: str | None, days: int | None, limit: int) -> dict[str, Any]:
    return {
        "generated_at_utc": utc_now_iso(),
        "source": "github-traffic.sqlite3",
        "scope": "repo" if repo else "summary",
        "repo": repo,
        "window_days": days,
        "history_bounds": history_bounds(conn),
        "latest_run": latest_run(conn),
        "repositories": repositories(conn) if repo is None else [],
        "totals_by_repo": totals_by_repo(conn, days) if repo is None else [],
        "daily_series": daily_series(conn, repo, days),
        "latest_popular_paths": latest_paths(conn, repo, limit),
        "latest_popular_referrers": latest_referrers(conn, repo, limit),
        "promotion_events": promotion_events(conn, repo, None),
        "recent_failures": raw_failures(conn, limit) if repo is None else [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read GitHub traffic SQLite data and emit deterministic JSON for dashboard/Jarri surfaces."
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite database path. Default: {DEFAULT_DB}")
    parser.add_argument("--summary-json", action="store_true", help="Emit summary JSON.")
    parser.add_argument("--repo", help="Emit repo-specific JSON.")
    parser.add_argument("--days", type=int, help="Optional recent-day filter. Omit for all local history.")
    parser.add_argument("--limit", type=int, default=25, help="Limit popular paths/referrers/failures. Default: 25.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.days is not None and args.days < 1:
        raise SystemExit("ERROR: --days must be >= 1")

    if args.limit < 1:
        raise SystemExit("ERROR: --limit must be >= 1")

    db_path = expand_path(args.db)
    conn = connect_db(db_path)

    try:
        result = payload(conn, args.repo, args.days, args.limit)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2 if args.pretty else None))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
