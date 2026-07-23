#!/usr/bin/env python3
"""Safe stdin-to-argv adapter and read-only health check for orderdesk-kb."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FALLBACK_BIN = ROOT / "bin" / "orderdesk-kb"
FALLBACK_DB = ROOT / "kb.db"
MODES = ("auto", "lexical", "semantic", "hybrid")
QUERY_COMMANDS = ("ask", "search", "triage")


def parse_query_line(line: str) -> str:
    if len(line) > 16_384:
        raise ValueError("query input is too large")
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError("stdin must contain one JSON string followed by a newline") from exc
    if not isinstance(value, str):
        raise ValueError("query input must be a JSON string")
    normalized = " ".join(value.split())
    if not normalized:
        raise ValueError("query must not be empty")
    if "\x00" in normalized or any(
        ord(char) < 32 and char not in "\t\n\r" for char in normalized
    ):
        raise ValueError("query contains unsupported control characters")
    return normalized


def resolve_binary() -> Path:
    configured = os.environ.get("ORDERDESK_KB_BIN")
    if configured:
        path = Path(configured).expanduser()
    elif FALLBACK_BIN.is_file():
        path = FALLBACK_BIN
    else:
        discovered = shutil.which("orderdesk-kb")
        path = Path(discovered) if discovered else FALLBACK_BIN
    if not path.is_file():
        raise FileNotFoundError(f"orderdesk-kb executable not found at {path}")
    return path.resolve()


def resolve_db() -> Path:
    configured = os.environ.get("ORDERDESK_KB_DB")
    path = Path(configured).expanduser() if configured else FALLBACK_DB
    if not path.is_file():
        raise FileNotFoundError(f"Order Desk KB database not found at {path}")
    return path.resolve()


def build_argv(args: argparse.Namespace, query: str) -> list[str]:
    argv = [
        str(resolve_binary()),
        "--db",
        str(resolve_db()),
        "--json",
        args.command,
    ]
    if args.command in ("search", "triage"):
        argv.extend(["--limit", str(args.limit)])
    argv.extend(["--mode", args.mode, query])
    return argv


def iso_age_days(value: str | None) -> float | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    seconds = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    return round(seconds / 86400, 1)


def health_payload() -> dict:
    db_path = resolve_db()
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        pages = connection.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
        sections = connection.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
        oldest, newest = connection.execute(
            "SELECT MIN(synced_at), MAX(synced_at) FROM pages"
        ).fetchone()
        embeddings = connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    finally:
        connection.close()
    modified = datetime.fromtimestamp(db_path.stat().st_mtime, timezone.utc).isoformat()
    return {
        "ok": True,
        "db": str(db_path),
        "pages": pages,
        "sections": sections,
        "embedded": embeddings,
        "oldest_page_fetched_at": oldest,
        "newest_page_fetched_at": newest,
        "newest_page_age_days": iso_age_days(newest),
        "index_file_modified_at": modified,
        "freshness_caveat": (
            "Page-fetch and file timestamps do not prove that every live help page is unchanged."
        ),
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=(*QUERY_COMMANDS, "health"))
    result.add_argument("--limit", type=int, default=8)
    result.add_argument("--mode", choices=MODES, default="auto")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 1 <= args.limit <= 25:
        raise SystemExit("--limit must be between 1 and 25")
    if args.command == "health":
        print(json.dumps(health_payload(), indent=2))
        return 0

    try:
        query = parse_query_line(sys.stdin.readline(16_385))
        command = build_argv(args, query)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        print(completed.stderr.strip() or "orderdesk-kb failed", file=sys.stderr)
        return completed.returncode
    try:
        json.loads(completed.stdout)
    except json.JSONDecodeError:
        print("error: orderdesk-kb returned invalid JSON", file=sys.stderr)
        return 2
    sys.stdout.write(completed.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
