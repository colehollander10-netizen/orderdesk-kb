"""orderdesk-kb — offline search over the public Order Desk knowledge base.

Commands:
  sync     crawl the public KB into the local index (incremental)
  search   ranked passages for a query (list of hits)
  ask      single best answer for a question, with a confidence label
  stats    show index size

Every command supports --json so a future `/orderdesk` agent skill can wrap
this CLI instead of reimplementing retrieval. No network at query time, no API
key: search runs entirely against the local kb.db.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import index as index_mod
from .index import DEFAULT_DB_PATH, Hit
from .sync import sync as run_sync

# Confidence is derived from RELATIVE separation, not absolute BM25 score.
# Absolute BM25 magnitude isn't comparable across queries (it scales with query
# length and term rarity), so a fixed score threshold mislabels — a query of
# common words like "order desk" scores weak everywhere even on the right page,
# while a rare-term query scores strong on a thin match. The query-invariant
# signal is how far the top hit separates from the runner-up.
#
# The bar we actually hold: never label junk "high"; never rank junk above the
# right answer. Coarse on purpose.
CONFIDENCE_HIGH_SEPARATION = 0.30   # #1 leads #2 by ≥30% of the top score
CONFIDENCE_MEDIUM_SEPARATION = 0.08


def _db_path(args) -> Path:
    return Path(args.db) if args.db else DEFAULT_DB_PATH


def _confidence(hits: list[Hit]) -> str:
    """High/medium/low from the relative gap between the top two hits.

    SQLite BM25 is negative ("more negative is better"), so we work in
    magnitudes: |best| is the top strength, and separation is how much it leads
    the runner-up as a fraction of that strength.
    """
    if not hits:
        return "none"
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


def cmd_sync(args) -> int:
    conn = index_mod.connect(_db_path(args))
    progress = (lambda m: None) if args.json else (lambda m: print(m, file=sys.stderr))
    result = run_sync(conn, force=args.force, limit=args.limit, progress=progress)
    payload = {
        "fetched": result.fetched,
        "skipped": result.skipped,
        "empty": result.empty,
        "failed": result.failed,
        "errors": result.errors,
        **index_mod.stats(conn),
    }
    conn.close()
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
    hits = index_mod.search(conn, args.query, limit=args.limit)
    conn.close()
    if args.json:
        print(json.dumps(
            [
                {
                    "title": h.title,
                    "heading_path": h.heading_path,
                    "url": h.anchor_url,
                    "snippet": h.snippet,
                    "score": h.rank,
                }
                for h in hits
            ],
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
    hits = index_mod.search(conn, args.question, limit=5)
    conn.close()
    # Defensive: never answer from an empty-body hit even if one slips through
    # indexing. Keep ranking order, just prefer the first hit with real content.
    hits = [h for h in hits if h.text.strip()] or hits
    confidence = _confidence(hits)
    if not hits:
        if args.json:
            print(json.dumps({"answer": None, "confidence": "none", "sources": []}))
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
            "sources": sources,
        }, indent=2))
        return 0

    print(f"[confidence: {confidence}]  {best.heading_path}\n")
    print(best.text.strip())
    print("\nSources:")
    for s in sources:
        print(f"  - {s['title']}: {s['url']}")
    return 0


def cmd_stats(args) -> int:
    conn = index_mod.connect(_db_path(args))
    index_mod.init_schema(conn)
    s = index_mod.stats(conn)
    conn.close()
    print(json.dumps(s, indent=2) if args.json else f"{s['pages']} pages, {s['sections']} sections")
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
    p_sync.set_defaults(func=cmd_sync)

    p_search = sub.add_parser("search", help="ranked passages for a query")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=8)
    p_search.set_defaults(func=cmd_search)

    p_ask = sub.add_parser("ask", help="single best answer with a confidence label")
    p_ask.add_argument("question")
    p_ask.set_defaults(func=cmd_ask)

    p_stats = sub.add_parser("stats", help="show index size")
    p_stats.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
