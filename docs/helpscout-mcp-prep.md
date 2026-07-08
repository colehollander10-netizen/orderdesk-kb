# Prep: Help Scout MCP → Order Desk skill

Goal: when Cole is on a Help Scout ticket, the `/orderdesk` skill can pull
**read-only** ticket context, look up public Order Desk docs, and return a
**context brief in chat** — never a Help Scout draft or send.

## What already exists

| Piece | Role |
|-------|------|
| `orderdesk-kb` CLI | Local FTS5 (+ optional embeddings) over `help.orderdesk.com` |
| `skill/SKILL.md` | Agent skill: query CLI, synthesize answers with source URLs |
| Help Scout MCP (custom / local) | Ticket/customer/thread access — **not in this repo** |

The skill owns product knowledge. Help Scout MCP owns mailbox context. They
meet only in the agent: ticket → question → KB → chat brief.

## Non-goals (locked)

- No `createReply` / draft replies written into Help Scout
- No notes, status changes, tags, or new conversations from this skill
- No Docs write tools
- No customer PII stored in `kb.db` or this repo

## MCP readiness checklist

Do these on the machine where Cursor runs (Cole’s laptop), not in this repo:

1. **Help Scout private app**
   - My Apps → Create Private App
   - Scopes: **Read** on Mailboxes, Conversations, Customers (and Organizations
     if useful)
   - Prefer **no write scopes** for this workflow. If the app already has write
     scopes, keep MCP write paths disabled (below).

2. **Install / point Cursor at the custom MCP**
   - Add a `helpscout` (or similar) entry in Cursor MCP config
     (e.g. `~/.cursor/mcp.json` or project `.cursor/mcp.json`)
   - Prefer a local build of the custom server over a random public package if
     Order Desk has fork-specific tools or allowlists
   - Credentials via env / Keychain launcher — **never commit** App ID/Secret

3. **Fail-closed writes (required)**
   - Leave write allowlists **unset** so write tools error if called
     (e.g. `HELPSCOUT_WRITE_INBOX_ALLOWLIST` unset on hardened forks)
   - Do **not** set `HELPSCOUT_ALLOW_SEND_REPLY=true`
   - Optional: hide Docs tools if unused (`HELPSCOUT_DISABLE_DOCS=true`)

4. **Smoke-test read tools only**
   - List/search a known conversation
   - Fetch summary + threads
   - Confirm write tools are absent or reject when invoked
   - Confirm the agent can see the MCP tools in Cursor

5. **Wire the skill**
   - Skill lives at `skill/SKILL.md` in this repo; install/symlink into Cursor
     skills as Cole already does for `/orderdesk`
   - Skill text already forbids Help Scout writes and defines the context-only
     brief format

## Intended agent flow

```text
Help Scout ticket (ID / # / email / paste)
        │
        ▼
Help Scout MCP  ──read──►  summary / threads / customer
        │
        ▼
Extract Order Desk product question
        │
        ▼
orderdesk-kb ask|search  ──►  passages + deep links
        │
        ▼
Chat reply: context brief for Cole
        ✗  never createReply / draft / note / update
```

### Context brief shape (chat only)

1. Customer ask (1–2 sentences)
2. Order Desk answer / steps from KB
3. Source URL(s)
4. Optional: what to verify in OD UI / store (not in public docs)

## Skill vs MCP responsibility

| Concern | Owner |
|---------|--------|
| “How does Shopify sync work?” | `orderdesk-kb` via skill |
| “What did this customer write in #42839?” | Help Scout MCP (read) |
| “Draft a reply into the ticket” | **Out of scope** — Cole writes it |
| Stale / missing help docs | `orderdesk-kb sync` / `embed` |

## Suggested MCP tool allowlist (read)

Exact names depend on the custom server. Prefer only:

- Conversation search / filter / get / summary / threads
- Customer / organization lookup (as needed)
- Inbox list (if needed for scoping)
- Server time (for relative date queries)

Block or never invoke:

- `createReply`, `createNote`, `createConversation`, `updateConversation`
- Docs create/update/delete
- Attachment download unless Cole explicitly needs a file for the question

## Open items (when custom MCP is ready)

- [ ] Confirm final MCP server name + tool names in Cursor
- [ ] Confirm mailbox / inbox IDs for Order Desk support
- [ ] Decide whether ticket numbers in chat should auto-trigger Help Scout
      lookup, or only when Cole mentions Help Scout / pastes a link
- [ ] Optional: add a one-line “Help Scout MCP connected?” check to skill
      maintenance section once the server name is stable
- [ ] Optional later: separate “reply coach” skill that still only outputs
      chat text — keep write tools off forever for `/orderdesk`

## Security notes

- Public KB only in this repo; ticket content stays in Help Scout + chat
- Redact message bodies in MCP (`REDACT_MESSAGE_CONTENT`) only if debugging
  without needing body text — default off for real support context
- Do not log App Secret; do not put credentials in skill markdown
