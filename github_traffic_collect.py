#!/usr/bin/env python3
from __future__ import annotations

import argparse
import configparser
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path.home() / "projects" / "github-traffic" / "github-traffic.ini"
DEFAULT_DB = Path.home() / "github-traffic" / "github-traffic.sqlite3"
DEFAULT_TOKEN_FILE = Path("/etc/tokens/github.token")

ENDPOINTS = {
    "repo": "/repos/{owner}/{repo}",
    "clones": "/repos/{owner}/{repo}/traffic/clones",
    "views": "/repos/{owner}/{repo}/traffic/views",
    "popular_paths": "/repos/{owner}/{repo}/traffic/popular/paths",
    "popular_referrers": "/repos/{owner}/{repo}/traffic/popular/referrers",
    "forks": "/repos/{owner}/{repo}/forks",
}


@dataclass(frozen=True)
class Settings:
    owner: str
    repos: list[str]
    db: Path
    token_file: Path
    config_file: Path | None
    discover_repos: bool
    repo_visibility: str
    repo_affiliation: str


@dataclass(frozen=True)
class ApiResult:
    endpoint: str
    url: str
    status_code: int | None
    ok: bool
    data: Any | None
    error: str | None
    headers: dict[str, str]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def utc_date() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def expand_path(raw_path: str | Path) -> Path:
    return Path(raw_path).expanduser().resolve()


def parse_bool(raw: str, default: bool = False) -> bool:
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "yes", "true", "on"}:
        return True
    if value in {"0", "no", "false", "off"}:
        return False
    return default


def split_config_repos(raw: str) -> list[str]:
    repos: list[str] = []
    for line in raw.splitlines():
        clean = line.strip()
        if clean and not clean.startswith("#"):
            repos.append(clean)
    return repos


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        clean = item.strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def read_repos_file(path: Path) -> list[str]:
    return split_config_repos(path.read_text(encoding="utf-8"))


def read_token(token_file: Path) -> str:
    if not token_file.exists():
        raise FileNotFoundError(f"Token file does not exist: {token_file}")
    token = token_file.read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError(f"Token file is empty: {token_file}")
    return token


