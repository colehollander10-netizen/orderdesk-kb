# Order Desk Support Brief Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `/orderdesk` evidence and routing decisions deterministic while replacing the default operator-style report with a concise Support-facing brief.

**Architecture:** Preserve `investigation_plan.py` and `brief_evidence.py` as the internal planning and evidence boundary. Express their stable decision fields in `investigation.json`, then make `SKILL.md`, `internal-brief.md`, and the synthetic harness render from that internal frame without displaying routine capability, masking, audit, receipt, or source-status mechanics.

**Tech Stack:** Markdown skill instructions, JSON contract, Python `unittest`, existing synthetic investigation harness.

## Global Constraints

- Preserve the governed read-only source set and exact claim-to-source routing.
- Preserve mask-before-model, fail-closed errors, bounded source coverage, and human-controlled replies.
- Use invented-only fixtures and tests; do not contact Help Scout, Slack, Notion, Bitbucket, S3, or any other provider.
- Natural prose may vary, but accepted evidence, authority, unresolved claims, conflicts, route, and next-step owner class must not.
- Routine safety machinery remains internal; a source failure that changes the answer is translated into one plain Support-facing sentence.
- Do not add visual source styling, badges, `@` mentions, or UI work.
- Local and synthetic verification do not establish deployment, production readiness, or team adoption.

---

### Task 1: Lock the Support-facing and convergence contracts with failing tests

**Files:**
- Modify: `tests/test_skill_contracts.py`
- Modify: `tests/test_investigation_harness.py`
- Modify: `skill/scripts/contract_smoke.py`

**Interfaces:**
- Consumes: existing `skill/contracts/investigation.json`, `skill/references/internal-brief.md`, `skill/SKILL.md`, and `run_case(case)`.
- Produces: failing assertions for the new hidden decision-frame contract and visible Support brief shape.

- [ ] **Step 1: Add the failing skill/manifest contract test**

Add this test to `MultiSourceBriefContractTests`:

```python
def test_support_brief_renders_from_a_hidden_converged_decision(self):
    skill = " ".join(SKILL.read_text().split())
    template = INTERNAL_BRIEF.read_text()
    manifest = json.loads(
        (ROOT / "skill" / "contracts" / "investigation.json").read_text()
    )

    for phrase in (
        "evidence and decision convergence, not prose convergence",
        "freeze the internal decision frame before writing",
        "must not change its accepted evidence, authority, route, or next-step owner",
        "routine safety machinery stays in the background",
    ):
        self.assertIn(phrase, skill.casefold())

    self.assertEqual(
        manifest["decisionFrame"]["fields"],
        [
            "sanitized_question",
            "claim_dispositions",
            "source_coverage",
            "accepted_evidence",
            "conflicts",
            "unknowns",
            "route",
            "next_step_owner",
        ],
    )
    self.assertTrue(manifest["decisionFrame"]["backgroundOnly"])
    self.assertTrue(manifest["decisionFrame"]["naturalLanguageMayVary"])
    self.assertEqual(
        manifest["requiredBriefSections"],
        [
            "What the customer needs",
            "What I found",
            "What this means",
            "Recommended next step",
            "Reply Boundary",
        ],
    )

    for heading in (
        "**What the customer needs**",
        "**What I found**",
        "**What this means**",
        "**Recommended next step**",
        "**Reply Boundary**",
    ):
        self.assertIn(heading, template)
    for operator_heading in (
        "**Investigation Plan**",
        "**What I Checked**",
        "**Coverage and Freshness**",
        "**Source Ledger**",
    ):
        self.assertNotIn(operator_heading, template)
```

- [ ] **Step 2: Add the failing synthetic-render test**

Replace the old required-section assertion in `tests/test_investigation_harness.py` with:

