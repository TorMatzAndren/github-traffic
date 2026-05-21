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
                COALESCE(stargazers_count, 0) AS stargazers_count,
                COALESCE(watchers_count, 0) AS watchers_count,
                COALESCE(forks_count, 0) AS forks_count,
                COALESCE(stargazers_count, 0) AS stars,
                COALESCE(forks_count, 0) AS forks,
                updated_at_utc
            FROM repositories
            ORDER BY owner, repo
            """
        ).fetchall()
    )


def repository_inventory(conn: sqlite3.Connection, days: int | None) -> list[dict[str, Any]]:
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
                r.id,
                r.owner,
                r.repo,
                r.github_id,
                r.full_name,
                r.private,
                r.fork,
                r.archived,
                r.disabled,
                r.default_branch,
                r.html_url,
                r.pushed_at,
                r.github_updated_at,
                COALESCE(r.stargazers_count, 0) AS stargazers_count,
                COALESCE(r.watchers_count, 0) AS watchers_count,
                COALESCE(r.forks_count, 0) AS forks_count,
                COALESCE(r.stargazers_count, 0) AS stars,
                COALESCE(r.forks_count, 0) AS forks,
                COALESCE(v.views, 0) AS views,
                COALESCE(v.unique_viewers, 0) AS unique_viewers,
                COALESCE(c.clones, 0) AS clones,
                COALESCE(c.unique_cloners, 0) AS unique_cloners,
                r.updated_at_utc
            FROM repositories r
            LEFT JOIN recent_views v ON v.repository_id = r.id
            LEFT JOIN recent_clones c ON c.repository_id = r.id
            ORDER BY views DESC, clones DESC, r.repo
            """,
            view_params + clone_params,
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


def referrer_timeline(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            p.snapshot_date_utc,
            r.owner,
            r.repo,
            p.referrer,
            p.count,
            p.uniques
        FROM popular_referrers_snapshot p
        JOIN repositories r ON r.id = p.repository_id
        {repo_filter}
        ORDER BY p.snapshot_date_utc DESC, p.count DESC, p.uniques DESC, r.repo, p.referrer
        LIMIT ?
    """, params).fetchall())


def path_timeline(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            p.snapshot_date_utc,
            r.owner,
            r.repo,
            p.path,
            p.title,
            p.count,
            p.uniques
        FROM popular_paths_snapshot p
        JOIN repositories r ON r.id = p.repository_id
        {repo_filter}
        ORDER BY p.snapshot_date_utc DESC, p.count DESC, p.uniques DESC, r.repo, p.path
        LIMIT ?
    """, params).fetchall())


def metadata_timeline(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    if not has_table(conn, "repository_metadata_snapshots"):
        return []

    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            m.snapshot_date_utc,
            r.owner,
            r.repo,
            m.stargazers_count,
            m.watchers_count,
            m.forks_count,
            m.open_issues_count
        FROM repository_metadata_snapshots m
        JOIN repositories r ON r.id = m.repository_id
        {repo_filter}
        ORDER BY m.snapshot_date_utc DESC, r.repo
        LIMIT ?
    """, params).fetchall())


def referrer_first_seen(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            r.owner,
            r.repo,
            p.referrer,
            MIN(p.snapshot_date_utc) AS first_seen_date,
            MAX(p.snapshot_date_utc) AS last_seen_date,
            COUNT(DISTINCT p.snapshot_date_utc) AS days_seen,
            MAX(p.count) AS peak_count,
            MAX(p.uniques) AS peak_uniques,
            SUM(p.count) AS total_count,
            SUM(p.uniques) AS total_uniques
        FROM popular_referrers_snapshot p
        JOIN repositories r ON r.id = p.repository_id
        {repo_filter}
        GROUP BY r.owner, r.repo, p.referrer
        ORDER BY first_seen_date DESC, peak_count DESC, total_count DESC
        LIMIT ?
    """, params).fetchall())


