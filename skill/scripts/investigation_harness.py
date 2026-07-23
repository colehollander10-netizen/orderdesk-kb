"""Synthetic-only cross-source acceptance harness for the investigation contract."""

from __future__ import annotations

from typing import Any, Callable

from .brief_evidence import evaluate_evidence
from .investigation_findings import derive_cross_source_findings
from .investigation_plan import STOP_ERRORS, merge_source_result, plan_investigation, stopped_plan


SOURCE_TYPE = {
    "helpscout_history": "help_scout",
    "public_kb": "public_kb",
    "slack": "slack",
    "notion": "notion",
    "code_context": "code_context",
    "s3_logs": "s3_logs",
}
AUTHORITY = {
    "helpscout_history": "historical",
    "public_kb": "authoritative",
    "slack": "supporting",
    "notion": "authoritative",
    "code_context": "supporting",
    "s3_logs": "supporting",
}


def _callback_envelope(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("outcome") not in {"resolved", "unresolved", "unavailable", "stopped"}:
        raise ValueError("synthetic callback envelope is invalid")
    if value["outcome"] == "stopped":
        allowed_shapes = ({"outcome", "safeError"},)
    elif value["outcome"] == "resolved":
        allowed_shapes = ({"outcome"}, {"outcome", "evidence"})
    else:
        allowed_shapes = ({"outcome"},)
    if set(value) not in allowed_shapes:
        raise ValueError("synthetic callback envelope has unexpected fields")
    if value["outcome"] == "stopped" and value["safeError"] not in STOP_ERRORS:
        raise ValueError("synthetic callback stop error is invalid")
    if "evidence" in value and (not isinstance(value["evidence"], list) or not value["evidence"]):
        raise ValueError("synthetic callback evidence must be a non-empty list")
    return dict(value)


def expand_case_input(case: dict) -> dict:
    """Convert closed synthetic labels into the planner's complete safe state."""
    claims = []
    for index, kind in enumerate(case["claims"], start=1):
        record = {"id": f"c{index}", "kind": kind, "status": "unresolved", "safeQueryAvailable": True, "attempts": []}
        if kind == "runtime_event":
            record["logLookupKind"] = "order_import"
        claims.append(record)
    has_runtime = "runtime_event" in case["claims"]
    default_eligibility = {
        "trustedCorrelation": has_runtime,
        "boundedTimeWindow": has_runtime,
        "materiallyChangesRoute": has_runtime,
        "lookupKinds": ["order_import"] if has_runtime else [],
    }
    return {
        "ticketNumber": 11000,
        "targetContextState": "full",
        "sanitizedQuestion": {"productArea": "order_import", "workflow": "provider_to_order_desk", "observedBehavior": "orders_delayed", "expectedBehavior": "orders_imported", "safeTerms": ["order import", "delay"]},
        "safeFacts": [],
        "missingEvidence": claims,
        "capabilities": {
            "helpscout_history": True,
            "public_kb": True,
            "slack": True,
            "notion": True,
            "code_context": True,
            "s3_logs": case.get("s3LogsCallable", True),
        },
        "s3LogEligibility": case.get("s3LogEligibility", default_eligibility),
        "hardStopError": None,
    }


def synthetic_evidence(case: dict, step: dict, outcome: str) -> list[dict]:
    if outcome != "resolved":
        return []
    source = step["source"]
    claim_key = step["claimKind"]
    claim_value = f"{source}_supported"
    if case.get("conflict") and source in {"slack", "notion", "helpscout_history"}:
        claim_key = "resolution"
        claim_value = "current_policy" if source == "notion" else "historical_or_discussion"
    record_id = "notion-evidence" if case.get("conflict") and source == "notion" else f"{source}-evidence"
    return [{
        "id": record_id,
        "claim_key": claim_key,
        "claim_value": claim_value,
        "summary": "Synthetic sanitized governed evidence.",
        "source_type": SOURCE_TYPE[source],
        "safe_reference": f"synthetic-{source}",
        "source_date": "2026-07-21" if source == "notion" else "2025-01-01",
        "retrieved_at": "2026-07-21T16:30:00Z",
        "authority": AUTHORITY[source],
        "claim_supported": "Synthetic named claim evidence.",
        "coverage": "Synthetic bounded callback.",
    }]


def _route(case: dict, plan: dict, evidence_result: dict, findings: list[dict]) -> tuple[str, str]:
    if plan["status"] != "complete":
        if case["name"] == "runtime_without_schema":
            return "Insufficient evidence — abstain", "Hand off to the S3 Logs contract owner"
        return "Insufficient evidence — abstain", "Obtain the smallest missing governed fact"
    kinds = set(case["claims"])
    mismatch = next(
        (
            finding
            for finding in findings
            if finding["findingType"] == "intended_vs_implemented" and finding["relationship"] == "mismatch"
        ),
        None,
    )
    if mismatch:
        return mismatch["route"], mismatch["nextStep"]
    informal_mismatch = next(
        (
            finding
            for finding in findings
            if finding["findingType"] == "informal_vs_intended" and finding["relationship"] == "mismatch"
        ),
        None,
    )
    if informal_mismatch:
        return informal_mismatch["route"], informal_mismatch["nextStep"]
    if "implementation_behavior" in kinds and not ({"intended_process", "runtime_event"} & kinds):
        code_evidence = [item for item in evidence_result["evidence"] if item["source_type"] == "code_context"]
        if code_evidence and all(item["authority"] == "supporting" for item in code_evidence):
            return (
                "Insufficient evidence — abstain",
                (
                    "Ask Engineering to confirm whether the cited behavior is intentional and whether the cited commit is deployed for the affected path"
                    if kinds == {"implementation_behavior"}
                    else "Verify the implementation evidence against an authoritative process source or runtime evidence, then ask Engineering whether the cited commit is deployed for the affected path"
                ),
            )
    if "implementation_behavior" in kinds:
        return "Likely code change", "Hand off the cited implementation evidence"
    if "intended_process" in kinds:
        return "Store configuration / Rule Builder", "Apply the current intended process"
    if kinds == {"runtime_event"}:
        return (
            "Logs or runtime investigation",
            "Hand off the minimized S3 Logs finding and the separate human-only evidence artifact",
        )
    if kinds == {"recent_team_context"}:
        slack_evidence = [item for item in evidence_result["evidence"] if item["source_type"] == "slack"]
        if slack_evidence and all(item["authority"] == "supporting" for item in slack_evidence):
            return (
                "Insufficient evidence — abstain",
                "Verify the recent Slack workaround against an authoritative process source or runtime evidence before treating it as confirmed",
            )
    return "Support can answer", "Use the bounded evidence in the internal investigation"


def render_brief(plan: dict, evidence_result: dict, findings: list[dict], route: str, next_step: str) -> str:
    plan_lines = "\n".join(
        f"- {item['claimId']}: {item['status']}; source: {item['source'] or 'none'}; reason: {item['reason']}"
        for item in plan["claimDispositions"]
    )
    checked_lines = "\n".join(
        f"- {source}: {item['status']} ({item['reason']})"
        for source, item in plan["sourceCoverage"].items()
        if item["status"] in {"checked", "unavailable", "stopped"}
    )
    checked_lines = checked_lines or "- No governed source completed."
    coverage_lines = []
    for source, disposition in plan["sourceCoverage"].items():
        source_type = SOURCE_TYPE.get(source)
        records = [item for item in evidence_result["evidence"] if item["source_type"] == source_type]
        if records:
            details = "; ".join(
                f"date {item['source_date']}; retrieved {item['retrieved_at']}; {item['coverage']}"
                for item in records
            )
            coverage_lines.append(f"- {source}: {disposition['status']} ({disposition['reason']}); {details}")
        else:
            coverage_lines.append(f"- {source}: {disposition['status']} ({disposition['reason']})")
    coverage = "\n".join(coverage_lines)
    ledger = "\n".join(
        f"- {item['source_type']} | {item['safe_reference']} | {item['source_date']} | {item['retrieved_at']} | {item['authority']} | {item['claim_supported']} | {item['summary']}"
        for item in evidence_result["evidence"]
    ) or "- No governed evidence established."
    mismatch = next(
        (
            finding
            for finding in findings
            if finding["findingType"] == "intended_vs_implemented" and finding["relationship"] == "mismatch"
        ),
        None,
    )
    informal_mismatch = next(
        (
            finding
            for finding in findings
            if finding["findingType"] == "informal_vs_intended" and finding["relationship"] == "mismatch"
        ),
        None,
    )
    if mismatch:
        conflicts = "Notion establishes intended process; code describes implementation at the cited commit. Neither source establishes runtime behavior or deployment."
    elif informal_mismatch:
        conflicts = "Slack describes a recent informal workaround; Notion establishes the intended process. The informal workaround differs from the authoritative process."
    else:
        conflicts = "; ".join(f"{item['claim_key']}: {', '.join(item['competing_claim_values'])}; refs {', '.join(item['source_ids'])}; {item['reason']}" for item in evidence_result["conflicts"]) or "None."
    similar = "History checked: bounded historical evidence is not current policy." if plan["sourceCoverage"]["helpscout_history"]["status"] == "checked" else "History not checked."
    code_only_supporting = route == "Insufficient evidence — abstain" and evidence_result["evidence"] and all(
        item["source_type"] == "code_context" and item["authority"] == "supporting"
        for item in evidence_result["evidence"]
    )
    slack_only_supporting = route == "Insufficient evidence — abstain" and evidence_result["evidence"] and all(
        item["source_type"] == "slack" and item["authority"] == "supporting"
        for item in evidence_result["evidence"]
    )
    if mismatch:
        intended = " ".join(mismatch["intended"]["statements"])
        implemented = " ".join(mismatch["implemented"]["statements"])
        likely_pattern = f"{intended} {implemented} At the cited commit, implementation appears inconsistent with the intended process."
        evidence_status = "The intended-process and implementation claims are both established within their own source roles; neither source globally wins or proves production behavior."
        unknown = "The deployed commit, runtime path, and correct remediation remain unknown."
    elif informal_mismatch:
        informal = " ".join(informal_mismatch["informal"]["statements"])
        intended = " ".join(informal_mismatch["intended"]["statements"])
        likely_pattern = f"{informal} {intended} The informal workaround differs from the authoritative process."
        evidence_status = "Slack is supporting informal context; Notion is authoritative only for the intended process. Neither source establishes the runtime outcome."
        unknown = "The runtime outcome and whether the workaround is approved remain unknown."
    elif code_only_supporting:
        claim_values = sorted({item["claim_value"].replace("_", " ") for item in evidence_result["evidence"]})
        likely_pattern = f"Across the cited commit-pinned passages, the implementation evidence consistently supports that {'; '.join(claim_values)}."
        evidence_status = "Code establishes implementation behavior only at the cited commit; code-only supporting evidence does not establish deployment, runtime cause, design intent, or that a code change is warranted."
        unknown = "The deployed commit, runtime path, intended behavior, and whether a change is desirable remain unknown."
    elif slack_only_supporting:
        likely_pattern = " ".join(item["summary"] for item in evidence_result["evidence"])
        evidence_status = "Slack provides a possible explanation, but Slack-only supporting evidence does not establish policy, deployment, runtime cause, or a confirmed fix."
        unknown = "Authoritative process or runtime confirmation remains missing."
    else:
        likely_pattern = " ".join(item["summary"] for item in evidence_result["evidence"]) or "Not established."
        evidence_status = "Documented behavior, possible explanation, and not established remain separate."
        unknown = next((f"{item['claimId']}: {item['reason']}" for item in plan["claimDispositions"] if item["status"] != "resolved"), "No unresolved claim.")
    public_records = [item for item in evidence_result["evidence"] if item["source_type"] == "public_kb"]
    public_links = "\n".join(f"- {item['safe_reference']}: {item['claim_supported']}" for item in public_records) or "Not checked; no public-KB claim was selected."
    return "\n\n".join((
        "**Support Investigation Brief**\n\n**Question / Scope**\nSanitized ticket investigation.",
        f"**Investigation Plan**\n{plan_lines}",
        f"**What I Checked**\n{checked_lines}",
        f"**Coverage and Freshness**\n{coverage}",
        f"**Route**\n{route}",
        f"**Source Ledger**\n{ledger}",
        f"**Evidence Status**\n{evidence_status}",
        f"**Likely Pattern**\n{likely_pattern}",
        f"**Similar Tickets**\n{similar}",
        f"**Conflicts**\n{conflicts}",
        f"**Unknowns**\n{unknown}",
        f"**Public KB Links**\n{public_links}",
        f"**Suggested Next Step**\n{next_step}",
        "**Reply Boundary**\nCustomer-reply drafting is outside `/orderdesk`; no customer-facing wording was produced.",
    ))


def run_case(case: dict, tool_runner: dict[str, Callable[..., dict]] | None = None) -> dict:
    """Run injected callbacks only; it never opens a connector or serializes a handle."""
    state = expand_case_input(case)
    private_correlation_handle = "opaque-test-handle"
    responses = {source: list(tokens) for source, tokens in case.get("responses", {}).items()}
    trace = [{"source": "help_scout_target", "claimId": None, "outcome": "checked", "handleTransit": False}]
    evidence: list[dict] = []
    plan = plan_investigation(state)
    while plan["status"] == "running":
        for step in plan["steps"]:
            source = step["source"]
            handle = private_correlation_handle if source == "s3_logs" else None
            if tool_runner and source in tool_runner:
                envelope = tool_runner[source](step, handle)
            else:
                envelope = responses[source].pop(0)
            envelope = _callback_envelope(envelope)
            outcome = envelope["outcome"]
            trace.append({
                "source": source,
                "claimId": step["claimId"],
                "outcome": outcome,
                "handleTransit": source == "s3_logs",
            })
            if outcome == "stopped":
                stopped = stopped_plan(state, envelope["safeError"])
                return {
                    "plan": stopped,
                    "sourceCoverage": stopped["sourceCoverage"],
                    "claims": stopped["claimDispositions"],
                    "callTrace": trace,
                }
            evidence.extend(envelope.get("evidence", synthetic_evidence(case, step, outcome)))
            plan = merge_source_result(state, {"claimId": step["claimId"], "source": source, "outcome": outcome})
            state = plan["planningState"]
        if plan["status"] == "stopped":
            break
        if plan["status"] == "running":
            continue
    evidence_result = evaluate_evidence(evidence, plan["sourceCoverage"])
    findings = derive_cross_source_findings(evidence_result["evidence"])
    route, next_step = _route(case, plan, evidence_result, findings)
    brief = render_brief(plan, evidence_result, findings, route, next_step)
    return {"plan": plan, "sourceCoverage": plan["sourceCoverage"], "evidence": evidence_result["evidence"], "evidenceResult": evidence_result, "findings": findings, "callTrace": trace, "claims": plan["claimDispositions"], "route": route, "nextStep": next_step, "brief": brief}
