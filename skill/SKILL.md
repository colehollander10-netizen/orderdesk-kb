---
name: orderdesk
description: Answer questions about Order Desk (integrations, rules, templates, folders, inventory, the app itself) using the local orderdesk-kb CLI — offline search over the public Order Desk help docs. Use whenever Cole asks how something works in Order Desk or needs a help-doc reference for support/internship work. Also use when a Help Scout ticket needs Order Desk product context — pull ticket context read-only, then look up docs; never draft or send replies.
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

## Help Scout ticket context (read-only)

When Cole is working a Help Scout conversation (ticket number, conversation
ID, customer email, or pasted thread), use the Help Scout MCP **only** to
gather context, then answer with Order Desk KB findings.

### Workflow

1. **Read the ticket** via Help Scout MCP (whichever read tools are available),
   e.g. conversation lookup / summary / threads / customer search. Prefer the
   smallest call that answers: summary first, full threads only if needed.
2. **Extract the Order Desk question** from the customer message (product
   behavior, integration setup, rules, templates, folders, inventory, etc.).
3. **Query orderdesk-kb** with that question (`ask`, then `search` if low
   confidence).
4. **Reply in chat with context only** — a short brief Cole can use:
   - What the customer is asking (1–2 sentences)
   - Relevant Order Desk facts / steps from the KB
   - Source deep-link URL(s)
   - Optional: gaps / what to verify in the store or Order Desk UI

### Hard rule: never write to Help Scout

This skill is **context-only**. It must **not** create, update, or send
anything in Help Scout.

**Do not call** (or ask Cole to call) any write tools, including:

- `createReply` / draft reply / send reply
- `createNote`
- `createConversation`
- `updateConversation`
- Docs create/update/delete tools
- Any tool that posts a draft into the conversation

If Cole asks for a draft reply, still **do not** write it into Help Scout.
Give the context brief in chat only; Cole pastes or writes the reply himself.

If the Help Scout MCP is missing or auth fails, say so and continue with
orderdesk-kb from whatever ticket text Cole pasted.

## Maintenance (only when relevant)

- Index missing or stale (`no such table`, empty results everywhere, or docs
  changed): run `sync` (incremental, ~minutes, polite crawl):
  `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb sync`
- `mode` in output says `lexical` even though Cole expects semantic: the
  semantic extra or vectors are missing — `pip install -e ".[semantic]"` in the
  repo, then `orderdesk-kb embed`.
- Check index health: `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb stats`

## Boundaries

- This KB indexes only the **public** help docs. It has no Slack, tickets, or
  customer data by itself — Help Scout MCP is the only ticket source, and only
  for read context.
- Never imply the KB knows a specific customer's store, orders, or account.
- Never draft or send Help Scout replies from this skill.
