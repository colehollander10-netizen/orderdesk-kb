# orderdesk-kb

Offline, full-text search over the **public** [Order Desk knowledge base](https://help.orderdesk.com).
Ask it a question, get the right help-doc passage back with a deep link — no
browser, no account, no API key.

```
$ orderdesk-kb ask "Stripe webhook setup"
[confidence: high]  Stripe Integration > Webhook Setup Instructions

Browse to your Stripe account settings and click on the webhooks tab...

Sources:
  - Stripe Integration: https://help.orderdesk.com/integration-setup-guides/payment-gateways/stripe-integration/#webhook-setup-instructions
```

## Why it exists

A lightweight lookup tool for learning and supporting Order Desk faster. It
indexes only the **public** help docs — no Slack, tickets, customer data, or
internal docs. The whole index is a single 6 MB `kb.db` file you can copy and
run offline.

## How it works

1. **`sync`** reads the WordPress/Yoast sitemap, fetches each help article,
   strips page chrome with [`defuddle`](https://github.com/kepano/defuddle),
   and chunks it into ~6,000 searchable sections (by heading where the article
   has them, by packed paragraphs where it doesn't).
2. The sections go into **SQLite FTS5**, which provides BM25 ranking.
3. Optionally, **`embed`** adds a semantic layer: each section gets a small
   local vector (model2vec static embeddings, ~30 MB model, CPU-only) stored
   right inside `kb.db`, so "connect my store" can find the Shopify page even
   though it shares no words with it.
4. **`search` / `ask`** query that local index. With embeddings present they
   run **hybrid** retrieval — BM25 and nearest-vector rankings fused with
   Reciprocal Rank Fusion — and fall back to pure lexical otherwise. Either
   way: no LLM at query time, no API key, no network.

`sync` is **incremental**: it stores each page's sitemap `lastmod` and skips
unchanged pages on re-run, so monthly refreshes only fetch what actually
changed. It also re-embeds just the refreshed pages when the semantic extra is
installed.

## Setup

Requires Python ≥ 3.10 (stdlib only) and the `defuddle` CLI:

```bash
npm install -g defuddle-cli      # provides `defuddle`
git clone <this repo> && cd orderdesk-kb
./bin/orderdesk-kb sync          # build the index (~3 min, polite crawl)
```

Or install as a package so `orderdesk-kb` is on your PATH. Use **editable**
mode (`-e`) — a plain `pip install .` would look for `kb.db` inside
site-packages, where it isn't:

```bash
pip install -e .
```

To enable semantic/hybrid search (optional — everything works without it):

```bash
pip install -e ".[semantic]"     # adds model2vec (small, CPU-only)
orderdesk-kb embed               # vectorize the index (~30 MB model, one-time download)
```

## Usage

```bash
orderdesk-kb sync                 # build / refresh the index (incremental)
orderdesk-kb sync --force         # re-fetch every page
orderdesk-kb sync --limit 12      # quick partial sync (testing)
orderdesk-kb embed                # build/refresh semantic vectors (optional)
orderdesk-kb embed --force        # re-embed everything (e.g. model change)

orderdesk-kb search "twig custom fields"      # ranked list of passages
orderdesk-kb ask "how do I connect Shopify"   # single best answer + confidence
orderdesk-kb search "..." --mode lexical      # force BM25 only
orderdesk-kb search "..." --mode semantic     # force vectors only
orderdesk-kb search "..." --mode hybrid       # force fusion (default when embedded)

orderdesk-kb stats                # index size + embedding coverage
orderdesk-kb --json search "..."  # machine-readable output (any command)
```

### Search modes

- **lexical** — SQLite FTS5 BM25. Tries all-terms-AND first for precision,
  falls back to any-term-OR so one off-corpus word never zeroes the results.
- **semantic** — cosine similarity over local embeddings; finds meaning, not
  words ("link my storefront" → the Shopify guide).
- **hybrid** *(auto default when embeddings exist)* — runs both and fuses the
  rankings with Reciprocal Rank Fusion: sections both rankers like win.

### Confidence labels (`ask`)

With embeddings, confidence comes from the top hit's **cosine similarity** —
an absolute, query-comparable signal, which fixes the old weakness where
common-word questions always read `low`. It's **high / low / none**: the
threshold (≥0.66) is calibrated against the live corpus so on-topic questions
read `high` and questions the KB can't answer (e.g. "how do I file my taxes")
read `low`. There's no `medium` band — for this small static model a mid score
is noise, not partial confidence, so labeling it would over-promise.

Lexical-only indexes (no embeddings) keep the original heuristic: high/medium/
low from how clearly the top result separates from the runner-up.

### `--json` mode

Every command accepts `--json` for structured output. This is deliberate: the
`/orderdesk` agent skill wraps this CLI instead of reimplementing retrieval.
`search --json` returns `{"mode": ..., "hits": [...]}`; `ask --json` includes
`confidence`, `mode`, `similarity`, and `sources`.

## Scope & boundaries

- **Public docs only.** Indexes `help.orderdesk.com`. Never touches internal or
  customer data.
- **No LLM, no API key.** Retrieval is local BM25 + (optionally) local static
  embeddings. Nothing leaves the machine at query time.
- **`kb.db` is generated** — it's gitignored. Rebuild it with `sync` + `embed`.

### Help Scout (agent skill only)

The `/orderdesk` skill can use a **custom Help Scout MCP** for read-only ticket
context, then answer from this KB. It must **not** draft or send Help Scout
replies — chat context only. See `docs/helpscout-mcp-prep.md` and
`skill/SKILL.md`.