def path_first_seen(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            r.owner,
            r.repo,
            p.path,
            MIN(p.snapshot_date_utc) AS first_seen_date,
            MAX(p.snapshot_date_utc) AS last_seen_date,
            COUNT(DISTINCT p.snapshot_date_utc) AS days_seen,
            MAX(p.count) AS peak_count,
            MAX(p.uniques) AS peak_uniques,
            SUM(p.count) AS total_count,
            SUM(p.uniques) AS total_uniques
        FROM popular_paths_snapshot p
        JOIN repositories r ON r.id = p.repository_id
        {repo_filter}
        GROUP BY r.owner, r.repo, p.path
        ORDER BY first_seen_date DESC, peak_count DESC, total_count DESC
        LIMIT ?
    """, params).fetchall())


def propagation_highlights(conn: sqlite3.Connection, repo: str | None, limit: int) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "AND r.repo = ?"
        params.append(repo)

    params.append(limit)

    return rows_to_dicts(conn.execute(f"""
        WITH latest_day AS (
            SELECT MAX(snapshot_date_utc) AS day FROM popular_referrers_snapshot
        ),
        previous_referrers AS (
            SELECT DISTINCT repository_id, referrer
            FROM popular_referrers_snapshot
            WHERE snapshot_date_utc < (SELECT day FROM latest_day)
        ),
        latest_referrers AS (
            SELECT
                r.owner,
                r.repo,
                'new_referrer' AS highlight_type,
                p.referrer AS subject,
                p.count,
                p.uniques,
                p.snapshot_date_utc
            FROM popular_referrers_snapshot p
            JOIN repositories r ON r.id = p.repository_id
            LEFT JOIN previous_referrers prev
              ON prev.repository_id = p.repository_id
             AND prev.referrer = p.referrer
            WHERE p.snapshot_date_utc = (SELECT day FROM latest_day)
              AND prev.referrer IS NULL
              {repo_filter}
        ),
        latest_path_day AS (
            SELECT MAX(snapshot_date_utc) AS day FROM popular_paths_snapshot
        ),
        previous_paths AS (
            SELECT DISTINCT repository_id, path
            FROM popular_paths_snapshot
            WHERE snapshot_date_utc < (SELECT day FROM latest_path_day)
        ),
        latest_paths AS (
            SELECT
                r.owner,
                r.repo,
                'new_path' AS highlight_type,
                p.path AS subject,
                p.count,
                p.uniques,
                p.snapshot_date_utc
            FROM popular_paths_snapshot p
            JOIN repositories r ON r.id = p.repository_id
            LEFT JOIN previous_paths prev
              ON prev.repository_id = p.repository_id
             AND prev.path = p.path
            WHERE p.snapshot_date_utc = (SELECT day FROM latest_path_day)
              AND prev.path IS NULL
              {repo_filter}
        )
        SELECT * FROM latest_referrers
        UNION ALL
        SELECT * FROM latest_paths
        ORDER BY snapshot_date_utc DESC, count DESC, uniques DESC
        LIMIT ?
    """, params).fetchall())


def repository_stars(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("""
        SELECT
            owner,
            repo,
            COALESCE(stargazers_count, 0) AS stargazers_count,
            COALESCE(watchers_count, 0) AS watchers_count
        FROM repositories
        ORDER BY stargazers_count DESC
    """).fetchall()

    return [
        {
            "owner": r[0],
            "repo": r[1],
            "stars": r[2],
            "watchers": r[3],
        }
        for r in rows
    ]

def repository_forks(conn: sqlite3.Connection, repo: str | None = None) -> list[dict[str, Any]]:
    params: list[Any] = []
    repo_filter = ""

    if repo:
        repo_filter = "WHERE r.repo = ?"
        params.append(repo)

    return rows_to_dicts(conn.execute(f"""
        SELECT
            r.owner,
            r.repo,
            f.fork_full_name,
            f.fork_owner,
            f.fork_repo,
            f.fork_created_at,
            f.default_branch,
            f.html_url,
            f.pushed_at,
            COALESCE(f.stargazers_count, 0) AS stargazers_count
        FROM repository_forks f
        JOIN repositories r ON r.id = f.repository_id
        {repo_filter}
        ORDER BY f.pushed_at DESC
    """, params).fetchall())


def payload(conn: sqlite3.Connection, repo: str | None, days: int | None, limit: int) -> dict[str, Any]:
    return {
        "generated_at_utc": utc_now_iso(),
        "source": "github-traffic.sqlite3",
        "scope": "repo" if repo else "summary",
        "repo": repo,
        "window_days": days,
        "history_bounds": history_bounds(conn),
        "latest_run": latest_run(conn),
        "repositories": repository_inventory(conn, days) if repo is None else [],
        "totals_by_repo": totals_by_repo(conn, days) if repo is None else [],
        "daily_series": daily_series(conn, repo, days),
        "latest_popular_paths": latest_paths(conn, repo, limit),
        "latest_popular_referrers": latest_referrers(conn, repo, limit),
        "referrer_timeline": referrer_timeline(conn, repo, limit),
        "path_timeline": path_timeline(conn, repo, limit),
        "metadata_timeline": metadata_timeline(conn, repo, limit),
        "referrer_first_seen": referrer_first_seen(conn, repo, limit),
        "path_first_seen": path_first_seen(conn, repo, limit),
        "propagation_highlights": propagation_highlights(conn, repo, limit),
        "repository_stars": repository_stars(conn),
        "repository_forks": repository_forks(conn, repo),
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





