# Read-only Help Scout research

Read this file before a real Help Scout query.

## Require current authority

A current request containing one positive real Help Scout ticket number, or `/orderdesk` with that number, authorizes one task-scoped conditional governed source set. Start with the named ticket through the masked-target Help Scout bridge. After the masked target transcript identifies unresolved closed claims, the same invocation permits the smallest sufficient read-only source set through the configured company-governed public KB and `orderdesk_context` tools. It does not permit unrelated exploration, attachments, Browser access, native personal plugins, raw provider APIs, CLI body output, credentials, customer-reply drafting, private-source subagents, or writes.

Do not ask the rep to name every source in advance. The orchestrator must name one unresolved claim before each conditional source call and must stop widening when that claim is resolved or one safe route is established.

## Prove the bridge

Use `helpscout_status` before calling `helpscout_get_support_context`. It must advertise `helpscout.support-context.typed-facts.v1`, `helpscout.support-context.complete-target.v1`, and `helpscout.support-context.masked-target-transcript.v1`; otherwise the bridge is a technical blocker. Never substitute another body-returning tool. After target intake, require `limits.targetThreads` to equal `all provider pages`, `target.threadLimitApplied` to be false, and `target.inspectedThreadCount` to equal `target.page.totalElements`. Any mismatch is a technical blocker because the bridge has not proven that it inspected the complete target conversation. Require `target.transcript.messages` to contain only `{role,text}` records and `target.transcript.characterCount` to be present. `helpscout_status` must also advertise `helpscout.support-correlation.opaque-handle.v1` with output mode `opaque-correlation-envelope` before accepting or passing a correlation handle. Validate that exact pair against `contracts/help-scout-correlation.json`.

For a whole-product benchmark, the static bridge contract is not enough.
Before selecting or opening a ticket, pass capability names, correlation output
mode, and tool names only from the connected runtimes through
`python3 scripts/runtime_preflight.py`. Send one JSON object on standard input with
exactly `helpScoutCapabilities`, `helpScoutCorrelationOutputMode`, and
`gatewayTools`. `runtime_contract_mismatch` exits nonzero and stops the
benchmark before body intake; it must not be downgraded to correlation
unavailability. Start a fresh Codex task/runtime after a merge, then repeat the
preflight. An ordinary one-ticket investigation may continue when only the
optional correlation capability is absent, but it must ignore all correlation
fields and mark correlation unavailable.

The `available` variant contains exactly `state`, `correlationHandle`, and `lookupKinds`; `not_found` and `unavailable` contain exactly `state` and an empty `lookupKinds`. This means a trusted correlation candidate exists; it does not grant an S3 Logs read. Only the owner-side orchestrator may grant that candidate after resolving an eligible server-held runtime claim. No variant contains `available`, `expiresAt`, eligibility flags, or an extra field. If capability or envelope is absent or mismatched, the target/history workflow may continue, but ignore every correlation field and mark correlation unavailable. Never infer handle support from the transcript or typed facts.

The MCP workflow has no automatic CLI body fallback. The explicit CLI body command is an operator-only local diagnostic, never model context and not a fallback. Internal notes and attachments are excluded: notes never contribute evidence, and attachments are not accessed.

## Standard support-context run

1. Locate and read the named target through the masked-target bridge with no history handles.
2. Form the sanitized question and closed claim ledger from the masked transcript. Do not retain or quote raw transcript prose in planner state.
3. Do not search history unless the claim ledger contains an unresolved `prior_case_handling` claim with a safe query term.
4. When that claim exists, run bounded metadata history search: at most three narrow queries, five unique candidates, and at most three selected fact reads.
5. Use only opaque `historySelectionHandle` values in `historicalSelectionHandles`; they are from earlier Stage-0 metadata results, process-local, expire after five minutes, and one-time. metadata and handles remain bounded. Expired, unissued, or reused handles fail before source inspection. Raw historical ticket numbers are never inputs.
6. Merge history into that claim and replan before any other source call.
7. Record planned, checked, skipped, unavailable, or stopped sources with dates, authority, conflicts, uncertainty, route, and next step.

raw Help Scout prose never reaches the model. Target intake returns readable masked customer/staff messages in order; identities, secrets, URLs, quoted history, signatures, notes, attachments, subject, preview, people metadata, and raw IDs are not exposed. The target transcript is evidence for forming a sanitized question and closed claims, not safe query text by itself. Historical tickets remain typed-facts-only; only an actual closed safe public term may form history queries. `blocked` stops the workflow safely without source-derived content.

Do not put it—or any customer, order, store, email, domain, URL, or other raw identifier—into a history or public-KB query. Stop on policy, scope, masking, audit, or source-read failure. Never create, save, or send a Help Scout draft.
