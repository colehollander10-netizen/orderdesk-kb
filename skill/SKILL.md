---
name: orderdesk
description: "Investigate one Order Desk Help Scout ticket through governed read-only Help Scout, public KB, Slack, Notion, code-context, and schema-enabled AWS log tools. Use when a Support rep supplies one positive Help Scout ticket number and needs a source-backed internal investigation brief. Select only sources that can resolve a named claim, preserve source authority and uncertainty, and never draft customer replies or perform writes."
---

# Order Desk ticket investigator

`/orderdesk` accepts one positive Help Scout ticket number and returns one internal investigation brief. Do not ask the rep to restate the symptom or supply customer, order, store, shipment, request, or credential identifiers. Read the ticket first through the fact-only governed Help Scout bridge.

Customer-reply drafting is outside this skill. Do not generate customer-facing wording, create or save a draft, or reopen private sources for reply work. End every run at the internal brief and its `Reply Boundary` line.

## Establish the governed boundary

The ticket-number invocation grants task-scoped authority for one conditional, read-only investigation through the configured company-governed Help Scout bridge and `orderdesk_context` gateway. It covers only the smallest sufficient governed source set selected by the claim loop. Do not substitute a personal plugin, Browser copy/paste, raw provider API, CLI body output, credential access, source writes, or unrelated exploration. Do not dispatch private-source subagents.

Read [references/help-scout.md](references/help-scout.md) before target intake, [references/product-diagnostics.md](references/product-diagnostics.md) before claim planning, [references/public-kb.md](references/public-kb.md) before KB access, and [references/governed-context.md](references/governed-context.md) before any `orderdesk_context` call.

## Read the target and form closed claims

A named real Help Scout ticket is the intake artifact. Proceed without a second approval prompt. Verify that `helpscout_status` advertises `helpscout.support-context.typed-facts.v1` before calling `helpscout_get_support_context`; an absent capability is a technical blocker. Before accepting or passing a correlation handle, require `helpscout.support-correlation.opaque-handle.v1` with output mode `opaque-correlation-envelope`; otherwise ignore correlation fields and mark correlation unavailable.

raw Help Scout prose never reaches the model. The fact-only bridge returns closed enums, counts, missing-evidence codes, and rule IDs plus zero or more safe facts; internal notes and attachments are ignored. It permits only `{state:"available", correlationHandle, lookupKinds}`, `{state:"not_found", lookupKinds:[]}`, or `{state:"unavailable", lookupKinds:[]}` correlation variants. `full` is route-ready; `partial` is not route-ready and partial is not `masking_failed`; a zero-fact partial does not produce history search terms. `blocked` stops the workflow safely. The explicit CLI body command is an operator-only local diagnostic, never model context and not a fallback.

Record the sanitized question as product area, workflow direction, observed behavior, expected behavior, and safe closed query terms. Convert missing evidence into `documented_behavior`, `prior_case_handling`, `recent_team_context`, `intended_process`, `implementation_behavior`, or `runtime_event`. Help Scout history occurs only after `build_claims(sanitizedQuestion, safeFacts, missingEvidence)` returns one unresolved `prior_case_handling` claim with a safe term. Then shortlist at most five unique metadata candidates across three narrow queries and read at most three opaque historical handles; they are process-local, expire after five minutes, and are one-time.

## Plan and execute the smallest source set

Use `scripts/investigation_plan.py` only with sanitized closed facts and safe availability booleans. Never place source prose, operational identifiers, customer data, or opaque handles in planner input, evidence, fixtures, or the brief.

| Unresolved claim | Source |
|---|---|
| `documented_behavior` | Public KB |
| `prior_case_handling` | Help Scout history |
| `recent_team_context` | governed `slack_search` |
| `intended_process` | governed `notion_search` / `notion_page` |
| `implementation_behavior` | governed `code_context` |
| `runtime_event` | governed schema-enabled `aws_log_lookup` |

Every private call names one unresolved claim. After each `resolved`, `unresolved`, `unavailable`, or `stopped` result, merge and replan. Claim dispositions are exactly `resolved`, `planned`, `exhausted`, `unavailable`, or `stopped`; source coverage is exactly `checked`, `planned`, `skipped`, `unavailable`, or `stopped`. Never use a cross-authority fallback that cannot establish the original claim.

AWS is optional. Use it only for `runtime_event`, only when the gateway advertises the schema-specific log contract, and only when trusted intake reports correlation availability. Pass the exact opaque handle directly once; never copy it into a planner, query, evidence, or brief. If unavailable, record the safe skipped reason and abstain; never browse S3 generically.

Stop before merge, replan, or rendering on `policy_denied`, `scope_denied`, `unsafe_query`, `masking_failed`, `audit_failed`, `handle_integrity_failed`, or `credential_boundary_failed`. Normal bounded unavailability is recorded truthfully.

## Render one internal brief

Follow [references/internal-brief.md](references/internal-brief.md). Include the Investigation Plan, complete coverage, freshness, one route, normalized Source Ledger, conflicts, unknowns, and one next step. Keep documented behavior, possible explanation, and not established separate. State a likely cause only when direct claim-specific evidence supports it.

A resolved retrieval claim is not automatically a resolved Support answer. Preserve the source that resolved each claim and apply its authority when choosing the route. In particular, Slack-only supporting evidence stays a possible explanation and must abstain unless the governed result establishes an explicit decision and owner or another authoritative or runtime source confirms the action.

Code-only supporting evidence may establish implementation behavior at the cited commit, but it must not become a deployment claim, runtime diagnosis, design-intent claim, or automatic **Likely code change** route. Abstain until intended-process or runtime evidence establishes the missing claim, and ask Engineering to verify intent plus the deployed commit.

Before rendering a multi-source conclusion, preserve claim roles. Notion may establish intended process, while code may establish implementation at the cited commit. Compare those roles through a structured finding; neither source globally wins. When they differ, state the intent-versus-implementation mismatch, then preserve the deployed commit, runtime path, and correct remediation as separate unknowns. A mismatch may earn **Likely code change** only as an Engineering-review route, never as proof of production cause.

Apply the same role discipline to informal Slack context and authoritative intended process evidence. Slack may establish that a workaround was recently discussed; it does not approve that workaround. When Slack and the owner-backed process differ, state the informal-versus-intended mismatch, preserve runtime outcome and workaround approval as unknowns, follow the authoritative process, and send the workaround to the process owner for review.

**Reply Boundary**
Customer-reply drafting is outside `/orderdesk`; no customer-facing wording was produced.

## Hard boundaries

Never create, save, or send a Help Scout draft. Keep every source read-only and never write, message, change credentials, or use raw private content. An unavailable source is not checked. Zero evidence must choose **Insufficient evidence — abstain**.
