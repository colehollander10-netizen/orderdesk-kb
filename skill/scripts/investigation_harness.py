"""Synthetic-only cross-source acceptance harness for the investigation contract."""

from __future__ import annotations

from typing import Any, Callable

from .brief_evidence import evaluate_evidence
from .investigation_plan import merge_source_result, plan_investigation


SOURCE_TYPE = {
    "helpscout_history": "help_scout",
    "public_kb": "public_kb",
    "slack": "slack",
    "notion": "notion",
    "code_context": "code_context",
    "aws_logs": "aws_logs",
}
AUTHORITY = {
    "helpscout_history": "historical",
    "public_kb": "authoritative",
    "slack": "supporting",
    "notion": "authoritative",
    "code_context": "supporting",
    "aws_logs": "supporting",
}
_SYNTHETIC_AWS_TRANSIT = object()


def expand_case_input(case: dict) -> dict:
    """Convert closed synthetic labels into the planner's complete safe state."""
    claims = []
    for index, kind in enumerate(case["claims"], start=1):
        record = {"id": f"c{index}", "kind": kind, "status": "unresolved", "safeQueryAvailable": True, "attempts": []}
        if kind == "runtime_event":
            record["logLookupKind"] = "order_import"
        claims.append(record)
    has_runtime = "runtime_event" in case["claims"]
    enabled = case.get("enabledLogKinds", ["order_import"] if has_runtime else [])
    return {
        "ticketNumber": 11000,
        "targetContextState": "full",
        "sanitizedQuestion": {"productArea": "order_import", "workflow": "provider_to_order_desk", "observedBehavior": "orders_delayed", "expectedBehavior": "orders_imported", "safeTerms": ["order import", "delay"]},
        "safeFacts": [],
        "missingEvidence": claims,
        "capabilities": {"helpscout_history": True, "public_kb": True, "slack": True, "notion": True, "code_context": True, "aws_logs": True},
        "correlationAvailable": bool(case.get("correlationAvailable")),
        "enabledLogKinds": enabled,
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


def _route(case: dict, plan: dict) -> tuple[str, str]:
    if plan["status"] != "complete":
        if case["name"] == "runtime_without_schema":
            return "Insufficient evidence — abstain", "Hand off to the AWS log-contract owner"
        return "Insufficient evidence — abstain", "Obtain the smallest missing governed fact"
    kinds = set(case["claims"])
    if "implementation_behavior" in kinds:
        return "Likely code change", "Hand off the cited implementation evidence"
    if "intended_process" in kinds:
        return "Store configuration / Rule Builder", "Apply the current intended process"
    return "Support can answer", "Use the bounded evidence in the internal investigation"


def run_case(case: dict, tool_runner: dict[str, Callable[..., str]] | None = None) -> dict:
    """Run injected callbacks only; it never opens a connector or serializes a handle."""
    state = expand_case_input(case)
    responses = {source: list(tokens) for source, tokens in case.get("responses", {}).items()}
    trace = [{"source": "help_scout_target", "claimId": None, "outcome": "checked", "handleTransit": False}]
    evidence: list[dict] = []
    plan = plan_investigation(state)
    while plan["status"] == "running":
        for step in plan["steps"]:
            source = step["source"]
            if tool_runner and source in tool_runner:
                token = tool_runner[source](step, _SYNTHETIC_AWS_TRANSIT if source == "aws_logs" else None)
            else:
                token = responses[source].pop(0)
            outcome, _, safe_error = token.partition(":")
            handle_transit = source == "aws_logs"
            if handle_transit and not case.get("correlationAvailable"):
                raise ValueError("AWS stub requires correlation availability")
            trace.append({"source": source, "claimId": step["claimId"], "outcome": outcome, "handleTransit": handle_transit})
            if outcome == "stopped":
                merged = merge_source_result(state, {"claimId": step["claimId"], "source": source, "outcome": outcome, "safeError": safe_error})
                plan = merged
                break
            evidence.extend(synthetic_evidence(case, step, outcome))
            plan = merge_source_result(state, {"claimId": step["claimId"], "source": source, "outcome": outcome})
            state = plan["planningState"]
        if plan["status"] == "stopped":
            break
        if plan["status"] == "running":
            continue
    route, next_step = _route(case, plan)
    evidence_result = evaluate_evidence(evidence, plan["sourceCoverage"])
    brief = None if plan["status"] == "stopped" else {"sections": ["Question / Scope", "Investigation Plan", "Source Ledger", "Reply Boundary"], "route": route}
    return {"plan": plan, "sourceCoverage": plan["sourceCoverage"], "evidence": evidence_result["evidence"], "evidenceResult": evidence_result, "callTrace": trace, "claims": plan["claimDispositions"], "route": route, "nextStep": next_step, "brief": brief}
