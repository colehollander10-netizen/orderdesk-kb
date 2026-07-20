# Support context brief

Use this internal format after any approved private-source read:

    **Support Context Brief**

    **Question / Scope**
    <sanitized support question and the private sources authorized now>

    **What I Checked**
    - Boundary: <task-level authority; read-only tools; caps used; blockers>
    - Public KB: <queries, cache timestamp, source links, or not checked>
    - Private sources: <source, minimized query/read shape, result counts, dates>

    **Coverage and Freshness**
    - Slack: <bounded conversation/time/message window; result; explicitly not
      workspace-wide, or not checked>
    - Notion: <title-only query and result cap; selected pages read or page
      bodies unchecked; explicitly not a comprehensive Notion absence, or not
      checked>
    - Bitbucket: <paths/files checked; or safe failure code and remained
      unchecked with no code-behavior inference>
    - Public KB freshness: <health checked at; newest and oldest `fetched_at`;
      cache-acquisition caveat; or not checked>

    **Route**
    <exactly one six-route label> - <one-sentence evidence-based reason>

    **Source Ledger**
    - Source A - <source type> - <source date or unknown> -
      <authority: authoritative/supporting/historical/unknown> -
      <safe reference or public link> - <claim supported>

    **Evidence Status**
    - Documented behavior: <directly sourced behavior or “not found”>
    - Possible explanation: <synthesis that is not proven>
    - Not established: <configuration/runtime/account facts still needed>

    **Likely Pattern**
    <one short synthesis with its evidence level, or “not established”>

    **Similar Tickets**
    - <include only when Help Scout was used; date/status/freshness, symptom
      match, root-cause match or not established, verified resolution or not
      established, and doc conflict/caveat>

    **Conflicts**
    - <claim key> - <competing source references and values> -
      <preferred source plus authority/date reason, or “unresolved”>

    **Unknowns**
    - <smallest missing fact or unavailable source that blocks certainty>

    **Public KB Links**
    - <title> - <url> - <why it matters>

    **Suggested Next Step**
    <one practical investigation step, owner handoff, or focused question>

    **Reply Boundary**
    No customer-facing draft written.

Use Candidate A/B and Source A/B labels by default. Include a private ticket,
page, channel, or code reference only when the current user explicitly needs it
for internal follow-up. Never include private references in customer copy.

If a section does not apply, write `not checked`, `not found`, or `not
established`; do not fill the gap with inference. Keep the brief compact enough
for a support rep to scan before opening the underlying sources.

Never use bare `not found` for Slack or Notion. Use the coverage-specific
phrasing above so an empty bounded window or title query cannot read as a
comprehensive absence claim.

Always retain this freshness line in a multi-source brief. When the public KB
was used, run its health check and record when health was checked plus the
newest and oldest `fetched_at` values; say that cache acquisition does not prove
the live pages are unchanged. When it was not used, record `not checked` rather
than omitting the line.

Every material source must appear in the Source Ledger with its source type,
source date (or `unknown`), and explicit authority. Do not infer authority from
source type alone. Several historical sources repeating one resolution do not
outvote one newer, explicitly authoritative source. Repetition is not a vote.
If authority is unknown, keep the conflict unresolved.

## Optional deterministic conflict check

Use `../scripts/brief_evidence.py` only when records are already sanitized and
the caller has explicitly assigned each claim key, claim value, source type,
source date, and authority. It validates the ledger and ranks conflict-review
candidates by explicit authority and date. It does not:

- sanitize input;
- infer authority;
- detect semantic conflicts; or
- turn a preferred review candidate into proven truth.

Do not write private evidence to a temporary fixture unless the current task
has an approved output and retention location. Apply the same ledger contract
manually when that boundary is absent.

After a separate customer-copy request, use the reviewed evidence without
reopening private sources unless new research is required. Return only clean
paste-ready text with public links placed naturally.
