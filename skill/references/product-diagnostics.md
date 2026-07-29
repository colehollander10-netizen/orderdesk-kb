# Order Desk product diagnostics

Use this reference before answering underspecified troubleshooting,
integration, folder, or rule questions.

## Gate ambiguous troubleshooting

Do not query ask or triage with a generic symptom such as “an order did not
import.” First establish:

- integration/provider and the store or service role;
- data-flow direction and affected object;
- expected behavior versus observed behavior;
- sanitized exact error or skipped-step wording, when available;
- when governed attachment coverage is complete, the sanitized exact error and
  visible automation chain from the attachment evidence envelope;
- approximate occurrence time and whether all or only some records are
  affected.

Ask one focused question when the provider or flow is missing. Never let a
high-similarity article silently choose the customer's platform.

For a request that asks for cause, treat any missing field
above as an intake blocker when it could change the source plan. Do not query
the KB or choose a route merely to fill the silence with a list
of documented settings. Ask the single smallest question that separates the
credible paths.

Do not ask the operator to paste customer, order, store, or credential
identifiers into agent chat. If an exact private identifier is required for a
human investigation or an unavailable source, name that requirement in the
handoff without requesting its value.

When a decisive Help Scout attachment is partial, unreadable, blocked, or
unavailable, preserve that closed material ambiguity. Ask one focused
human-inspection question about the missing error or visible automation-chain
step; do not turn the gap into a generic KB, Slack, Notion, code, or historical
ticket search. Complete governed attachment evidence may establish the exact
sanitized error and visible event -> filters -> actions chain, but does not
establish customer configuration, runtime cause, deployment, or a fix.

## Describe integration direction

Express integration behavior as source -> Order Desk -> destination, naming
the object and operation:

- order import;
- fulfillment submission;
- inventory pull or push;
- shipment/tracking return;
- product or item-data exchange.

Do not use bare “integrates with” as a complete answer. Verify each direction
separately; support for one direction does not prove another.

## Use Order Desk-native terms

- Distinguish an external channel's order status from an Order Desk folder.
- Treat a folder as organization/filtering state, not an action by itself.
- For rule problems, capture the exact event -> filters -> actions chain and
  the folder transition involved.
- Never imply that moving into a folder changes an external system unless a
  documented rule/action or integration setting performs that change.
- Use store, folder, rule event, filter, action, inventory item, and order item
  precisely.

## Separate evidence from inference

Classify internal conclusions:

- **Documented behavior:** directly supported by a cited current-enough public
  guide.
- **Possible explanation:** consistent with evidence but not proven for this
  account or event.
- **Not established:** requires account state, logs, code, an internal owner,
  or another approved source.

Public docs cannot establish a customer's current configuration, an incident,
bug status, rollout, roadmap, contractual promise, or engineering ETA. Never
promise a fix, availability, or timing from retrieval alone.

## Choose one support route

Use exactly one route for an internal support brief:

- **Support can answer:** available evidence supports a safe explanation,
  documented step, or bounded workaround without another owner.
- **Store configuration / Rule Builder:** the next decisive evidence is an
  authorized store setting, integration mapping, folder transition, or exact
  event -> filters -> actions chain. Do not choose this route merely because a
  public guide lists configuration options.
- **Logs or runtime investigation:** the question requires an event timeline,
  API/provider response, job state, fulfillment state, or other runtime fact.
- **Likely code change:** implementation evidence points to engineering work or
  the case cannot be resolved without code ownership. Do not label a bug
  confirmed from retrieval alone.
- **Manual admin action / product gap:** an authorized administrator must act,
  or the requested behavior is a product limitation rather than a supported
  self-service workflow.
- **Insufficient evidence — abstain:** the provider, data-flow direction,
  affected object, expected/observed behavior, or decisive source is missing.

The route names the next evidence or owner. It does not prove root cause,
authorize the source, or permit the action.

For a field-attribution mismatch, structural code evidence may show that two
fields are distinct without establishing creation-time assignment, defaults, or
runtime values. If Support can inspect the authorized current order, request, or
integration record to determine whether the incoming value is present, keep the
route **Insufficient evidence — abstain** and make that one observable fact the
Support-owned next step. Escalate to Engineering only if the value is present
and the product ignores or replaces it, or if only Engineering can obtain the
fact.