def load_config(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")
    return parser


def resolve_settings(args: argparse.Namespace) -> Settings:
    config_path = expand_path(args.config) if args.config else DEFAULT_CONFIG
    config = load_config(config_path)

    owner = ""
    db = DEFAULT_DB
    token_file = DEFAULT_TOKEN_FILE
    repos: list[str] = []
    discover_repos = False
    repo_visibility = "all"
    repo_affiliation = "owner"

    if config.has_section("github"):
        owner = config.get("github", "owner", fallback=owner).strip()
        token_file = expand_path(config.get("github", "token_file", fallback=str(token_file)))
        discover_repos = parse_bool(config.get("github", "discover_repos", fallback="false"))
        repo_visibility = config.get("github", "repo_visibility", fallback=repo_visibility).strip()
        repo_affiliation = config.get("github", "repo_affiliation", fallback=repo_affiliation).strip()

    if config.has_section("storage"):
        db = expand_path(config.get("storage", "db", fallback=str(db)))

    if config.has_section("repos"):
        repos.extend(split_config_repos(config.get("repos", "names", fallback="")))

    if args.owner:
        owner = args.owner.strip()
    if args.db:
        db = expand_path(args.db)
    if args.token_file:
        token_file = expand_path(args.token_file)
    if args.repos_file:
        repos.extend(read_repos_file(expand_path(args.repos_file)))
    if args.repo:
        repos.extend(args.repo)
    if args.discover_repos:
        discover_repos = True
    if args.no_discover_repos:
        discover_repos = False

    repos = dedupe_preserve_order(repos)

    return Settings(
        owner=owner,
        repos=repos,
        db=db,
        token_file=token_file,
        config_file=config_path if config_path.exists() else None,
        discover_repos=discover_repos,
        repo_visibility=repo_visibility,
        repo_affiliation=repo_affiliation,
    )


def connect_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY,
            run_uuid TEXT UNIQUE NOT NULL,
            collected_at_utc TEXT NOT NULL,
            owner TEXT NOT NULL,
            dry_run INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        
        CREATE TABLE IF NOT EXISTS repository_metadata_snapshots (
            repository_id INTEGER NOT NULL,
            snapshot_date_utc TEXT NOT NULL,
            stargazers_count INTEGER NOT NULL,
            watchers_count INTEGER NOT NULL,
            subscribers_count INTEGER NOT NULL DEFAULT 0,
            forks_count INTEGER NOT NULL,
            open_issues_count INTEGER NOT NULL,
            source_run_id INTEGER NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            FOREIGN KEY(source_run_id) REFERENCES collection_runs(id),
            PRIMARY KEY(repository_id, snapshot_date_utc)
        );

        CREATE TABLE IF NOT EXISTS repository_forks (
            id INTEGER PRIMARY KEY,
            repository_id INTEGER NOT NULL,
            fork_full_name TEXT NOT NULL,
            fork_owner TEXT NOT NULL,
            fork_repo TEXT NOT NULL,
            fork_created_at TEXT,
            default_branch TEXT,
            html_url TEXT,
            pushed_at TEXT,
            stargazers_count INTEGER,
            collected_at_utc TEXT NOT NULL,
            UNIQUE(repository_id, fork_full_name)
        );


    
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY,
    owner TEXT NOT NULL,
    repo TEXT NOT NULL,
    github_id INTEGER,
    full_name TEXT,
    private INTEGER,
    fork INTEGER,
    archived INTEGER,
    disabled INTEGER,
    default_branch TEXT,
    html_url TEXT,
    pushed_at TEXT,
    github_updated_at TEXT,
            stargazers_count INTEGER DEFAULT 0,
            watchers_count INTEGER DEFAULT 0,
            subscribers_count INTEGER DEFAULT 0,
            forks_count INTEGER DEFAULT 0,
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    UNIQUE(owner, repo)
);


        CREATE TABLE IF NOT EXISTS repository_snapshots (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            repository_id INTEGER NOT NULL,
            github_id INTEGER,
            full_name TEXT,
            private INTEGER,
            fork INTEGER,
            archived INTEGER,
            disabled INTEGER,
            default_branch TEXT,
            html_url TEXT,
            pushed_at TEXT,
            github_updated_at TEXT,
            discovered_at_utc TEXT NOT NULL,
            raw_json TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES collection_runs(id),
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            UNIQUE(run_id, repository_id)
        );

        CREATE TABLE IF NOT EXISTS raw_api_responses (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            repository_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            url TEXT NOT NULL,
            status_code INTEGER,
            ok INTEGER NOT NULL,
            error TEXT,
            response_json TEXT,
            fetched_at_utc TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES collection_runs(id),
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            UNIQUE(run_id, repository_id, endpoint)
        );

        CREATE TABLE IF NOT EXISTS traffic_clones_daily (
            repository_id INTEGER NOT NULL,
            day_utc TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            source_run_id INTEGER NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            FOREIGN KEY(source_run_id) REFERENCES collection_runs(id),
            PRIMARY KEY(repository_id, day_utc)
        );

        CREATE TABLE IF NOT EXISTS traffic_views_daily (
            repository_id INTEGER NOT NULL,
            day_utc TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            source_run_id INTEGER NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            FOREIGN KEY(source_run_id) REFERENCES collection_runs(id),
            PRIMARY KEY(repository_id, day_utc)
        );

        CREATE TABLE IF NOT EXISTS popular_paths_snapshot (
            repository_id INTEGER NOT NULL,
            snapshot_date_utc TEXT NOT NULL,
            path TEXT NOT NULL,
            title TEXT,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            source_run_id INTEGER NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            FOREIGN KEY(source_run_id) REFERENCES collection_runs(id),
            PRIMARY KEY(repository_id, snapshot_date_utc, path)
        );

        CREATE TABLE IF NOT EXISTS popular_referrers_snapshot (
            repository_id INTEGER NOT NULL,
            snapshot_date_utc TEXT NOT NULL,
            referrer TEXT NOT NULL,
            count INTEGER NOT NULL,
            uniques INTEGER NOT NULL,
            source_run_id INTEGER NOT NULL,
            updated_at_utc TEXT NOT NULL,
            FOREIGN KEY(repository_id) REFERENCES repositories(id),
            FOREIGN KEY(source_run_id) REFERENCES collection_runs(id),
            PRIMARY KEY(repository_id, snapshot_date_utc, referrer)
        );
        """
    )

    ensure_column(conn, "repositories", "github_id", "INTEGER")
    ensure_column(conn, "repositories", "full_name", "TEXT")
    ensure_column(conn, "repositories", "private", "INTEGER")
    ensure_column(conn, "repositories", "fork", "INTEGER")
    ensure_column(conn, "repositories", "archived", "INTEGER")
    ensure_column(conn, "repositories", "disabled", "INTEGER")
    ensure_column(conn, "repositories", "default_branch", "TEXT")
    ensure_column(conn, "repositories", "html_url", "TEXT")
    ensure_column(conn, "repositories", "pushed_at", "TEXT")
    ensure_column(conn, "repositories", "github_updated_at", "TEXT")
    ensure_column(conn, "repositories", "stargazers_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "repositories", "watchers_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "repositories", "subscribers_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "repositories", "forks_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "repository_metadata_snapshots", "subscribers_count", "INTEGER DEFAULT 0")
    ensure_column(conn, "repositories", "updated_at_utc", "TEXT")

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_repositories_github_id
            ON repositories(github_id);

        CREATE INDEX IF NOT EXISTS idx_repository_snapshots_run
            ON repository_snapshots(run_id);

        CREATE INDEX IF NOT EXISTS idx_raw_api_responses_repo_endpoint
            ON raw_api_responses(repository_id, endpoint);

        CREATE INDEX IF NOT EXISTS idx_clones_day
            ON traffic_clones_daily(day_utc);

        CREATE INDEX IF NOT EXISTS idx_views_day
            ON traffic_views_daily(day_utc);

        CREATE INDEX IF NOT EXISTS idx_paths_snapshot
            ON popular_paths_snapshot(snapshot_date_utc);

        CREATE INDEX IF NOT EXISTS idx_referrers_snapshot
            ON popular_referrers_snapshot(snapshot_date_utc);
        """
    )
    backfill_repository_metadata_from_stored_json(conn)
    conn.commit()


