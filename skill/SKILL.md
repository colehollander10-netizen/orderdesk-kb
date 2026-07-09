---
name: orderdesk
description: "Answer Order Desk product/support questions with the local orderdesk-kb CLI and, when explicitly working on support context, use read-only Help Scout tools to surface similar tickets plus public KB links. Use for Order Desk integrations, rules, templates, folders, inventory, support-ticket research, similar-ticket recall, Help Scout + KB briefs, and the Order Desk support-agent beta."
---

# Order Desk support context

Use this skill as the `/orderdesk` workbench. It has two modes:

1. Public-doc lookup from `~/Developer/orderdesk-kb`.
2. Support-context research from read-only Help Scout plus the public KB.

Default to cached/local sources. Never web-search Order Desk help-doc content
before trying the local KB first.

## Guardrails

- Keep Help Scout read-only. Do not send replies, draft customer-facing text,
  tag, assign, close, edit, publish docs, run workflows, download attachments,
  or perform writes.
- Do not create Help Scout drafts, saved replies, notes, draft replies, or any
  customer-visible/helpdesk artifact. If Cole later asks for customer copy, put
  it in chat only.
- In Help Scout/support-context mode, do not write draft responses, sample
  replies, or customer-facing copy. If Cole asks "what should I say?" in the
  same request as ticket research, give an internal brief plus response
  structure/questions only. Write pasteable customer copy only after Cole
  explicitly asks for a customer-facing reply as a separate follow-up.
- Do not fetch real ticket content unless Cole has explicitly asked for a
  Help Scout/ticket-context task in the current conversation or a named Order
  Desk reviewer has approved the beta/test boundary.
- Treat masking as a **pre-model boundary**, not a final-answer cleanup step.
  Raw Help Scout/API data may exist inside the local bridge, but the LLM should
  only receive sanitized, minimized snippets after the bridge's masking layer
  has run.
- Use the Help Scout MCP tools or local bridge CLI for ticket content. Do not
  bypass the bridge with raw API calls, browser copy/paste, or unmasked ticket
  dumps into the chat.
- Minimize private content in model-visible outputs. Avoid names, emails, order
  IDs, store URLs, API keys, credentials, payment data, and raw customer text
  unless the bridge has already masked them into placeholders.
- Treat ticket history as evidence, not truth. Older repeated tickets do not
  override newer tickets, current public docs, or explicitly approved current
  internal sources.
- Follow evidence-or-silence: every claim in an internal brief needs a source,
  or say "not found."
- Slack, codebase, logs, order/store data, and internal docs are out of scope
  for this v0 skill unless Cole explicitly opens that source and the access
  boundary has been approved.

## Public KB lookup

For ordinary Order Desk questions, run:

```bash
/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb --json ask "<question>"
```

For broader research, comparing options, or low-confidence answers, run:

```bash
/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb --json search "<query>" --limit 8
```

For sanitized support-style research, run `triage`:

```bash
/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb --json triage "<sanitized support question>"
```

Never pass private ticket text or customer details into `orderdesk-kb`; it is
for public-doc retrieval only.

### Interpreting KB results