```python
for section in (
    "**What the customer needs**",
    "**What I found**",
    "**What this means**",
    "**Recommended next step**",
    "**Reply Boundary**",
):
    self.assertIn(section, result["brief"])

for operator_section in (
    "**Investigation Plan**",
    "**What I Checked**",
    "**Coverage and Freshness**",
    "**Source Ledger**",
):
    self.assertNotIn(operator_section, result["brief"])

self.assertEqual(result["briefDecision"]["route"], result["route"])
self.assertEqual(
    result["briefDecision"]["nextStepOwner"],
    result["nextStepOwner"],
)
self.assertEqual(
    result["briefDecision"]["claimDispositions"],
    result["plan"]["claimDispositions"],
)
self.assertEqual(
    result["briefDecision"]["sourceCoverage"],
    result["sourceCoverage"],
)
```

- [ ] **Step 3: Update the contract-smoke expectation first**

Change the expected `requiredBriefSections` list in `skill/scripts/contract_smoke.py` to the five Support-facing headings. Add checks requiring:

```python
require(
    manifest.get("decisionFrame", {}).get("backgroundOnly") is True,
    "decision frame must remain background-only",
)
require(
    manifest.get("decisionFrame", {}).get("naturalLanguageMayVary") is True,
    "decision frame must permit natural-language variation",
)
```

- [ ] **Step 4: Run the focused tests and confirm RED**

Run:

```bash
python3 -m unittest \
  tests.test_skill_contracts.MultiSourceBriefContractTests.test_support_brief_renders_from_a_hidden_converged_decision \
  tests.test_investigation_harness -v
```

Expected: FAIL because the current manifest lacks `decisionFrame`, the template still requires operator headings, and the harness does not expose `briefDecision`.

- [ ] **Step 5: Commit the failing tests**

```bash
git add tests/test_skill_contracts.py tests/test_investigation_harness.py skill/scripts/contract_smoke.py
git commit -m "test: define support brief convergence contract"
```

---

### Task 2: Implement the hidden decision frame and Support-facing brief

**Files:**
- Modify: `skill/contracts/investigation.json`
- Modify: `skill/SKILL.md`
- Modify: `skill/references/internal-brief.md`
- Modify: `skill/scripts/investigation_harness.py`

**Interfaces:**
- Consumes: final `plan`, normalized `evidence_result`, structured findings, existing `route`, and existing `next_step`.
- Produces: `briefDecision` with stable evidence/routing fields plus a natural-language `brief`.

- [ ] **Step 1: Add the machine-readable decision-frame contract**

Add to `skill/contracts/investigation.json`:

```json
"decisionFrame": {
  "backgroundOnly": true,
  "naturalLanguageMayVary": true,
  "fields": [
    "sanitized_question",
    "claim_dispositions",
    "source_coverage",
    "accepted_evidence",
    "conflicts",
    "unknowns",
    "route",
    "next_step_owner"
  ]
}
```

Replace `requiredBriefSections` with:

```json
[
  "What the customer needs",
  "What I found",
  "What this means",
  "Recommended next step",
  "Reply Boundary"
]
```

- [ ] **Step 2: Add the positive convergence recipe to `SKILL.md`**

Immediately before `## Render one internal brief`, add:

```markdown
## Converge before writing

The goal is evidence and decision convergence, not prose convergence. After the
last replan, freeze the internal decision frame before writing: sanitized
question, claim dispositions, complete source coverage, accepted evidence and
authority, conflicts, unknowns, one route, and one next-step owner. Natural
wording may vary, but the brief must not change its accepted evidence,
authority, unresolved claims, route, or next-step owner.

The decision frame is background-only. Routine safety machinery stays in the
background: do not narrate capability names, masking or attachment receipts,
audit mechanics, tool inventories, source caps, or internal error codes in the
normal Support response. When a stopped or unavailable source materially
limits the answer, translate only that consequence into plain language.
```

Replace the first paragraph under `## Render one internal brief` with:

```markdown
Follow [references/internal-brief.md](references/internal-brief.md). Write for
the Support person investigating the ticket: lead with what the customer needs,
attach each recognizable source naturally to the finding it supports, separate
documented behavior from possible explanation and unknowns, and finish with one
practical next step. Do not print the internal decision frame or routine
verification trace.
```

- [ ] **Step 3: Replace the visible brief template with a positive Support recipe**

Make `skill/references/internal-brief.md` define exactly:

```markdown
# Support Investigation Brief

The default brief is written for a Support person, not an operator. Render from
the completed background decision frame; do not print that frame.

**What the customer needs**
A short sanitized explanation of the workflow, observed behavior, and desired
outcome.

**What I found**
- **Recognizable source name:** the finding it directly supports, with its
  public link or safe internal reference when useful.
- Keep authority and uncertainty in the sentence. A bounded empty result is “no
  match in the checked scope,” never proof that the information does not exist.

**What this means**
Separate documented behavior, possible explanation, and what remains
unconfirmed. State a likely cause only when the frozen evidence directly
supports it.

**Recommended next step**
Exactly one practical Support action, focused question, or named owner handoff
from the frozen route and next-step owner.

**Reply Boundary**
Customer-reply drafting is outside `/orderdesk`; no customer-facing wording was
produced.
```

Retain the existing final paragraph listing content that must never appear in a
brief.

- [ ] **Step 4: Expose the stable decision frame in the synthetic harness**

Add:

```python
def next_step_owner(route: str) -> str:
    return {
        "Support can answer": "support",
        "Store configuration / Rule Builder": "support_configuration",
        "Logs or runtime investigation": "engineering_runtime",
        "Likely code change": "engineering",
        "Manual admin action / product gap": "product_admin",
        "Insufficient evidence — abstain": "source_owner",
    }[route]


def build_brief_decision(
    plan: dict,
    evidence_result: dict,
    findings: list[dict],
    route: str,
) -> dict:
    return {
        "claimDispositions": plan["claimDispositions"],
        "sourceCoverage": plan["sourceCoverage"],
        "acceptedEvidence": evidence_result["evidence"],
        "conflicts": evidence_result["conflicts"],
        "findings": findings,
        "route": route,
        "nextStepOwner": next_step_owner(route),
    }
```

Update `render_brief()` to use the five Support-facing headings and naturally
name the source in each finding. Keep the existing evidence-status, conflict,
code-only, Slack-only, and mismatch reasoning; remove only the operator-facing
rendering.

Return both fields from `run_case()`:

```python
"briefDecision": brief_decision,
"nextStepOwner": brief_decision["nextStepOwner"],
```

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run:

```bash
python3 -m unittest \
  tests.test_skill_contracts.MultiSourceBriefContractTests.test_support_brief_renders_from_a_hidden_converged_decision \
  tests.test_investigation_harness -v
```

Expected: PASS.

- [ ] **Step 6: Commit the implementation**

```bash
git add \
  skill/contracts/investigation.json \
  skill/SKILL.md \
  skill/references/internal-brief.md \
  skill/scripts/investigation_harness.py
git commit -m "feat: render converged support investigation briefs"
```

---

### Task 3: Verify the complete portable skill contract

**Files:**
- Modify only if verification exposes an in-scope defect.

**Interfaces:**
- Consumes: the complete branch diff.
- Produces: current local and synthetic verification evidence only.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all tests pass with no real-provider access.

- [ ] **Step 2: Run the tracked skill contract**

Run:

```bash
python3 skill/scripts/contract_smoke.py
```

Expected: `{"ok": true}`.

- [ ] **Step 3: Run static verification**

Run:

```bash
python3 -m py_compile \
  skill/scripts/investigation_harness.py \
  skill/scripts/contract_smoke.py
git diff --check
git status --short
```

Expected: compilation and diff check exit zero; status contains only intended branch files.

- [ ] **Step 4: Review the requirements against the diff**

Confirm:

- the source set, read-only boundary, masking boundary, stop errors, and Reply Boundary are unchanged;
- the decision frame is background-only;
- the visible brief has five Support-facing sections;
- source evidence remains naturally attached to findings;
- route and next-step owner derive from the frozen internal frame;
- no visual styling or provider changes entered the slice; and
- no completion statement implies deployment, production readiness, or team adoption.

- [ ] **Step 5: Handle any verification defect through the owning task**

If Task 3 reveals an in-scope defect, return to Task 1 for a failing regression
test, apply the minimal fix in Task 2, rerun all Task 3 commands, and stage only
the exact files changed by that red-green cycle.