def ensure_column(conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    existing = {row["name"] for row in rows}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def backfill_repository_metadata_from_stored_json(conn: sqlite3.Connection) -> None:
    raw_rows = conn.execute(
        """
        WITH latest_repo_raw AS (
            SELECT repository_id, MAX(id) AS id
            FROM raw_api_responses
            WHERE endpoint = 'repo'
              AND ok = 1
              AND response_json IS NOT NULL
            GROUP BY repository_id
        )
        SELECT raw.repository_id, raw.response_json
        FROM raw_api_responses raw
        JOIN latest_repo_raw latest ON latest.id = raw.id
        """
    ).fetchall()

    raw_repo_ids: set[int] = set()
    for row in raw_rows:
        raw_repo_ids.add(int(row["repository_id"]))
        try:
            repo_json = json.loads(row["response_json"])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid stored repo metadata JSON for repository_id={row['repository_id']}") from exc
        if not isinstance(repo_json, dict):
            raise RuntimeError(f"Stored repo metadata is not an object for repository_id={row['repository_id']}")
        update_repository_metadata(conn, int(row["repository_id"]), repo_json)

    snapshot_rows = conn.execute(
        """
        WITH latest_snapshot AS (
            SELECT repository_id, MAX(id) AS id
            FROM repository_snapshots
            WHERE raw_json IS NOT NULL
            GROUP BY repository_id
        )
        SELECT s.repository_id, s.raw_json
        FROM repository_snapshots s
        JOIN latest_snapshot latest ON latest.id = s.id
        """
    ).fetchall()

    for row in snapshot_rows:
        repository_id = int(row["repository_id"])
        if repository_id in raw_repo_ids:
            continue
        try:
            repo_json = json.loads(row["raw_json"])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid stored repository snapshot JSON for repository_id={repository_id}") from exc
        if not isinstance(repo_json, dict):
            raise RuntimeError(f"Stored repository snapshot is not an object for repository_id={repository_id}")
        update_repository_metadata(conn, repository_id, repo_json)


def create_run(conn: sqlite3.Connection, owner: str, dry_run: bool) -> int:
    now = utc_now_iso()
    cur = conn.execute(
        """
        INSERT INTO collection_runs (
            run_uuid,
            collected_at_utc,
            owner,
            dry_run,
            status,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), now, owner, int(dry_run), "running", now),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    conn.execute("UPDATE collection_runs SET status = ? WHERE id = ?", (status, run_id))
    conn.commit()


def ensure_repository(conn: sqlite3.Connection, owner: str, repo: str) -> int:
    now = utc_now_iso()
    conn.execute(
        """
        INSERT OR IGNORE INTO repositories (owner, repo, created_at_utc, updated_at_utc)
        VALUES (?, ?, ?, ?)
        """,
        (owner, repo, now, now),
    )
    conn.execute(
        "UPDATE repositories SET updated_at_utc = ? WHERE owner = ? AND repo = ?",
        (now, owner, repo),
    )
    row = conn.execute(
        "SELECT id FROM repositories WHERE owner = ? AND repo = ?",
        (owner, repo),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Could not resolve repository row for {owner}/{repo}")
    return int(row["id"])


def update_repository_metadata(conn: sqlite3.Connection, repository_id: int, repo_json: dict[str, Any]) -> None:
    owner_login = ""
    owner_data = repo_json.get("owner")
    if isinstance(owner_data, dict):
        owner_login = str(owner_data.get("login") or "")

    repo_name = str(repo_json.get("name") or "")
    now = utc_now_iso()

    conn.execute(
        """
        UPDATE repositories
        SET
            github_id = ?,
            full_name = ?,
            private = ?,
            fork = ?,
            archived = ?,
            disabled = ?,
            default_branch = ?,
            html_url = ?,
            pushed_at = ?,
            github_updated_at = ?,
            stargazers_count = ?,
            watchers_count = ?,
            subscribers_count = ?,
            forks_count = ?,
            updated_at_utc = ?
        WHERE id = ?
        """,
        (
            repo_json.get("id"),
            repo_json.get("full_name"),
            int(bool(repo_json.get("private"))),
            int(bool(repo_json.get("fork"))),
            int(bool(repo_json.get("archived"))),
            int(bool(repo_json.get("disabled"))),
            repo_json.get("default_branch"),
            repo_json.get("html_url"),
            repo_json.get("pushed_at"),
            repo_json.get("updated_at"),
            int(repo_json.get("stargazers_count") or 0),
            int(repo_json.get("watchers_count") or 0),
            int(repo_json.get("subscribers_count") or 0),
            int(repo_json.get("forks_count") or repo_json.get("forks") or 0),
            now,
            repository_id,
        ),
    )

    if owner_login and repo_name:
        conn.execute(
            """
            UPDATE repositories
            SET owner = ?, repo = ?
            WHERE id = ?
            """,
            (owner_login, repo_name, repository_id),
        )


def store_repository_snapshot(
    conn: sqlite3.Connection,
    run_id: int,
    repository_id: int,
    repo_json: dict[str, Any],
) -> None:
    conn.execute(
        """
        INSERT INTO repository_snapshots (
            run_id,
            repository_id,
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
            discovered_at_utc,
            raw_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, repository_id)
        DO UPDATE SET
            github_id = excluded.github_id,
            full_name = excluded.full_name,
            private = excluded.private,
            fork = excluded.fork,
            archived = excluded.archived,
            disabled = excluded.disabled,
            default_branch = excluded.default_branch,
            html_url = excluded.html_url,
            pushed_at = excluded.pushed_at,
            github_updated_at = excluded.github_updated_at,
            discovered_at_utc = excluded.discovered_at_utc,
            raw_json = excluded.raw_json
        """,
        (
            run_id,
            repository_id,
            repo_json.get("id"),
            repo_json.get("full_name"),
            int(bool(repo_json.get("private"))),
            int(bool(repo_json.get("fork"))),
            int(bool(repo_json.get("archived"))),
            int(bool(repo_json.get("disabled"))),
            repo_json.get("default_branch"),
            repo_json.get("html_url"),
            repo_json.get("pushed_at"),
            repo_json.get("updated_at"),
            utc_now_iso(),
            json.dumps(repo_json, sort_keys=True, ensure_ascii=False),
        ),
    )


def parse_next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        match = re.match(r'\s*<([^>]+)>;\s*rel="([^"]+)"', part.strip())
        if match and match.group(2) == "next":
            return match.group(1)
    return None


def github_get_url(token: str, url: str, endpoint: str) -> ApiResult:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jarri-github-traffic-collector",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
            data = json.loads(body) if body else None
            headers = {key.lower(): value for key, value in response.headers.items()}
            return ApiResult(endpoint, url, int(response.status), True, data, None, headers)

    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        parsed: Any | None = None
        error = f"HTTP {exc.code}"
        if body:
            try:
                parsed = json.loads(body)
                if isinstance(parsed, dict) and parsed.get("message"):
                    error = f"HTTP {exc.code}: {parsed['message']}"
            except json.JSONDecodeError:
                error = f"HTTP {exc.code}: non-JSON error body"
        headers = {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {}
        return ApiResult(endpoint, url, int(exc.code), False, parsed, error, headers)

    except urllib.error.URLError as exc:
        return ApiResult(endpoint, url, None, False, None, f"URL error: {exc.reason}", {})

    except TimeoutError:
        return ApiResult(endpoint, url, None, False, None, "Timeout", {})


def github_get(token: str, owner: str, repo: str, endpoint: str) -> ApiResult:
    api_path = ENDPOINTS[endpoint].format(owner=owner, repo=repo)
    return github_get_url(token, f"https://api.github.com{api_path}", endpoint)


def discover_repositories(token: str, settings: Settings, verbose: bool) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "visibility": settings.repo_visibility,
            "affiliation": settings.repo_affiliation,
            "per_page": "100",
            "sort": "full_name",
            "direction": "asc",
        }
    )
    url: str | None = f"https://api.github.com/user/repos?{params}"
    repos: list[dict[str, Any]] = []

    while url:
        result = github_get_url(token, url, "discover_repos")
        if not result.ok:
            raise RuntimeError(result.error or "repository discovery failed")

        if not isinstance(result.data, list):
            raise RuntimeError("repository discovery returned non-list payload")

        for repo_json in result.data:
            if not isinstance(repo_json, dict):
                continue
            owner_data = repo_json.get("owner")
            owner_login = owner_data.get("login") if isinstance(owner_data, dict) else None
            if owner_login == settings.owner:
                repos.append(repo_json)

        url = parse_next_link(result.headers.get("link"))

    if verbose:
        print(f"Discovered owner repos: {len(repos)}")

    return repos


def store_raw_response(
    conn: sqlite3.Connection,
    run_id: int,
    repository_id: int,
    result: ApiResult,
) -> None:
    conn.execute(
        """
        INSERT INTO raw_api_responses (
            run_id,
            repository_id,
            endpoint,
            url,
            status_code,
            ok,
            error,
            response_json,
            fetched_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id, repository_id, endpoint)
        DO UPDATE SET
            url = excluded.url,
            status_code = excluded.status_code,
            ok = excluded.ok,
            error = excluded.error,
            response_json = excluded.response_json,
            fetched_at_utc = excluded.fetched_at_utc
        """,
        (
            run_id,
            repository_id,
            result.endpoint,
            result.url,
            result.status_code,
            int(result.ok),
            result.error,
            json.dumps(result.data, sort_keys=True, ensure_ascii=False) if result.data is not None else None,
            utc_now_iso(),
        ),
    )


def normalize_clones(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> bool:
    changed = False
    if not isinstance(data, dict) or not isinstance(data.get("clones"), list):
        return changed
    now = utc_now_iso()
    for item in data["clones"]:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        day_utc = timestamp[:10]
        count = int(item.get("count") or 0)
        uniques = int(item.get("uniques") or 0)

        existing = conn.execute(
            """
            SELECT count, uniques
            FROM traffic_clones_daily
            WHERE repository_id = ? AND day_utc = ?
            """,
            (repository_id, day_utc),
        ).fetchone()

        if existing is None or int(existing["count"]) != count or int(existing["uniques"]) != uniques:
            changed = True

        conn.execute(
            """
            INSERT INTO traffic_clones_daily (
                repository_id, day_utc, count, uniques, source_run_id, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, day_utc)
            DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                source_run_id = excluded.source_run_id,
                updated_at_utc = excluded.updated_at_utc
            """,
            (repository_id, day_utc, count, uniques, run_id, now),
        )

    return changed


def normalize_views(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> bool:
    changed = False
    if not isinstance(data, dict) or not isinstance(data.get("views"), list):
        return changed
    now = utc_now_iso()
    for item in data["views"]:
        if not isinstance(item, dict):
            continue
        timestamp = item.get("timestamp")
        if not isinstance(timestamp, str):
            continue
        day_utc = timestamp[:10]
        count = int(item.get("count") or 0)
        uniques = int(item.get("uniques") or 0)

        existing = conn.execute(
            """
            SELECT count, uniques
            FROM traffic_views_daily
            WHERE repository_id = ? AND day_utc = ?
            """,
            (repository_id, day_utc),
        ).fetchone()

        if existing is None or int(existing["count"]) != count or int(existing["uniques"]) != uniques:
            changed = True

        conn.execute(
            """
            INSERT INTO traffic_views_daily (
                repository_id, day_utc, count, uniques, source_run_id, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, day_utc)
            DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                source_run_id = excluded.source_run_id,
                updated_at_utc = excluded.updated_at_utc
            """,
            (repository_id, day_utc, count, uniques, run_id, now),
        )

    return changed


def normalize_popular_paths(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> None:
    if not isinstance(data, list):
        return
    snapshot_date = utc_date()
    now = utc_now_iso()
    for item in data:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        if not isinstance(path, str):
            continue
        conn.execute(
            """
            INSERT INTO popular_paths_snapshot (
                repository_id, snapshot_date_utc, path, title, count, uniques, source_run_id, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, snapshot_date_utc, path)
            DO UPDATE SET
                title = excluded.title,
                count = excluded.count,
                uniques = excluded.uniques,
                source_run_id = excluded.source_run_id,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                repository_id,
                snapshot_date,
                path,
                item.get("title"),
                int(item.get("count") or 0),
                int(item.get("uniques") or 0),
                run_id,
                now,
            ),
        )