Confidence is **high / low / none** (no "medium"; for this embedding model a
mid score is noise, not partial confidence, so it's folded into low).

- `confidence: high` — the top hit is a real semantic match (cosine ≥ 0.66).
  Quote/summarize the answer directly and cite the source URL.
- `confidence: low` — weak or tangential match. Do NOT quote hit #1 blindly:
  run `search`, read the top 3–5 hits, and synthesize across them. If none are
  actually on-topic, say the KB doesn't seem to cover it.
- `confidence: none` / no hits — say the KB doesn't cover it. Offer to check
  https://help.orderdesk.com live (Firecrawl) only if Cole wants.
- Always include the deep-link `url` of the source(s) in the reply.

`search --json` returns `{"mode": ..., "hits": [...]}`; each hit has `title`,
`heading_path`, `url`, `snippet`, `score`, and `similarity`. `ask --json`
returns `{"answer", "section", "confidence", "mode", "similarity", "sources"}`.

## Help Scout tools

Prefer MCP tools when available:

- `helpscout_status`
- `helpscout_list_mailboxes`
- `helpscout_search_conversations`
- `helpscout_get_threads`
- `helpscout_list_saved_replies`

If MCP tools are unavailable, use the local read-only CLI:

```bash
/Users/colehollander/Developer/help-scout-mcp/bin/help-scout-mcp.js doctor
/Users/colehollander/Developer/help-scout-mcp/bin/help-scout-mcp.js mailboxes
/Users/colehollander/Developer/help-scout-mcp/bin/help-scout-mcp.js search --query '<query>' --status all --limit 5
/Users/colehollander/Developer/help-scout-mcp/bin/help-scout-mcp.js threads --conversation-id <id> --limit 25
```

The Help Scout bridge masks and compacts content before returning it to the
LLM. A final outbound sanitizer also runs at the MCP/CLI serialization boundary
so future raw fields are masked before they become model-visible. If that final
gate returns `masking_failed`, stop and report the masking blocker instead of
trying to recover the raw payload.

### Model-visible Help Scout contract

Help Scout output visible to the LLM must be bridge-produced, masked, and
minimized. Accept only sanitized fields such as ticket id/number/link, source
type, status, date, mailbox/team if present, masked snippet/summary, matching
reason, masking status, and redaction notes.

Stop before analysis if a Help Scout result exposes raw customer text, customer
names, emails, phone numbers, order IDs, store domains/URLs, credentials,
payment data, tokens, or any absent/failed masking status. Report the masking
blocker; do not summarize, quote, transform, or manually redact the payload.

## Support-context workflow

Use this flow when Cole asks for a ticket brief, similar-ticket recall, Help
Scout + KB research, or support-agent beta work.

### Real-ticket preflight

Before reading a real Help Scout ticket, confirm:

- Cole explicitly requested a Help Scout/ticket-context task in this
  conversation, or a named Order Desk reviewer approved this exact beta/test.
- The bridge is read-only and reachable (`helpscout_status` or `doctor`).
- The result shape includes masking status/metadata. If it is absent, stop.
- Search terms are masked exact error phrases, public integration/provider
  names, endpoint names, template/rule/folder terms, or redacted workflow
  phrases. Do not search on raw customer text.
- The user prompt, shell command, and final answer contain no raw private
  customer/internal data.

### Research steps

1. Classify the request.
   - Public product/docs question: use KB `ask` or `search`.
   - Sanitized ticket/workflow question: use KB `triage`.
   - Approved Help Scout context: use Help Scout search/read plus KB.
2. Extract search keys.
   - Prioritize masked exact error phrases, public integration names, provider
     names, endpoint names, template/rule/folder terms, and redacted workflow
     phrases.
   - Try more than one search query before saying no similar ticket exists.
3. Search Help Scout.
   - Use at most 3 Help Scout search queries for v0.
   - Start narrow with `status: "closed"` or `status: "all"`, `limit: 5`,
     `sortField: "modifiedAt"`, `sortOrder: "desc"`.
   - Broaden only if the first query misses. Prefer focused terms over dumping
     whole ticket text into search.
   - Fetch threads only for selected candidate conversations, not every result.
     Fetch at most 3 candidate conversations for v0.
4. Search the KB.
   - Run `triage` on a sanitized description.
   - Run `search` for specific integrations, settings, or public-doc links that
     could be useful to Cole. Include at most 5 KB links in the brief.
5. Apply freshness and authority.
   - Show source type and date for every material source.
   - Prefer current public docs, then explicitly approved current internal
     sources, then newer sanitized tickets, then older sanitized tickets.
   - Label every similar ticket `current` (0-90 days old), `recent` (91-365
     days old), `stale` (over 365 days old), or `unknown date`.
   - For every similar ticket, note product area, integration/provider, and
     whether it conflicts with current public docs.
   - Do not majority-vote stale history. If four old tickets say one thing and
     one newer/current source says another, flag the conflict and treat the old
     answer as potentially stale.
   - Do not make older tickets the likely pattern unless current public KB or
     an explicitly approved current source supports the same answer.
6. Produce an internal brief, not a customer reply. No suggested customer
   wording, no sample reply, and no draft response section.

## Internal brief format

Use this shape by default:

```markdown
**Support Context Brief**

**What I Checked**
- Preflight: <approval boundary, read-only bridge, masking status>
- Help Scout: <queries, statuses, result count, ticket dates, caps used>
- Public KB: <queries and source links>

**Likely Pattern**
<one short sourced synthesis, or "not found"; do not rely on stale tickets
unless current KB/current approved evidence supports them>

**Similar Tickets**
- <ticket number/id/link> — <date/status/freshness label> — <product
  area/integration> — <why it matches> — <doc conflict or freshness caveat>

**Public KB Links**
- <title> — <url> — <why it matters>

**Freshness / Conflicts**
<call out stale-ticket risk, newer/current sources, or "no conflict found">

**Suggested Next Step**
<one practical support investigation step or question>

**Reply Boundary**
No customer-facing draft written. Ask Cole whether he wants pasteable copy
after he reviews the evidence.
```

If Cole asks for a customer-facing reply afterward, write clean pasteable copy
without internal metadata, ticket IDs, private notes, or gray citation blocks.

## Maintenance

- Default to cached KB only. Do not run live crawls just because a result is
  weak; use `search` first and say when the local KB does not cover something.
- Index missing or stale (`no such table`, empty results everywhere, or Cole
  explicitly asks to refresh): run one locked, low-rate sync only:
  `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb sync --limit 25`
- Full refreshes are unusual. Before running an uncapped sync, confirm it is
  needed, then use the CLI defaults (single worker, 2s global delay, process
  lock). Never start parallel syncs, background syncs, or multiple agents that
  crawl `help.orderdesk.com`.
- Do not use `--force`, raise `--workers`, or lower `--delay` unless Cole
  explicitly approves that specific live-refresh risk.
- `mode` in output says `lexical` even though Cole expects semantic: the
  semantic extra or vectors are missing; install the semantic extra in the KB
  repo, then run `orderdesk-kb embed`.
- Check index health:
  `/Users/colehollander/Developer/orderdesk-kb/bin/orderdesk-kb stats`

## Known limits

- The public KB indexes only `help.orderdesk.com`. It has no Slack, tickets,
  customer data, code, logs, or internal docs.
- Help Scout search quality is part of the beta question. If recall is weak,
  say that directly instead of padding the brief with weak matches.
- If the Help Scout connector is unavailable, surface the blocker quickly and
  fall back to public KB work only.
