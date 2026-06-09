"""SQLite FTS5 index for the Order Desk knowledge base.

One file (`kb.db`) is the entire portable artifact: copy it and the CLI works
offline with no network, no API key, no server. FTS5 gives us BM25 ranking out
of the box, which is plenty for a few-thousand-section corpus.

Schema:
  pages    — one row per crawled URL, with last-seen sitemap lastmod so `sync`
             can skip unchanged pages incrementally.
  sections — FTS5 virtual table; the searchable unit. We keep the heading path
             and body in the index and join nothing else, so a query is a
             single MATCH.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .extract import Section

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "kb.db"


@dataclass(frozen=True)
class Hit:
    """One search result row."""

    rank: float        # BM25 score (lower is a better match in SQLite)
    title: str
    heading_path: str
    anchor_url: str
    snippet: str
    text: str


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            url        TEXT PRIMARY KEY,
            title      TEXT NOT NULL,
            lastmod    TEXT,
            published  TEXT,
            word_count INTEGER,
            synced_at  TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS sections USING fts5(
            url UNINDEXED,
            anchor_url UNINDEXED,
            title,
            heading_path,
            text,
            tokenize = 'porter unicode61'
        );
        """
    )
    conn.commit()


def get_lastmod(conn: sqlite3.Connection, url: str) -> str | None:
    row = conn.execute("SELECT lastmod FROM pages WHERE url = ?", (url,)).fetchone()
    return row["lastmod"] if row else None


def delete_page_sections(conn: sqlite3.Connection, url: str) -> None:
    """Remove a page's existing sections before re-inserting (idempotent sync)."""
    conn.execute("DELETE FROM sections WHERE url = ?", (url,))


def upsert_page(
    conn: sqlite3.Connection,
    url: str,
    title: str,
    lastmod: str,
    published: str,
    word_count: int,
    synced_at: str,
    sections: list[Section],
) -> None:
    """Replace a page and all its sections in one transaction."""
    delete_page_sections(conn, url)
    conn.execute(
        """
        INSERT INTO pages (url, title, lastmod, published, word_count, synced_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title=excluded.title,
            lastmod=excluded.lastmod,
            published=excluded.published,
            word_count=excluded.word_count,
            synced_at=excluded.synced_at
        """,
        (url, title, lastmod, published, word_count, synced_at),
    )
    conn.executemany(
        """
        INSERT INTO sections (url, anchor_url, title, heading_path, text)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (s.url, s.anchor_url, s.title, s.heading_path, s.text)
            for s in sections
        ],
    )


def stats(conn: sqlite3.Connection) -> dict:
    pages = conn.execute("SELECT COUNT(*) AS n FROM pages").fetchone()["n"]
    sections = conn.execute("SELECT COUNT(*) AS n FROM sections").fetchone()["n"]
    return {"pages": pages, "sections": sections}


# Common words that carry no retrieval signal. Without this, "what is order
# desk?" OR-searches `what`/`is` against every doc, inflating junk matches and
# diluting the real terms. (BM25 magnitude isn't comparable across queries, so
# removing noise terms matters more than threshold tuning.)
_STOPWORDS = frozenset(
    """a an and are as at be by can do does for from how i in is it of on or
    that the to was what when where which who why will with you your""".split()
)


def _query_terms(query: str) -> list[str]:
    """Lowercase, drop punctuation-only tokens and stopwords."""
    raw = re.findall(r"[a-z0-9]+", query.lower())
    terms = [t for t in raw if t not in _STOPWORDS]
    # If the query is ALL stopwords (e.g. "how do I"), fall back to the raw
    # words so we still return something rather than erroring on empty MATCH.
    return terms or raw


def _escape_query(query: str) -> str:
    """Build a safe FTS5 OR-query from content terms only.

    FTS5 treats characters like ? and - as syntax; quoting each term makes it a
    safe phrase so natural questions never raise a syntax error.
    """
    terms = _query_terms(query)
    return " OR ".join(f'"{t}"' for t in terms) if terms else '""'


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 8,
) -> list[Hit]:
    """Ranked BM25 search. Weights title/heading above body text."""
    match = _escape_query(query)
    rows = conn.execute(
        """
        SELECT
            bm25(sections, 0.0, 0.0, 5.0, 3.0, 1.0) AS rank,
            title,
            heading_path,
            anchor_url,
            snippet(sections, 4, '[', ']', ' … ', 12) AS snippet,
            text
        FROM sections
        WHERE sections MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (match, limit),
    ).fetchall()
    return [
        Hit(
            rank=row["rank"],
            title=row["title"],
            heading_path=row["heading_path"],
            anchor_url=row["anchor_url"],
            snippet=row["snippet"],
            text=row["text"],
        )
        for row in rows
    ]
