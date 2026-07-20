"""orderdesk-kb — offline search over the public Order Desk knowledge base.

Commands:
  sync     crawl the public KB into the local index (incremental, locked)
  embed    build/refresh the optional semantic vectors (see embed.py)
  search   ranked passages for a query (list of hits)
  ask      single best answer for a question, with a confidence label
  triage   support research brief with ranked public-doc sources
  stats    show index size

`search` and `ask` take --mode {auto,lexical,semantic,hybrid}. Auto picks
hybrid when the optional semantic layer is installed and embedded, and falls
back to lexical otherwise — so the zero-dependency install keeps working
unchanged.

Every command supports --json so the `/orderdesk` agent skill can wrap this
CLI instead of reimplementing retrieval. No network at query time, no API key:
search runs entirely against the local kb.db.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import sys
from contextlib import contextmanager
from pathlib import Path

from . import embed as embed_mod
from . import index as index_mod
from .index import DEFAULT_DB_PATH, Hit
from .sync import DEFAULT_MAX_WORKERS, DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS
from .sync import sync as run_sync

# Confidence, lexical path: derived from RELATIVE separation, not absolute
# BM25 score. Absolute BM25 magnitude isn't comparable across queries (it
# scales with query length and term rarity), so a fixed score threshold
# mislabels — a query of common words like "order desk" scores weak everywhere
# even on the right page, while a rare-term query scores strong on a thin
# match. The query-invariant signal is how far the top hit separates from the
# runner-up.
#
# The bar we actually hold: never label junk "high"; never rank junk above the
# right answer. Coarse on purpose.
CONFIDENCE_HIGH_SEPARATION = 0.30   # #1 leads #2 by ≥30% of the top score
CONFIDENCE_MEDIUM_SEPARATION = 0.08

# Confidence, semantic path: cosine similarity IS comparable across queries
# (it's the angle between two unit vectors, independent of query length), so
# when the top hit carries one we can use ABSOLUTE thresholds — which fixes
# the lexical path's known weakness on common-word questions.
#
# Calibrated against the live 5,800-section index (potion-base-8M), not picked
# a priori. The model's similarity floor for loosely-related text runs high:
# off-topic questions the KB can't answer ("how do I file my taxes") still
# score ~0.45-0.63 against the nearest tangential section, while genuinely
# on-topic queries floor around ~0.72. That overlap is why there's no useful
# "medium" band here — a mid score is noise, not partial confidence. So this
# is deliberately high/low only: HIGH sits just above the off-topic ceiling
# (≥0.66 → trust and quote), everything below is LOW (read several hits, don't
# quote hit #1 blindly). Better to under-claim than to confidently cite a
# tangential match.
CONFIDENCE_HIGH_SIMILARITY = 0.66

SEARCH_MODES = ("auto", "lexical", "semantic", "hybrid")


class SyncAlreadyRunning(RuntimeError):
    pass


def _db_path(args) -> Path:
    return Path(args.db) if args.db else DEFAULT_DB_PATH


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


@contextmanager
def _sync_lock(db_path: Path):
    lock_path = (
        DEFAULT_DB_PATH.with_suffix(".sync.lock")
        if str(db_path) == ":memory:"
        else Path(f"{db_path}.sync.lock")
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SyncAlreadyRunning(
                f"sync already running (lock held at {lock_path})"
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _confidence(hits: list[Hit]) -> str:
    """Confidence for the top hit; the cosine signal wins when present.

    Semantic/hybrid hits carry a real cosine (high/low, see thresholds above).
    Pure lexical hits have similarity 0.0 — those keep the original
    relative-separation heuristic.
    """
    if not hits:
        return "none"
    if hits[0].similarity > 0:
        return "high" if hits[0].similarity >= CONFIDENCE_HIGH_SIMILARITY else "low"
    return _confidence_from_separation(hits)


def _confidence_from_separation(hits: list[Hit]) -> str:
    """Lexical fallback: relative gap between the top two hits.

    SQLite BM25 is negative ("more negative is better"), so we work in
    magnitudes: |best| is the top strength, and separation is how much it leads
    the runner-up as a fraction of that strength.
    """
    best = abs(hits[0].rank)
    if best == 0:
        return "low"
    if len(hits) == 1:
        return "medium"  # a single hit can't be separated from anything
    second = abs(hits[1].rank)
    separation = (best - second) / best
    if separation >= CONFIDENCE_HIGH_SEPARATION:
        return "high"
    if separation >= CONFIDENCE_MEDIUM_SEPARATION:
        return "medium"
    return "low"


def _run_query(conn, query: str, limit: int, mode: str) -> tuple[str, list[Hit]]:
    """Resolve --mode and run the right retrieval, with safe fallbacks.

    Auto never fails: if the semantic layer errors for any reason (model not
    installed, first-run download offline, no vectors yet), it warns on stderr
    and serves lexical results. Explicit semantic/hybrid surface the error —
    if you asked for vectors by name, silently serving keywords would lie.
    """
    resolved = mode
    if mode == "auto":
        resolved = (
            "hybrid"
            if embed_mod.is_available() and index_mod.embeddings_ready(conn)
            else "lexical"
        )
    if resolved == "lexical":
        return "lexical", index_mod.search(conn, query, limit=limit)
    try:
        if resolved == "semantic":
            return "semantic", index_mod.semantic_search(conn, query, limit=limit)
        return "hybrid", index_mod.hybrid_search(conn, query, limit=limit)
    except Exception as exc:  # noqa: BLE001 — fallback only in auto mode
        if mode != "auto":
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        print(
            f"warning: semantic search unavailable ({exc}); using lexical",
            file=sys.stderr,
        )
        return "lexical", index_mod.search(conn, query, limit=limit)


def cmd_sync(args) -> int:
    db_path = _db_path(args)
    progress = (lambda m: None) if args.json else (lambda m: print(m, file=sys.stderr))
    try:
        with _sync_lock(db_path):
            conn = index_mod.connect(db_path)
            try:
                result = run_sync(
                    conn,
                    force=args.force,
                    limit=args.limit,
                    max_workers=args.workers,
                    min_interval=args.delay,
                    progress=progress,
                )
                # Keep vectors in step with the crawl automatically. If the semantic extra
                # isn't installed this is a no-op hint, never an error — sync must keep
                # working on a zero-dependency install.
                embedded = 0
                if embed_mod.is_available():
                    try:
                        embedded = index_mod.embed_missing(conn, progress=progress)
                    except RuntimeError as exc:  # model load failure OR model mismatch —
                        # either way the crawl itself succeeded; report and move on.
                        progress(f"semantic: skipped ({exc})")
                else:
                    progress(
                        "semantic: model2vec not installed; lexical-only "
                        "(pip install -e '.[semantic]' to enable)"
                    )
                payload = {
                    "fetched": result.fetched,
                    "skipped": result.skipped,
                    "empty": result.empty,
                    "failed": result.failed,
                    "errors": result.errors,
                    "embedded": embedded,
                    **index_mod.stats(conn),
                }
            finally:
                conn.close()
    except SyncAlreadyRunning as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"\nDone. indexed {payload['pages']} pages / {payload['sections']} sections "
            f"(fetched {result.fetched}, skipped {result.skipped}, "
            f"empty {result.empty}, failed {result.failed})"
        )
    return 0


def cmd_search(args) -> int:
    conn = index_mod.connect(_db_path(args))
    try:
        mode, hits = _run_query(conn, args.query, args.limit, args.mode)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(
            {
                "mode": mode,
                "hits": [
                    {
                        "title": h.title,
                        "heading_path": h.heading_path,
                        "url": h.anchor_url,
                        "snippet": h.snippet,
                        "score": h.rank,
                        "similarity": round(h.similarity, 4),
                    }
                    for h in hits
                ],
            },
            indent=2,
        ))
        return 0
    if not hits:
        print("No matches. Try fewer or different words, or run `sync` first.")
        return 0
    for i, h in enumerate(hits, 1):
        print(f"{i}. {h.heading_path}")
        print(f"   {h.snippet.strip()}")
        print(f"   {h.anchor_url}\n")
    return 0


def cmd_ask(args) -> int:
    conn = index_mod.connect(_db_path(args))
    try:
        mode, hits = _run_query(conn, args.question, 5, args.mode)
    finally:
        conn.close()
    # Defensive: never answer from an empty-body hit even if one slips through
    # indexing. Keep ranking order, just prefer the first hit with real content.
    hits = [h for h in hits if h.text.strip()] or hits
    confidence = _confidence(hits)
    if not hits:
        if args.json:
            print(json.dumps(
                {"answer": None, "confidence": "none", "mode": mode, "sources": []}
            ))
        else:
            print("I couldn't find anything in the KB for that. Try `search`.")
        return 0

    best = hits[0]
    sources = [{"title": h.title, "url": h.anchor_url} for h in hits[:3]]
    if args.json:
        print(json.dumps({
            "answer": best.text,
            "section": best.heading_path,
            "confidence": confidence,
            "mode": mode,
            "similarity": round(best.similarity, 4),
            "sources": sources,
        }, indent=2))
        return 0

    print(f"[confidence: {confidence} · {mode}]  {best.heading_path}\n")
    print(best.text.strip())
    print("\nSources:")
    for s in sources:
        print(f"  - {s['title']}: {s['url']}")
    return 0


def _source_kind(url: str) -> str:
    if "/order-desk-101/" in url:
        return "general"
    if "/integration-setup-guides/" in url:
        return "integration"
    if "/apis/" in url or "/api-" in url:
        return "api"
    return "public-doc"


def _source_payload(hit: Hit) -> dict:
    return {
        "title": hit.title,
        "section": hit.heading_path,
        "kind": _source_kind(hit.anchor_url),
        "url": hit.anchor_url,
        "snippet": hit.snippet,
        "similarity": round(hit.similarity, 4),
        "source_dates": {
            "published_at": hit.published or None,
            "modified_at": hit.lastmod or None,
            "fetched_at": hit.synced_at or None,
        },
    }


def _triage_next_step(confidence: str) -> str:
    if confidence == "high":
        return (
            "Start with the top source, but verify it matches the customer's "
            "platform and workflow before treating it as primary."
        )
    if confidence == "none":
        return (
            "The public KB did not surface coverage. Ask a follow-up question "
            "or verify outside the public docs before drafting."
        )
    return (
        "Review multiple sources before drafting; the match is not strong "
        "enough to rely on one passage."
    )


def _triage_payload(question: str, mode: str, hits: list[Hit]) -> dict:
    hits = [h for h in hits if h.text.strip()]
    confidence = _confidence(hits)
    return {
        "question": question,
        "confidence": confidence,
        "mode": mode,
        "recommended_next_step": _triage_next_step(confidence),
        "boundary": (
            "Public Order Desk docs only. Use sanitized ticket summaries; do "
            "not include customer data, secrets, credentials, or internal docs."
        ),
        "freshness_note": (
            "published_at and modified_at come from public page/sitemap metadata "
            "when available. fetched_at is the local cache acquisition time and "
            "does not prove the live page is unchanged."
        ),
        "sources": [_source_payload(h) for h in hits],
    }


def cmd_triage(args) -> int:
    conn = index_mod.connect(_db_path(args))
    try:
        mode, hits = _run_query(conn, args.question, args.limit, args.mode)
    finally:
        conn.close()
    payload = _triage_payload(args.question, mode, hits)
    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"Support research brief [{payload['confidence']} · {payload['mode']}]\n")
    print(f"Question: {payload['question']}\n")
    print(f"Next: {payload['recommended_next_step']}\n")
    if not payload["sources"]:
        print("Sources: none")
        return 0
    print("Sources:")
    for i, source in enumerate(payload["sources"], 1):
        print(f"{i}. [{source['kind']}] {source['section']}")
        print(f"   {source['snippet'].strip()}")
        dates = source["source_dates"]
        print(
            "   Dates: "
            f"published {dates['published_at'] or 'unknown'} · "
            f"modified {dates['modified_at'] or 'unknown'} · "
            f"fetched {dates['fetched_at'] or 'unknown'}"
        )
        print(f"   {source['url']}\n")
    print(f"Freshness: {payload['freshness_note']}\n")
    print(f"Boundary: {payload['boundary']}")
    return 0


def cmd_embed(args) -> int:
    conn = index_mod.connect(_db_path(args))
    if not embed_mod.is_available():
        print(
            "error: model2vec is not installed — run: pip install -e '.[semantic]'",
            file=sys.stderr,
        )
        conn.close()
        return 2
    progress = (lambda m: None) if args.json else (lambda m: print(m, file=sys.stderr))
    try:
        embedded = index_mod.embed_missing(conn, force=args.force, progress=progress)
    except (RuntimeError, embed_mod.EmbedderUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        conn.close()
        return 2
    # stats() also reports "embedded" (TOTAL vectors); keep the run count
    # under its own key so the two never shadow each other.
    payload = {"newly_embedded": embedded, **index_mod.stats(conn)}
    conn.close()
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"embedded {embedded} new sections "
            f"({payload['embedded']}/{payload['sections']} now covered)"
        )
    return 0


def cmd_stats(args) -> int:
    conn = index_mod.connect(_db_path(args))
    index_mod.init_schema(conn)
    s = index_mod.stats(conn)
    conn.close()
    if args.json:
        print(json.dumps(s, indent=2))
    else:
        semantic = (
            f"{s['embedded']} embedded ({s['embedding_model']})"
            if s["embedded"]
            else "no embeddings (run `embed`)"
        )
        print(f"{s['pages']} pages, {s['sections']} sections, {semantic}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orderdesk-kb",
        description="Offline search over the public Order Desk knowledge base.",
    )
    parser.add_argument("--db", help="path to the index db (default: kb.db beside the package)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="crawl the public KB into the local index")
    p_sync.add_argument("--force", action="store_true", help="re-fetch even unchanged pages")
    p_sync.add_argument("--limit", type=int, help="cap pages (for quick test runs)")
    p_sync.add_argument(
        "--workers",
        type=_positive_int,
        default=DEFAULT_MAX_WORKERS,
        help=f"fetch worker count (default: {DEFAULT_MAX_WORKERS})",
    )
    p_sync.add_argument(
        "--delay",
        type=_positive_float,
        default=DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS,
        help=(
            "minimum seconds between live HTTP requests "
            f"(default: {DEFAULT_MIN_SECONDS_BETWEEN_REQUESTS})"
        ),
    )
    p_sync.set_defaults(func=cmd_sync)

    p_embed = sub.add_parser("embed", help="build/refresh semantic vectors for the index")
    p_embed.add_argument("--force", action="store_true", help="re-embed every section")
    p_embed.set_defaults(func=cmd_embed)

    p_search = sub.add_parser("search", help="ranked passages for a query")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.add_argument(
        "--mode", choices=SEARCH_MODES, default="auto",
        help="retrieval mode (auto = hybrid when embeddings exist, else lexical)",
    )
    p_search.set_defaults(func=cmd_search)

    p_ask = sub.add_parser("ask", help="single best answer with a confidence label")
    p_ask.add_argument("question")
    p_ask.add_argument(
        "--mode", choices=SEARCH_MODES, default="auto",
        help="retrieval mode (auto = hybrid when embeddings exist, else lexical)",
    )
    p_ask.set_defaults(func=cmd_ask)

    p_triage = sub.add_parser(
        "triage",
        help="support research brief with ranked public-doc sources",
    )
    p_triage.add_argument("question")
    p_triage.add_argument("--limit", type=int, default=6)
    p_triage.add_argument(
        "--mode", choices=SEARCH_MODES, default="auto",
        help="retrieval mode (auto = hybrid when embeddings exist, else lexical)",
    )
    p_triage.set_defaults(func=cmd_triage)

    p_stats = sub.add_parser("stats", help="show index size")
    p_stats.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
