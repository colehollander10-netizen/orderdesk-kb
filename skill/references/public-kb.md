# Public Order Desk KB

Use the canonical helper at ../scripts/public_kb.py. It reads each dynamic
query as one JSON string from stdin and invokes the KB CLI with an argv array;
never put a query in the shell command itself.

## Check health when freshness matters

Run:

    python3 /Users/colehollander/Developer/orderdesk-kb/skill/scripts/public_kb.py health

The health result reports index counts, file modification time, and the newest
and oldest page-fetch timestamps. Those timestamps do not prove that every live
page is unchanged.

For every multi-source brief, retain a `Public KB freshness` entry. When the KB
is used, record when health was checked and the newest and oldest page-fetch
timestamps. When it is not used, record `not checked`. Never omit the entry or
treat a fetch timestamp as proof of current live product behavior.

For pricing, plan eligibility, current integration availability, APIs, recent
UI steps, or any claim using “currently,” inspect health first. If the cache is
too old to support the claim, say “documented in the cached public guide as of
<date>” and ask before checking live official docs. Do not present cache age as
product freshness.

## Run a query safely

Start one static command:

    python3 /Users/colehollander/Developer/orderdesk-kb/skill/scripts/public_kb.py ask
    python3 /Users/colehollander/Developer/orderdesk-kb/skill/scripts/public_kb.py search --limit 8
    python3 /Users/colehollander/Developer/orderdesk-kb/skill/scripts/public_kb.py triage --limit 6

Then send exactly one JSON string plus a newline to stdin. Use:

- ask for one well-specified product question;
- search for comparisons, broad research, weak results, or absence claims;
- triage for a sufficiently specified, non-identifying support problem.

Never pass private ticket text or customer details. Apply the intake gate in
[product-diagnostics.md](product-diagnostics.md) before troubleshooting.

## Interpret results

Confidence measures retrieval relevance only.

- high: inspect the passage and its product/workflow match before using it.
- medium or low: read the top 3-5 relevant hits and synthesize; lexical
  fallback can return medium.
- none: say the public KB did not surface coverage, then ask one focused
  question or offer a live official-doc check.

Semantic/hybrid results use high at cosine similarity >= 0.66; lexical fallback
can return high, medium, low, or none. Reject a tangential hit regardless of
its label.

For native-integration questions, search exact names and variants, then verify
each workflow direction. If no exact guide appears, say “I did not find a
documented native integration in the public KB”; ground any template, CSV, API,
middleware, or vendor-link alternative in its own source.

Always include deep-link source URLs. Keep retrieval metadata out of
customer-facing copy.

## Current JSON contracts

- search: mode and hits with title, heading_path, url, snippet, score, and
  similarity.
- successful ask: answer, section, confidence, mode, similarity, and sources;
  no-hit output can omit section and similarity.
- triage: question, confidence, mode, recommended_next_step, boundary, and
  sources. Each source includes `source_dates` with `published_at`,
  `modified_at`, and `fetched_at`; missing metadata is `null`. The top-level
  `freshness_note` explains that `fetched_at` is cache acquisition, not proof
  that the live page is unchanged.

Run scripts/contract_smoke.py when these shapes or commands appear to drift.

## Maintain cautiously

- Search more carefully before considering a crawl.
- When the index is missing or unusable, get the current user's acceptance before one
  locked low-rate sync --limit 25, unless he explicitly requested syncing.
- Confirm before an uncapped refresh. Keep one worker, the two-second global
  delay, and the process lock.
- Never parallelize/background a crawl, use --force, raise workers, or lower
  delay without explicit approval.
- Report lexical degradation when embeddings are absent. Do not install
  dependencies or rebuild vectors unless the current user asks for maintenance work.

The KB contains public help.orderdesk.com pages only—not tickets, Slack,
customer/order/store data, code, logs, or internal docs.
