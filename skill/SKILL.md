---
name: orderdesk
description: Answer questions about Order Desk (integrations, rules, templates, folders, inventory, the app itself) using the local orderdesk-kb CLI — offline search over the public Order Desk help docs. Use whenever Cole asks how something works in Order Desk or needs a help-doc reference for support/internship work.
---

# Order Desk KB lookup

Answer Order Desk questions from the local knowledge base CLI at
`~/Developer/orderdesk-kb`. Retrieval is local (SQLite FTS5 + optional
embeddings) — never web-search for Order Desk help-doc content before trying
the KB first.

## How to query

The user's text after `/orderdesk` is the question. Run:

```bash
/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb --json ask "<question>"
```

For broader research (multiple relevant passages, comparing options), use
`search` instead and read the top hits:

```bash
/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb --json search "<query>" --limit 8
```

`search --json` returns `{"mode": ..., "hits": [...]}`; each hit has `title`,
`heading_path`, `url` (deep link), `snippet`, `score`, `similarity`.
`ask --json` returns `{"answer", "section", "confidence", "mode", "similarity",
"sources"}`.

## Interpreting results

Confidence is **high / low / none** (no "medium" — for this embedding model a
mid score is noise, not partial confidence, so it's folded into low).

- `confidence: high` — the top hit is a real semantic match (cosine ≥ 0.66).
  Quote/summarize the answer directly and cite the source URL.
- `confidence: low` — weak or tangential match. Do NOT quote hit #1 blindly:
  run `search`, read the top 3–5 hits, and synthesize across them. If none are
  actually on-topic, say the KB doesn't seem to cover it.
- `confidence: none` / no hits — say the KB doesn't cover it. Offer to check
  https://help.orderdesk.com live (Firecrawl) only if Cole wants.
- Always include the deep-link `url` of the source(s) in the reply.

## Answer style

Answer the question directly first, then the source link(s). Don't dump raw
JSON or full passages unless asked — synthesize. If the passage describes UI
steps, keep them as a short numbered list.

## Maintenance (only when relevant)

- Index missing or stale (`no such table`, empty results everywhere, or docs
  changed): run `sync` (incremental, ~minutes, polite crawl):
  `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb sync`
- `mode` in output says `lexical` even though Cole expects semantic: the
  semantic extra or vectors are missing — `pip install -e ".[semantic]"` in the
  repo, then `orderdesk-kb embed`.
- Check index health: `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb stats`

## Boundaries

This KB indexes only the **public** help docs. It has no Slack, tickets, or
customer data — never imply otherwise in answers.
