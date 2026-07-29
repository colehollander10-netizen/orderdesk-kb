"""Synthetic-only cross-source acceptance harness for the investigation contract."""

from __future__ import annotations

from typing import Any, Callable

from .brief_evidence import evaluate_evidence
from .investigation_findings import derive_cross_source_findings
from .investigation_plan import (
    STOP_ERRORS,
    authorize_source_step,
    freeze_claim_ledger,
    merge_source_result,
    plan_investigation,
    stopped_plan,
)


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
SOURCE_LABEL = {
    "help_scout": "Help Scout",
    "public_kb": "Public KB",
    "slack": "Slack",
    "notion": "Notion",
    "code_context": "Code context",
    "s3_logs": "S3 Logs",
}
ROUTE_OWNER = {
    "Support can answer": "Support",
    "Store configuration / Rule Builder": "Support configuration",
    "Logs or runtime investigation": "Engineering runtime",
    "Likely code change": "Engineering",
    "Manual admin action / product gap": "Product administration",
    "Insufficient evidence — abstain": "Source owner",
}
ROUTE_DISPLAY = {
    "Support can answer": "Support has enough to answer",
    "Store configuration / Rule Builder": "Check the store setup or Rule Builder",
    "Logs or runtime investigation": "Engineering should check the runtime path",
    "Likely code change": "Engineering review",
    "Manual admin action / product gap": "Product or admin follow-up",
    "Insufficient evidence — abstain": "More evidence is needed",
}
SUPPORT_VERIFIABLE_NEXT_FACTS = {
    "incoming_order_source_presence": (
        "Have Support determine whether the incoming custom-app order contains "
        "a source value before escalating"
    ),
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


def _bound_callback_evidence(records: list[object], step: dict) -> list[dict]:
    expected_source_type = SOURCE_TYPE[step["source"]]
    expected_authority = AUTHORITY[step["source"]]
    bound = []
    for value in records:
        if not isinstance(value, dict):
            raise ValueError("synthetic callback evidence is invalid")
        record = dict(value)
        if (
            record.pop("claim_id", None) != step["claimId"]
            or record.pop("claim_kind", None) != step["claimKind"]
            or record.get("source_type") != expected_source_type
            or record.get("authority") != expected_authority
        ):
            raise ValueError("synthetic callback evidence exceeds the authorized step")
        record["source_type"] = expected_source_type
        record["authority"] = expected_authority
        bound.append(record)
    return bound


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
        "targetAttachmentCoverage": case.get("targetAttachmentCoverage", "none"),
        "decisiveEvidenceAttachmentOnly": case.get("decisiveEvidenceAttachmentOnly", False),
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
        if plan.get("decisiveEvidenceAttachmentOnly"):
            if plan["targetAttachmentCoverage"] == "none":
                return (
                    "Insufficient evidence — abstain",
                    "Ask a human reviewer whether the missing sanitized visible error or event -> filters -> actions chain can be established without an available attachment.",
                )
            return (
                "Insufficient evidence — abstain",
                "Ask a human reviewer: what visible error or event -> filters -> actions step does the attachment show?",
            )
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
    support_next_fact = SUPPORT_VERIFIABLE_NEXT_FACTS.get(
        case.get("supportVerifiableMissingFact")
    )
    if support_next_fact and any(
        item["source_type"] == "code_context"
        for item in evidence_result["evidence"]
    ):
        return "Insufficient evidence — abstain", support_next_fact
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


def _interpretation(
    plan: dict,
    evidence_result: dict,
    findings: list[dict],
    route: str,
) -> dict[str, str]:
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
        evidence_status = (
            "The finding is established only within the role of the cited source."
            if evidence_result["evidence"]
            else "There is not enough evidence to establish what happened or why."
        )
        unknown = next(
            (
                "The smallest claim-specific governed fact is still missing."
                for item in plan["claimDispositions"]
                if item["status"] != "resolved"
            ),
            "No unresolved claim.",
        )
    return {
        "evidence_status": evidence_status,
        "likely_pattern": likely_pattern,
        "conflicts": conflicts,
        "unknown": unknown,
    }


def _next_step_owner(route: str, next_step: str) -> str:
    if "S3 Logs contract owner" in next_step:
        return "S3 Logs contract owner"
    if "Engineering" in next_step:
        return "Engineering"
    if "human reviewer" in next_step:
        return "Support reviewer"
    if "process owner" in next_step:
        return "Process owner"
    if next_step.startswith("Have Support "):
        return "Support"
    return ROUTE_OWNER[route]


def _next_step_category(route: str, next_step: str) -> str:
    if "S3 Logs contract owner" in next_step:
        return "contract_owner_handoff"
    if "human reviewer" in next_step:
        return "human_evidence_review"
    if "process owner" in next_step:
        return "process_owner_confirmation"
    if next_step.startswith("Have Support "):
        return "support_verification"
    if "Engineering" in next_step:
        return "engineering_verification"
    return {
        "Support can answer": "support_response",
        "Store configuration / Rule Builder": "store_configuration",
        "Logs or runtime investigation": "runtime_investigation",
        "Likely code change": "engineering_handoff",
        "Manual admin action / product gap": "manual_admin_action",
        "Insufficient evidence — abstain": "obtain_governed_evidence",
    }[route]


def build_brief_decision(
    planning_state: dict,
    plan: dict,
    evidence_result: dict,
    findings: list[dict],
    route: str,
    next_step: str,
    interpretation: dict[str, str],
) -> dict:
    claim_kind_by_id = {
        item["id"]: item["kind"]
        for item in planning_state["missingEvidence"]
    }
    claim_dispositions = sorted(
        (
            {
                "claim_kind": claim_kind_by_id[item["claimId"]],
                "status": item["status"],
                "source": item["source"],
                "reason": item["reason"],
                "skipped_sources": sorted(item["skippedSources"]),
            }
            for item in plan["claimDispositions"]
        ),
        key=lambda item: (
            item["claim_kind"],
            item["status"],
            item["source"] or "",
            item["reason"],
        ),
    )
    unknowns = [
        item["reason"]
        for item in plan["claimDispositions"]
        if item["status"] != "resolved"
    ]
    attachment_disposition = plan["targetAttachmentDisposition"]
    if attachment_disposition["status"] != "complete":
        unknowns.append(attachment_disposition["reason"])
    if interpretation["unknown"] != "No unresolved claim.":
        unknowns.append(interpretation["unknown"])
    return {
        "sanitized_question": {
            **planning_state["sanitizedQuestion"],
            "safeTerms": sorted(planning_state["sanitizedQuestion"]["safeTerms"]),
        },
        "claim_dispositions": claim_dispositions,
        "source_coverage": plan["sourceCoverage"],
        "accepted_evidence": sorted(
            evidence_result["evidence"],
            key=lambda item: (
                item["claim_key"],
                item["source_type"],
                item["safe_reference"],
                item["source_date"],
            ),
        ),
        "conflicts": sorted(
            evidence_result["conflicts"],
            key=lambda item: (item["claim_key"], tuple(item["source_ids"])),
        ),
        "unknowns": sorted(set(unknowns)),
        "findings": findings,
        "route": route,
        "next_step_category": _next_step_category(route, next_step),
        "next_step": next_step,
        "next_step_owner": _next_step_owner(route, next_step),
    }


def render_brief(
    sanitized_question: dict,
    plan: dict,
    evidence_result: dict,
    brief_decision: dict,
    interpretation: dict[str, str],
) -> str:
    observed = sanitized_question["observedBehavior"].replace("_", " ")
    expected = sanitized_question["expectedBehavior"].replace("_", " ")
    workflow = sanitized_question["workflow"].replace("_", " ")
    evidence_lines = "\n".join(
        (
            f"- **{SOURCE_LABEL[item['source_type']]}** — "
            f"`{item['safe_reference']}` ({item['source_date']}; "
            f"{item['authority']}; {item['coverage']}): {item['summary']}"
        )
        for item in evidence_result["evidence"]
    ) or "No governed source established the unresolved claim."
    attachment_note = (
        "\n\nAttachment evidence remains incomplete."
        if plan["targetAttachmentDisposition"]["status"] != "complete"
        else ""
    )
    meaning_parts = [
        interpretation["likely_pattern"],
        interpretation["evidence_status"],
    ]
    if interpretation["conflicts"] != "None.":
        meaning_parts.append(interpretation["conflicts"])
    if interpretation["unknown"] != "No unresolved claim.":
        meaning_parts.append(interpretation["unknown"])
    meaning = " ".join(meaning_parts)
    route = brief_decision["route"]
    next_step = brief_decision["next_step"]
    owner = brief_decision["next_step_owner"]
    return "\n\n".join((
        "**Support Investigation Brief**",
        (
            "**What the customer needs**\n"
            f"The customer needs help with {observed} in the {workflow} workflow "
            f"and expects {expected}."
        ),
        f"**What I found**\n{evidence_lines}{attachment_note}",
        f"**What this means**\n{meaning}",
        (
            "**Recommended next step**\n"
            f"**{ROUTE_DISPLAY[route]}** — {next_step}. Owner: {owner}."
        ),
        "**Reply Boundary**\nCustomer-reply drafting is outside `/orderdesk`; no customer-facing wording was produced.",
    ))


def run_case(case: dict, tool_runner: dict[str, Callable[..., dict]] | None = None) -> dict:
    """Run injected callbacks only; it never opens a connector or serializes a handle."""
    state = expand_case_input(case)
    private_correlation_handle = "opaque-test-handle"
    responses = {source: list(tokens) for source, tokens in case.get("responses", {}).items()}
    trace = [{"source": "help_scout_target", "claimId": None, "outcome": "checked", "handleTransit": False}]
    evidence: list[dict] = []
    frozen_claim_ledger = freeze_claim_ledger(state)
    plan = plan_investigation(state)
    while plan["status"] == "running":
        for step in plan["steps"]:
            source = step["source"]
            authorize_source_step(
                state,
                frozen_claim_ledger,
                step["claimId"],
                source,
            )
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
            if tool_runner and source in tool_runner and "evidence" in envelope:
                evidence.extend(_bound_callback_evidence(envelope["evidence"], step))
            else:
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
    interpretation = _interpretation(plan, evidence_result, findings, route)
    brief_decision = build_brief_decision(
        state,
        plan,
        evidence_result,
        findings,
        route,
        next_step,
        interpretation,
    )
    brief = render_brief(
        state["sanitizedQuestion"],
        plan,
        evidence_result,
        brief_decision,
        interpretation,
    )
    return {
        "plan": plan,
        "sourceCoverage": plan["sourceCoverage"],
        "evidence": evidence_result["evidence"],
        "evidenceResult": evidence_result,
        "findings": findings,
        "callTrace": trace,
        "claims": plan["claimDispositions"],
        "route": route,
        "nextStep": brief_decision["next_step"],
        "nextStepOwner": brief_decision["next_step_owner"],
        "briefDecision": brief_decision,
        "brief": brief,
    }