def normalize_popular_referrers(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> None:
    if not isinstance(data, list):
        return
    snapshot_date = utc_date()
    now = utc_now_iso()
    for item in data:
        if not isinstance(item, dict):
            continue
        referrer = item.get("referrer")
        if not isinstance(referrer, str):
            continue
        conn.execute(
            """
            INSERT INTO popular_referrers_snapshot (
                repository_id, snapshot_date_utc, referrer, count, uniques, source_run_id, updated_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, snapshot_date_utc, referrer)
            DO UPDATE SET
                count = excluded.count,
                uniques = excluded.uniques,
                source_run_id = excluded.source_run_id,
                updated_at_utc = excluded.updated_at_utc
            """,
            (
                repository_id,
                snapshot_date,
                referrer,
                int(item.get("count") or 0),
                int(item.get("uniques") or 0),
                run_id,
                now,
            ),
        )



def normalize_endpoint(conn: sqlite3.Connection, run_id: int, repository_id: int, result: ApiResult) -> bool:
    if not result.ok:
        return False

    if result.endpoint == "clones":
        return normalize_clones(conn, run_id, repository_id, result.data)

    if result.endpoint == "views":
        return normalize_views(conn, run_id, repository_id, result.data)

    if result.endpoint == "popular_paths":
        normalize_popular_paths(conn, run_id, repository_id, result.data)
        return False

    if result.endpoint == "popular_referrers":
        normalize_popular_referrers(conn, run_id, repository_id, result.data)
        return False

    if result.endpoint == "forks":
        return normalize_forks(conn, run_id, repository_id, result.data)

    if result.endpoint == "repo":
        update_repository_metadata(conn, repository_id, result.data)
        normalize_repository_metadata_snapshot(conn, run_id, repository_id, result.data)
        return False

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GitHub repository traffic statistics into local SQLite.")
    parser.add_argument("--config", help=f"INI config path. Default: {DEFAULT_CONFIG}")
    parser.add_argument("--owner", help="GitHub owner/org. Overrides config.")
    parser.add_argument("--repo", action="append", default=[], help="Repository name. Can be repeated. Adds to config/discovered repos.")
    parser.add_argument("--repos-file", help="Text file with one repository name per line. Adds to config/discovered repos.")
    parser.add_argument("--db", help="SQLite database path. Overrides config.")
    parser.add_argument("--token-file", help="GitHub token file. Overrides config.")
    parser.add_argument("--discover-repos", action="store_true", help="Enable authenticated repository discovery.")
    parser.add_argument("--no-discover-repos", action="store_true", help="Disable repository discovery even if config enables it.")
    parser.add_argument("--dry-run", action="store_true", help="Initialize DB and show planned requests without calling traffic endpoints.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed non-secret progress.")
    return parser.parse_args()


def normalize_repository_metadata_snapshot(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> None:
    if not isinstance(data, dict):
        return

    now = utc_now_iso()
    snapshot_date = utc_date()

    conn.execute("""
        INSERT INTO repository_metadata_snapshots (
            repository_id,
            snapshot_date_utc,
            stargazers_count,
            watchers_count,
            subscribers_count,
            forks_count,
            open_issues_count,
            source_run_id,
            updated_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(repository_id, snapshot_date_utc)
        DO UPDATE SET
            stargazers_count = excluded.stargazers_count,
            watchers_count = excluded.watchers_count,
            subscribers_count = excluded.subscribers_count,
            forks_count = excluded.forks_count,
            open_issues_count = excluded.open_issues_count,
            source_run_id = excluded.source_run_id,
            updated_at_utc = excluded.updated_at_utc
    """, (
        repository_id,
        snapshot_date,
        int(data.get("stargazers_count") or 0),
        int(data.get("watchers_count") or 0),
        int(data.get("subscribers_count") or 0),
        int(data.get("forks_count") or data.get("forks") or 0),
        int(data.get("open_issues_count") or 0),
        run_id,
        now,
    ))


def normalize_forks(conn: sqlite3.Connection, run_id: int, repository_id: int, data: Any) -> bool:
    if not isinstance(data, list):
        return False

    now = utc_now_iso()
    changed = False

    for item in data:
        if not isinstance(item, dict):
            continue

        owner = item.get("owner") or {}
        if not isinstance(owner, dict):
            owner = {}

        conn.execute("""
            INSERT INTO repository_forks (
                repository_id,
                fork_full_name,
                fork_owner,
                fork_repo,
                fork_created_at,
                default_branch,
                html_url,
                pushed_at,
                stargazers_count,
                collected_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(repository_id, fork_full_name)
            DO UPDATE SET
                fork_created_at = excluded.fork_created_at,
                default_branch = excluded.default_branch,
                html_url = excluded.html_url,
                pushed_at = excluded.pushed_at,
                stargazers_count = excluded.stargazers_count,
                collected_at_utc = excluded.collected_at_utc
        """, (
            repository_id,
            item.get("full_name"),
            owner.get("login"),
            item.get("name"),
            item.get("created_at"),
            item.get("default_branch"),
            item.get("html_url"),
            item.get("pushed_at"),
            int(item.get("stargazers_count") or 0),
            now
        ))

        changed = True

    return changed

def main() -> int:
    args = parse_args()
    settings = resolve_settings(args)

    if not settings.owner:
        print("ERROR: owner missing. Set [github] owner in config or pass --owner.", file=sys.stderr)
        return 2

    if args.verbose or args.dry_run:
        print(f"Config: {settings.config_file or 'not found'}")
        print(f"Owner: {settings.owner}")
        print(f"Configured repos: {', '.join(settings.repos) if settings.repos else '(none)'}")
        print(f"Discover repos: {settings.discover_repos}")
        print(f"Discovery visibility: {settings.repo_visibility}")
        print(f"Discovery affiliation: {settings.repo_affiliation}")
        print(f"Database: {settings.db}")
        print(f"Token file: {settings.token_file}")
        print(f"Dry run: {args.dry_run}")

    conn = connect_db(settings.db)
    init_schema(conn)
    run_id = create_run(conn, settings.owner, args.dry_run)
    failures = 0
    daily_data_changed = False

    try:
        token = None if args.dry_run and not settings.discover_repos else read_token(settings.token_file)

        discovered_json: list[dict[str, Any]] = []
        discovered_names: list[str] = []

        if settings.discover_repos:
            if token is None:
                token = read_token(settings.token_file)
            discovered_json = discover_repositories(token, settings, args.verbose or args.dry_run)
            for repo_json in discovered_json:
                name = repo_json.get("name")
                if isinstance(name, str) and name:
                    discovered_names.append(name)

        final_repos = dedupe_preserve_order(settings.repos + discovered_names)

        if not final_repos:
            finish_run(conn, run_id, "failed")
            print("ERROR: no repositories configured or discovered.", file=sys.stderr)
            return 2

        repo_metadata_by_name = {
            str(repo_json.get("name")): repo_json
            for repo_json in discovered_json
            if isinstance(repo_json.get("name"), str)
        }

        for repo in final_repos:
            repository_id = ensure_repository(conn, settings.owner, repo)
            repo_json = repo_metadata_by_name.get(repo)
            if repo_json:
                update_repository_metadata(conn, repository_id, repo_json)
                store_repository_snapshot(conn, run_id, repository_id, repo_json)
            conn.commit()

        if args.dry_run:
            for repo in final_repos:
                for endpoint, template in ENDPOINTS.items():
                    url = "https://api.github.com" + template.format(owner=settings.owner, repo=repo)
                    print(f"DRY RUN {repo} {endpoint}: {url}")
            finish_run(conn, run_id, "dry_run")
            return 0

        if token is None:
            token = read_token(settings.token_file)

        for repo in final_repos:
            repository_id = ensure_repository(conn, settings.owner, repo)

            if args.verbose:
                print(f"Collecting {settings.owner}/{repo}")

            for endpoint in ENDPOINTS:
                result = github_get(token, settings.owner, repo, endpoint)
                store_raw_response(conn, run_id, repository_id, result)
                if normalize_endpoint(conn, run_id, repository_id, result):
                    daily_data_changed = True
                conn.commit()

                if result.ok:
                    if args.verbose:
                        print(f"  OK {endpoint} HTTP {result.status_code}")
                else:
                    failures += 1
                    print(f"  FAIL {settings.owner}/{repo} {endpoint}: {result.error or 'unknown error'}", file=sys.stderr)

        if failures:
            finish_run(conn, run_id, "completed_with_failures")
            return 1

        finish_run(
            conn,
            run_id,
            "completed_new_daily_data" if daily_data_changed else "completed_no_new_daily_data",
        )
        return 0

    except Exception as exc:
        finish_run(conn, run_id, "failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
