# Order Desk Evidence Convergence Design

**Date:** 2026-07-27

## Goal

Two capable AIs given the same `/orderdesk` skill, the same safely masked ticket
intake, and the same governed source results may explain the investigation in
different words. They must not materially disagree about:

- the sanitized support question;
- the closed claims that need evidence;
- which governed source can establish each claim;
- which evidence was accepted, rejected, unresolved, or unavailable;
- source authority, freshness, conflicts, and bounded coverage;
- the final six-route label; or
- the next-step category and responsible owner.

This is evidence and decision convergence, not prose convergence.

## Non-goals

- Do not standardize sentences, tone, paragraph length, or exact formatting.
- Do not add source colors, badges, `@` mentions, cards, or other visual
  treatment in this slice.
- Do not expose sanitization, capability negotiation, masking receipts, audit
  mechanics, tool inventories, or internal error codes in the normal
  Support-facing response.
- Do not add sources, widen allowlists, change credentials, or add any write or
  customer-reply capability.
- Do not claim that deterministic routing proves a correct Support answer.

## Considered approaches

### Prompt-only consistency

Add stronger prose instructions to `SKILL.md`. This is the smallest change, but
it leaves evidence selection, authority, route, and next-step drift mostly
unchecked.

### Evidence-convergence contract

Keep the existing deterministic planner and evidence evaluator, then require a
canonical decision frame before natural-language rendering. Tests verify that
equivalent reordered inputs produce the same decision frame. This is the
selected approach.

### Fully deterministic prose

Render every brief from one fixed template. This maximizes textual similarity
but makes the product robotic and over-constrains useful explanation.

## Design

### 1. Canonical decision frame

Add a small deterministic module that accepts already-sanitized outputs from
the existing planning and evidence layers and produces one normalized frame:

- sanitized question categories;
- sorted claim dispositions;
- complete source coverage;
- sorted accepted evidence references and claim roles;
- normalized conflicts and unknowns;
- one route from the existing six-route taxonomy; and
- one normalized next-step category plus owner class.

The frame contains no raw source prose, customer data, operational identifiers,
opaque handles, unrestricted code, or raw logs.

Ordering differences do not change the frame. Duplicate evidence never becomes
an authority vote.

### 2. Route and next-step invariants

The final brief must use the route and next-step category from the canonical
frame. A renderer may clarify the explanation, but it must not:

- add a source that was skipped or unavailable;
- turn supporting evidence into authoritative evidence;
- turn an unresolved claim into a resolved claim;
- infer absence from a bounded empty result;
- convert code-at-commit evidence into deployment or runtime evidence;
- convert Slack discussion into approved process;
- choose a different route; or
- send the ticket to a materially different owner.

### 3. Natural Support-facing rendering

After the decision frame is fixed, the AI may write naturally. The normal
Support view leads with what the customer needs, what the evidence establishes,
what remains unclear, and the recommended next move.

Background safety checks remain enforced but are not narrated as routine
progress. When a background failure changes the answer, translate it into one
plain sentence such as: “I couldn’t safely use that source, so this part remains
unconfirmed.” Technical audit details remain available only when explicitly
requested by an operator.

Sources should appear naturally beside the findings they support. Visual source
treatment is deferred.

### 4. Skill contract

Update `SKILL.md`, `references/internal-brief.md`, and the machine-readable
investigation contract so every compatible AI is told:

1. run the same closed-claim planner;
2. merge source results through the same disposition rules;
3. freeze the canonical decision frame;
4. render from that frame without changing its evidence or decision; and
5. keep routine safety machinery out of the Support-facing response.

## Testing

Use invented-only fixtures.

1. Write a failing contract test requiring the convergence instructions and
   machine-readable manifest fields.
2. Write a failing behavioral test that passes semantically identical evidence
   and claim inputs in different orders and requires identical decision frames.
3. Cover duplicate supporting evidence, unresolved bounded searches,
   code-only evidence, Slack-only evidence, and intent-versus-implementation
   conflict.
4. Verify that prose fields are not part of the equality contract.
5. Run the focused tests, the complete `orderdesk-kb` test suite, contract
   smoke checks, and `git diff --check`.

## Success criteria

- Equivalent safe inputs yield identical claim dispositions, source coverage,
  evidence roles, conflicts, route, and next-step category.
- Natural-language summaries may differ without failing the contract.
- No test or fixture contains real source content or operational identifiers.
- The normal brief no longer requires routine capability, masking, receipt, or
  audit narration.
- Existing fail-closed behavior, source boundaries, and the no-reply boundary
  remain unchanged.
