"""SQLite FTS5 index for the Order Desk knowledge base.

One file (`kb.db`) is the entire portable artifact: copy it and the CLI works
offline with no network, no API key, no server. FTS5 gives us BM25 ranking out
of the box, which is plenty for a few-thousand-section corpus.

Schema:
  pages      — one row per crawled URL, with last-seen sitemap lastmod so
               `sync` can skip unchanged pages incrementally.
  sections   — FTS5 virtual table; the searchable unit. We keep the heading
               path and body in the index and join nothing else, so a query is
               a single MATCH.
  embeddings — optional, one unit vector per section rowid (see embed.py).
               Created lazily; lexical search never touches it, so a kb.db
               without embeddings keeps working exactly as before.

Three retrieval modes build on this:
  search()          lexical BM25 (AND-first, OR fallback)
  semantic_search() nearest-vector by cosine similarity
  hybrid_search()   both, fused with Reciprocal Rank Fusion
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from .extract import Section

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "kb.db"


@dataclass(frozen=True)
class Hit:
    """One search result row.

    `rank` always sorts lower-is-better so callers can treat modes uniformly:
    BM25 score for lexical hits, negated cosine for semantic hits, negated
    fused score for hybrid hits. `similarity` is the raw cosine (0.0 when the
    hit never went through the vector index) — unlike BM25 it IS comparable
    across queries, which is what makes absolute confidence labels possible.
    """

    rank: float        # lower is a better match, in every mode
    title: str
    heading_path: str
    anchor_url: str
    snippet: str
    text: str
    similarity: float = 0.0  # cosine vs. the query; 0.0 = unknown/lexical-only
    rowid: int = -1          # sections rowid; internal key for rank fusion
    # Page-level provenance carried through retrieval for support triage.
    # `lastmod` comes from the public sitemap, `published` from page metadata,
    # and `synced_at` is only the local fetch/index time.
    lastmod: str | None = None
    published: str | None = None
    synced_at: str | None = None


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

        -- Optional semantic layer (embed.py). section_id mirrors the FTS
        -- rowid of the embedded section; url is denormalized so a page's
        -- vectors can be dropped together when the page is re-synced.
        CREATE TABLE IF NOT EXISTS embeddings (
            section_id INTEGER PRIMARY KEY,
            url        TEXT NOT NULL,
            vector     BLOB NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_embeddings_url ON embeddings(url);

        -- Which model produced the vectors. Embedding spaces are not
        -- compatible across models, so a model change must force a re-embed
        -- rather than silently mixing geometries.
        CREATE TABLE IF NOT EXISTS embedding_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    conn.commit()


def get_lastmod(conn: sqlite3.Connection, url: str) -> str | None:
    row = conn.execute("SELECT lastmod FROM pages WHERE url = ?", (url,)).fetchone()
    return row["lastmod"] if row else None


def delete_page_sections(conn: sqlite3.Connection, url: str) -> None:
    """Remove a page's existing sections before re-inserting (idempotent sync).

    Vectors go with them: re-inserting sections assigns NEW rowids, so stale
    embeddings keyed by the old rowids would point at the wrong (or no) text.
    """
    conn.execute("DELETE FROM sections WHERE url = ?", (url,))
    conn.execute("DELETE FROM embeddings WHERE url = ?", (url,))


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
    return {
        "pages": pages,
        "sections": sections,
        "embedded": _embedded_count(conn),
        "embedding_model": _embedding_model(conn),
    }


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _embedded_count(conn: sqlite3.Connection) -> int:
    # Pre-semantic databases have no embeddings table; treat as zero rather
    # than forcing a write (the db may be opened read-only).
    if not _has_table(conn, "embeddings"):
        return 0
    return conn.execute("SELECT COUNT(*) AS n FROM embeddings").fetchone()["n"]


def _embedding_model(conn: sqlite3.Connection) -> str | None:
    if not _has_table(conn, "embedding_meta"):
        return None
    row = conn.execute(
        "SELECT value FROM embedding_meta WHERE key = 'model'"
    ).fetchone()
    return row["value"] if row else None


def embeddings_ready(conn: sqlite3.Connection) -> bool:
    """True when the index has vectors to search against."""
    return _embedded_count(conn) > 0


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


def _match_candidates(query: str) -> list[str]:
    """FTS5 match strings to try in order: all-terms AND, then any-term OR.

    OR alone floods results with weak single-word matches — "connect shopify"
    would rank every section mentioning "connect" anywhere. Requiring all
    terms first is far more precise; OR stays as the fallback so a query with
    one off-corpus word (a typo, a product name we don't index) still returns
    something instead of nothing.
    """
    terms = _query_terms(query)
    if not terms:
        return ['""']
    quoted = [f'"{t}"' for t in terms]
    if len(quoted) == 1:
        return [quoted[0]]
    return [" AND ".join(quoted), " OR ".join(quoted)]


def search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 8,
) -> list[Hit]:
    """Ranked BM25 search. Weights title/heading above body text."""
    for match in _match_candidates(query):
        rows = conn.execute(
            """
            SELECT
                sections.rowid AS rowid,
                bm25(sections, 0.0, 0.0, 5.0, 3.0, 1.0) AS rank,
                sections.title AS title,
                sections.heading_path AS heading_path,
                sections.anchor_url AS anchor_url,
                snippet(sections, 4, '[', ']', ' … ', 12) AS snippet,
                sections.text AS text,
                pages.lastmod AS lastmod,
                pages.published AS published,
                pages.synced_at AS synced_at
            FROM sections
            JOIN pages ON pages.url = sections.url
            WHERE sections MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (match, limit),
        ).fetchall()
        if rows:
            break
    return [
        Hit(
            rank=row["rank"],
            title=row["title"],
            heading_path=row["heading_path"],
            anchor_url=row["anchor_url"],
            snippet=row["snippet"],
            text=row["text"],
            rowid=row["rowid"],
            lastmod=row["lastmod"],
            published=row["published"],
            synced_at=row["synced_at"],
        )
        for row in rows
    ]


