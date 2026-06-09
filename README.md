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
3. **`search` / `ask`** query that local index — pure lexical retrieval, no LLM,
   so it runs anywhere with zero keys and zero network.

`sync` is **incremental**: it stores each page's sitemap `lastmod` and skips
unchanged pages on re-run, so monthly refreshes only fetch what actually
changed.

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

## Usage

```bash
orderdesk-kb sync                 # build / refresh the index (incremental)
orderdesk-kb sync --force         # re-fetch every page
orderdesk-kb sync --limit 12      # quick partial sync (testing)

orderdesk-kb search "twig custom fields"      # ranked list of passages
orderdesk-kb ask "how do I connect Shopify"   # single best answer + confidence

orderdesk-kb stats                # index size
orderdesk-kb --json search "..."  # machine-readable output (any command)
```

### Confidence labels (`ask`)

`high` / `medium` / `low` reflect how clearly the top result separates from the
runner-up — not certainty about correctness. Because this is **lexical** search,
short queries made of common words (e.g. "what is order desk") legitimately read
`low` even when the answer is right: every word in them appears across the whole
corpus, so the match can't be confident. That's honest, not a bug.

### `--json` mode

Every command accepts `--json` for structured output. This is deliberate: a
future `/orderdesk` agent skill can wrap this CLI instead of reimplementing
retrieval.

## Scope & boundaries

- **Public docs only.** Indexes `help.orderdesk.com`. Never touches internal or
  customer data.
- **No LLM, no API key.** Retrieval is local BM25. This keeps it shareable and
  offline; the tradeoff is no semantic understanding (it matches words, not
  meaning).
- **`kb.db` is generated** — it's gitignored. Rebuild it with `sync`.
