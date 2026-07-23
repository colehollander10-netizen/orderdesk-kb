"""Crawl the public KB into the local index — incremental and polite.

Strategy:
  1. Read the sitemap for every URL + its lastmod.
  2. Skip URLs whose lastmod already matches the index (incremental re-sync;
     Order Desk ships monthly, so most pages are unchanged each run).
  3. For the rest, extract + chunk with one worker and a global rate limit,
     then upsert. Empty (category) pages are recorded but contribute no
     sections.

Concurrency is deliberately serialized by default and a per-request delay is
enforced: as a future Order Desk intern, this should read as a courteous
client, not a scraper.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone

from . import index as index_mod
from .extract import extract_page
from .sitemap import SitemapEntry, fetch_all_entries

DEFAULT_MAX_WORKERS = 1
DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS = 2.0  # global rate limit across workers


@dataclass
class SyncResult:
    fetched: int = 0
    skipped: int = 0
    empty: int = 0
    failed: int = 0
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


class _RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
            self._next_allowed = time.monotonic() + self._min_interval


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sync(
    conn: sqlite3.Connection,
    force: bool = False,
    limit: int | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    min_interval: float = DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS,
    progress=lambda msg: None,
) -> SyncResult:
    """Run a full incremental sync. `limit` caps pages for de-risk runs."""
    index_mod.init_schema(conn)
    limiter = _RateLimiter(min_interval)
    entries = fetch_all_entries(before_request=limiter.wait)
    if limit is not None:
        entries = entries[:limit]
    progress(f"sitemap: {len(entries)} URLs")

    to_fetch: list[SitemapEntry] = []
    result = SyncResult()
    for entry in entries:
        if not force and index_mod.get_lastmod(conn, entry.url) == entry.lastmod:
            result.skipped += 1
        else:
            to_fetch.append(entry)
    progress(f"to fetch: {len(to_fetch)} (skipped {result.skipped} unchanged)")

    def work(entry: SitemapEntry):
        limiter.wait()
        page = extract_page(entry.url)
        return entry, page

    # Writes happen on the main thread; sqlite connections aren't thread-safe.
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(work, e): e for e in to_fetch}
        for future in as_completed(futures):
            entry = futures[future]
            try:
                entry, page = future.result()
            except Exception as exc:  # noqa: BLE001 — record & continue per page
                result.failed += 1
                result.errors.append(f"{entry.url}: {exc}")
                progress(f"  FAIL {entry.url} ({exc})")
                continue

            index_mod.upsert_page(
                conn,
                url=page.url,
                title=page.title,
                lastmod=entry.lastmod,
                published=page.published,
                word_count=page.word_count,
                synced_at=_now_iso(),
                sections=page.sections,
            )
            if page.sections:
                result.fetched += 1
                progress(f"  ok   {page.title} ({len(page.sections)} sections)")
            else:
                result.empty += 1
                progress(f"  --   {page.title} (no content, skipped)")
    conn.commit()
    return result