# --- semantic + hybrid retrieval (optional layer; see embed.py) ----------

# How much text to show for hits that didn't come through FTS (which would
# otherwise generate the snippet for us).
_SNIPPET_WORDS = 30

# Standard RRF constant. Each list contributes 1/(K + position); K=60 keeps
# the curve flat enough that appearing in BOTH lists outweighs being #1 in
# just one — exactly the agreement signal we want from two noisy rankers.
RRF_K = 60
# How deep each ranker's candidate list goes before fusing. Deeper than the
# final limit so a result that is mediocre in both lists can still win.
HYBRID_CANDIDATES = 30


def _make_snippet(text: str, words: int = _SNIPPET_WORDS) -> str:
    parts = text.split()
    if len(parts) <= words:
        return text
    return " ".join(parts[:words]) + " …"


def _embed_input(heading_path: str, text: str) -> str:
    # Embed the heading path WITH the body: "Shopify Integration > Order
    # Sync" carries meaning a bare paragraph loses.
    return f"{heading_path}\n{text}"


def embed_missing(
    conn: sqlite3.Connection,
    force: bool = False,
    progress=lambda msg: None,
    embed_fn=None,
    batch_size: int = 256,
) -> int:
    """Embed every section that doesn't have a vector yet. Returns the count.

    Separate from sync on purpose: it backfills an existing kb.db without a
    re-crawl, and sync calls it at the end so both paths share one code path.
    `embed_fn` is injectable so tests never download the real model.
    """
    from . import embed as embed_mod  # pack() is stdlib-only, always safe

    init_schema(conn)
    if embed_fn is None:
        stored = _embedding_model(conn)
        if stored and stored != embed_mod.MODEL_NAME and not force:
            raise RuntimeError(
                f"index was embedded with {stored!r} but the current model is "
                f"{embed_mod.MODEL_NAME!r}; run `orderdesk-kb embed --force` "
                "to re-embed everything in one space"
            )
        embed_fn = embed_mod.embed_texts
        model_name = embed_mod.MODEL_NAME
    else:
        model_name = "injected"

    if force:
        conn.execute("DELETE FROM embeddings")
    rows = conn.execute(
        """
        SELECT s.rowid AS rowid, s.url AS url,
               s.heading_path AS heading_path, s.text AS text
        FROM sections s
        LEFT JOIN embeddings e ON e.section_id = s.rowid
        WHERE e.section_id IS NULL
        """
    ).fetchall()
    if not rows:
        return 0

    progress(f"embedding {len(rows)} sections …")
    for start in range(0, len(rows), batch_size):
        batch = rows[start : start + batch_size]
        vectors = embed_fn(
            [_embed_input(r["heading_path"], r["text"]) for r in batch]
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO embeddings (section_id, url, vector)
            VALUES (?, ?, ?)
            """,
            [
                (row["rowid"], row["url"], embed_mod.pack(vec))
                for row, vec in zip(batch, vectors)
            ],
        )
        progress(f"  embedded {min(start + batch_size, len(rows))}/{len(rows)}")
    conn.execute(
        "INSERT OR REPLACE INTO embedding_meta (key, value) VALUES ('model', ?)",
        (model_name,),
    )
    conn.commit()
    return len(rows)


def semantic_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 8,
    embed_fn=None,
) -> list[Hit]:
    """Nearest-vector search by cosine similarity (higher = closer meaning).

    Brute-force over the whole corpus on purpose: ~6k unit vectors is one
    small matrix multiply, so an ANN index would be complexity without payoff.
    """
    from . import embed as embed_mod

    if not embeddings_ready(conn):
        raise RuntimeError(
            "the index has no embeddings yet; run `orderdesk-kb embed` first"
        )
    # Never compare a query vector from one model against stored vectors from
    # another — same dims gives silently wrong rankings, different dims crashes
    # the matmul. Only enforce for the real embedder (injected ones in tests
    # store model "injected"); the query embedder there is the same fake fn.
    if embed_fn is None:
        stored = _embedding_model(conn)
        if stored and stored != embed_mod.MODEL_NAME:
            raise RuntimeError(
                f"index was embedded with {stored!r} but the current model is "
                f"{embed_mod.MODEL_NAME!r}; run `orderdesk-kb embed --force`"
            )
        embed_fn = embed_mod.embed_texts
    query_vec = embed_fn([query])[0]
    rows = conn.execute("SELECT section_id, vector FROM embeddings").fetchall()
    top = embed_mod.top_k(
        query_vec, [(r["section_id"], r["vector"]) for r in rows], limit
    )

    hits: list[Hit] = []
    for section_id, similarity in top:
        row = conn.execute(
            """
            SELECT
                sections.title AS title,
                sections.heading_path AS heading_path,
                sections.anchor_url AS anchor_url,
                sections.text AS text,
                pages.lastmod AS lastmod,
                pages.published AS published,
                pages.synced_at AS synced_at
            FROM sections
            JOIN pages ON pages.url = sections.url
            WHERE sections.rowid = ?
            """,
            (section_id,),
        ).fetchone()
        if row is None:  # orphan vector; shouldn't happen, never crash on it
            continue
        hits.append(
            Hit(
                rank=-similarity,  # negate so lower-is-better holds
                title=row["title"],
                heading_path=row["heading_path"],
                anchor_url=row["anchor_url"],
                snippet=_make_snippet(row["text"]),
                text=row["text"],
                similarity=similarity,
                rowid=section_id,
                lastmod=row["lastmod"],
                published=row["published"],
                synced_at=row["synced_at"],
            )
        )
    return hits


def _cosines_for(
    conn: sqlite3.Connection, query_vec: list[float], rowids: list[int]
) -> dict[int, float]:
    """Real cosine for specific section rowids (e.g. lexical-only hits).

    Lexical candidates may sit outside semantic's top-K, so they'd otherwise
    carry no similarity. Confidence labeling needs a real cosine on EVERY
    surfaced hit, not a 0.0 sentinel — so we look their vectors up directly.
    """
    from . import embed as embed_mod

    if not rowids:
        return {}
    # SQLite caps bound variables at 999. Callers here pass at most
    # HYBRID_CANDIDATES rowids, but `candidates` is a public param — guard so a
    # large value degrades (some hits miss a cosine) instead of raising.
    rowids = rowids[:999]
    placeholders = ",".join("?" for _ in rowids)
    rows = conn.execute(
        f"SELECT section_id, vector FROM embeddings WHERE section_id IN ({placeholders})",
        rowids,
    ).fetchall()
    return {
        r["section_id"]: sum(
            a * b for a, b in zip(embed_mod.unpack(r["vector"]), query_vec)
        )
        for r in rows
    }


def hybrid_search(
    conn: sqlite3.Connection,
    query: str,
    limit: int = 8,
    candidates: int = HYBRID_CANDIDATES,
    embed_fn=None,
) -> list[Hit]:
    """Fuse lexical and semantic rankings with Reciprocal Rank Fusion.

    RRF works on POSITIONS, not scores, which sidesteps the unit mismatch
    (BM25 magnitudes and cosines aren't comparable): each list votes
    1/(RRF_K + position) for its candidates, and sections that both rankers
    like float to the top.

    Two correctness details the naive version got wrong:
      * Ties break toward HIGHER COSINE, not toward lexical. When the rankers
        disagree on #1 and each surfaces a doc the other lacks, both score
        1/(K+1); letting lexical win there throws away exactly the semantic
        signal this mode exists to add ("link my online shop" → Shopify, not
        the doc that literally contains "shop").
      * EVERY returned hit carries its real cosine (looked up for lexical-only
        hits), so confidence labeling sees a true similarity instead of a 0.0
        sentinel that would silently fall back to BM25-tuned thresholds.
    """
    from . import embed as embed_mod

    if embed_fn is None:
        embed_fn = embed_mod.embed_texts
    query_vec = embed_fn([query])[0]

    lexical = search(conn, query, limit=candidates)
    semantic = semantic_search(conn, query, limit=candidates, embed_fn=embed_fn)

    fused: dict[int, float] = {}
    by_id: dict[int, Hit] = {}
    similarity_by_id = {h.rowid: h.similarity for h in semantic}
    # Backfill cosines for lexical hits the semantic top-K didn't include.
    missing = [h.rowid for h in lexical if h.rowid not in similarity_by_id]
    similarity_by_id.update(_cosines_for(conn, query_vec, missing))

    for ranking in (lexical, semantic):
        for position, hit in enumerate(ranking):
            fused[hit.rowid] = fused.get(hit.rowid, 0.0) + 1.0 / (
                RRF_K + position + 1
            )
            # Prefer the lexical Hit object when present — its FTS snippet
            # highlights the matched terms, which the semantic one can't.
            if hit.rowid not in by_id or ranking is lexical:
                by_id[hit.rowid] = hit

    # Sort by fused score, breaking ties on cosine so semantic wins genuine
    # disagreements. -similarity as the secondary key keeps lower-is-better.
    ranked_ids = sorted(
        fused,
        key=lambda rid: (-fused[rid], -similarity_by_id.get(rid, 0.0)),
    )[:limit]
    return [
        replace(
            by_id[rid],
            rank=-fused[rid],
            similarity=similarity_by_id.get(rid, 0.0),
        )
        for rid in ranked_ids
    ]
