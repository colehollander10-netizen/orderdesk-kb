# Read-only Help Scout research

Read this file before a real Help Scout query.

## Require current authority

A current request containing one positive real Help Scout ticket number, or `/orderdesk` with that number, authorizes one task-scoped conditional governed source set. Start with the named ticket through the fact-only Help Scout bridge. After safe target facts identify unresolved claims, the same invocation permits the smallest sufficient read-only source set through the configured company-governed public KB and `orderdesk_context` tools. It does not permit unrelated exploration, attachments, Browser access, native personal plugins, raw provider APIs, CLI body output, credentials, customer-reply drafting, private-source subagents, or writes.

Do not ask the rep to name every source in advance. The orchestrator must name one unresolved claim before each conditional source call and must stop widening when that claim is resolved or one safe route is established.

## Prove the bridge

Use `helpscout_status` before calling `helpscout_get_support_context`. It must advertise both `helpscout.support-context.typed-facts.v1` and `helpscout.support-context.complete-target.v1`; otherwise the bridge is a technical blocker. Never substitute a body-returning tool. After target intake, require `limits.targetThreads` to equal `all provider pages`, `target.threadLimitApplied` to be false, and `target.inspectedThreadCount` to equal `target.page.totalElements`. Any mismatch is a technical blocker because the bridge has not proven that it inspected the complete target conversation. `helpscout_status` must also advertise `helpscout.support-correlation.opaque-handle.v1` with output mode `opaque-correlation-envelope` before accepting or passing a correlation handle. Validate that exact pair against `contracts/help-scout-correlation.json`.

The `available` variant contains exactly `state`, `correlationHandle`, and `lookupKinds`; `not_found` and `unavailable` contain exactly `state` and an empty `lookupKinds`. No variant contains `available`, `expiresAt`, or an extra field. If capability or envelope is absent or mismatched, the fact-only target/history workflow may continue, but ignore every correlation field and mark correlation unavailable. Never infer handle support from typed facts alone.

The MCP workflow has no automatic CLI body fallback. The explicit CLI body command is an operator-only local diagnostic, never model context and not a fallback. Notes never contribute evidence, and attachments are not accessed.

## Standard support-context run

1. Locate and read the named target through the fact-only bridge with no history handles.
2. Form the sanitized question, retain safe facts and fixed missing-evidence codes, then call `build_claims(sanitizedQuestion, safeFacts, missingEvidence)`.
3. Do not search history unless the claim ledger contains an unresolved `prior_case_handling` claim with a safe query term.
4. When that claim exists, run bounded metadata history search: at most three narrow queries, five unique candidates, and at most three selected fact reads.
5. Use only opaque `historySelectionHandle` values in `historicalSelectionHandles`; they are from earlier Stage-0 metadata results, process-local, expire after five minutes, and one-time. metadata and handles remain bounded. Expired, unissued, or reused handles fail before source inspection. Raw historical ticket numbers are never inputs.
6. Merge history into that claim and replan before any other source call.
7. Record planned, checked, skipped, unavailable, or stopped sources with dates, authority, conflicts, uncertainty, route, and next step.

The connector is fact-only: raw Help Scout prose never reaches the model. It returns closed enums, counts, missing-evidence codes, and rule IDs with zero or more safe facts. internal notes and attachments are ignored. `full` is route-ready. `partial` is not route-ready, contains zero or more safe facts plus fixed missing-evidence codes, and partial is not `masking_failed`; a zero-fact partial does not produce history search terms. Only an actual closed safe public term can form history queries. blocked stops the workflow safely without source-derived content.

Do not put it—or any customer, order, store, email, domain, URL, or other raw identifier—into a history or public-KB query. Stop on policy, scope, masking, audit, or source-read failure. Never create, save, or send a Help Scout draft.
