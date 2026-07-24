"""Closed, content-free planning for one Help Scout support investigation."""

from __future__ import annotations

import copy
from typing import Any


SOURCE_NAMES = (
    "help_scout_target",
    "helpscout_history",
    "public_kb",
    "slack",
    "notion",
    "code_context",
    "s3_logs",
)
CLAIM_SOURCE_ROUTES = {
    "documented_behavior": ("public_kb",),
    "prior_case_handling": ("helpscout_history",),
    "recent_team_context": ("slack",),
    "intended_process": ("notion",),
    "implementation_behavior": ("code_context",),
    "runtime_event": ("s3_logs",),
}
LOG_LOOKUP_KINDS = {
    "fulfillment_submission",
    "order_import",
    "inventory_update",
    "shipment_tracking",
    "provider_api_error",
}
# Reviewed closed intake derivation. Unknown values never widen authority.
QUESTION_CLAIM_MAP = {
    ("order_import", "provider_to_order_desk", "orders_delayed", "orders_imported"): (
        "implementation_behavior", "recent_team_context", "runtime_event",
    ),
}
SAFE_FACT_CLAIM_MAP = {
    "missing_evidence_code": {
        "documented_behavior": ("documented_behavior", None),
        "prior_case_handling": ("prior_case_handling", None),
        "recent_team_context": ("recent_team_context", None),
        "intended_process": ("intended_process", None),
        "implementation_behavior": ("implementation_behavior", None),
        "runtime_order_import": ("runtime_event", "order_import"),
    },
}
SAFE_FACT_KEYS = {"provider_family", "affected_scope", "rule_event", "missing_evidence_code"}
STOP_ERRORS = {
    "support_context_blocked",
    "runtime_contract_mismatch",
    "policy_denied",
    "scope_denied",
    "unsafe_query",
    "masking_failed",
    "audit_failed",
    "handle_integrity_failed",
    "credential_boundary_failed",
}
ATTACHMENT_COVERAGE = {"complete", "partial", "none", "blocked", "unavailable"}
ATTACHMENT_DISPOSITIONS = {
    "complete": {"status": "complete", "reason": "attachment_evidence_complete"},
    "partial": {"status": "unavailable", "reason": "attachment_understanding_incomplete"},
    "none": {"status": "complete", "reason": "no_eligible_attachments"},
    "blocked": {"status": "blocked", "reason": "attachment_evidence_blocked"},
    "unavailable": {"status": "unavailable", "reason": "attachment_evidence_unavailable"},
}
COVERAGE_PRECEDENCE = {
    "skipped": 0,
    "planned": 1,
    "checked": 2,
    "unavailable": 3,
    "stopped": 4,
}
SOURCE_COVERAGE_REASONS = {
    "checked": {"target_facts_received", "governed_result_received"},
    "planned": {"next_eligible_source"},
    "skipped": {"not_needed_for_named_claim", "safe_query_unavailable", "log_not_material"},
    "unavailable": {
        "capability_unavailable",
        "correlation_unavailable",
        "log_kind_unavailable",
        "s3_log_lookup_unavailable",
        "source_unavailable",
        "time_window_unavailable",
    },
    "stopped": STOP_ERRORS,
}


def _require_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} has unexpected fields")
    return value


def _non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _validate_question(question: Any) -> dict[str, Any]:
    item = _require_keys(question, {"productArea", "workflow", "observedBehavior", "expectedBehavior", "safeTerms"}, "sanitizedQuestion")
    for key in ("productArea", "workflow", "observedBehavior", "expectedBehavior"):
        _non_empty_string(item[key], f"sanitizedQuestion.{key}")
    if not isinstance(item["safeTerms"], list) or any(not isinstance(term, str) or not term.strip() for term in item["safeTerms"]):
        raise ValueError("sanitizedQuestion.safeTerms must be a list of non-empty strings")
    return copy.deepcopy(item)


def _validate_fact(fact: Any, index: int) -> dict[str, str]:
    item = _require_keys(fact, {"key", "value"}, f"safeFacts[{index}]")
    key = _non_empty_string(item["key"], f"safeFacts[{index}].key")
    if key not in SAFE_FACT_KEYS:
        raise ValueError("safe fact key is undeclared")
    return {"key": key, "value": _non_empty_string(item["value"], f"safeFacts[{index}].value")}


def _validate_attempt(attempt: Any, index: int, claim_kind: str) -> dict[str, str]:
    item = _require_keys(attempt, {"source", "outcome"}, f"attempts[{index}]")
    if item["source"] not in CLAIM_SOURCE_ROUTES[claim_kind]:
        raise ValueError("attempt source is not eligible for claim")
    if item["outcome"] not in {"resolved", "unresolved", "unavailable"}:
        raise ValueError("attempt outcome is invalid")
    return copy.deepcopy(item)


def _validate_claim(claim: Any, index: int) -> dict[str, Any]:
    if not isinstance(claim, dict):
        raise ValueError(f"missingEvidence[{index}] must be an object")
    kind = claim.get("kind")
    if kind not in CLAIM_SOURCE_ROUTES:
        raise ValueError("claim kind is invalid")
    expected = {"id", "kind", "status", "safeQueryAvailable", "attempts"}
    if kind == "runtime_event":
        expected.add("logLookupKind")
    _require_keys(claim, expected, f"missingEvidence[{index}]")
    _non_empty_string(claim["id"], f"missingEvidence[{index}].id")
    if claim["status"] not in {"unresolved", "resolved"}:
        raise ValueError("claim status is invalid")
    if not isinstance(claim["safeQueryAvailable"], bool):
        raise ValueError("claim safeQueryAvailable must be boolean")
    if kind == "runtime_event" and claim["logLookupKind"] not in LOG_LOOKUP_KINDS:
        raise ValueError("claim logLookupKind is invalid")
    if not isinstance(claim["attempts"], list):
        raise ValueError("claim attempts must be a list")
    normalized = copy.deepcopy(claim)
    normalized["attempts"] = [_validate_attempt(value, attempt_index, kind) for attempt_index, value in enumerate(claim["attempts"])]
    return normalized


def _validate_s3_log_eligibility(value: Any) -> dict[str, Any]:
    item = _require_keys(
        value,
        {
            "trustedCorrelation",
            "boundedTimeWindow",
            "materiallyChangesRoute",
            "lookupKinds",
        },
        "s3LogEligibility",
    )
    for key in (
        "trustedCorrelation",
        "boundedTimeWindow",
        "materiallyChangesRoute",
    ):
        if not isinstance(item[key], bool):
            raise ValueError(f"s3LogEligibility.{key} must be boolean")
    lookup_kinds = item["lookupKinds"]
    if (
        not isinstance(lookup_kinds, list)
        or any(kind not in LOG_LOOKUP_KINDS for kind in lookup_kinds)
        or len(set(lookup_kinds)) != len(lookup_kinds)
    ):
        raise ValueError("s3LogEligibility.lookupKinds is invalid")
    return {
        "trustedCorrelation": item["trustedCorrelation"],
        "boundedTimeWindow": item["boundedTimeWindow"],
        "materiallyChangesRoute": item["materiallyChangesRoute"],
        "lookupKinds": list(lookup_kinds),
    }


def validate_planning_state(payload: object) -> dict[str, Any]:
    expected = {
        "ticketNumber",
        "targetContextState",
        "sanitizedQuestion",
        "safeFacts",
        "missingEvidence",
        "capabilities",
        "s3LogEligibility",
        "hardStopError",
        "targetAttachmentCoverage",
        "decisiveEvidenceAttachmentOnly",
    }
    data = _require_keys(payload, expected, "planning state")
    if isinstance(data["ticketNumber"], bool) or not isinstance(data["ticketNumber"], int) or data["ticketNumber"] <= 0:
        raise ValueError("ticketNumber must be a positive integer")
    if data["targetContextState"] not in {"full", "partial", "blocked"}:
        raise ValueError("targetContextState is invalid")
    if data["targetAttachmentCoverage"] not in ATTACHMENT_COVERAGE:
        raise ValueError("targetAttachmentCoverage is invalid")
    if not isinstance(data["decisiveEvidenceAttachmentOnly"], bool):
        raise ValueError("decisiveEvidenceAttachmentOnly must be boolean")
    if not isinstance(data["safeFacts"], list) or not isinstance(data["missingEvidence"], list):
        raise ValueError("safe facts and missing evidence must be lists")
    capabilities = data["capabilities"]
    required_capabilities = set(SOURCE_NAMES) - {"help_scout_target"}
    if not isinstance(capabilities, dict) or set(capabilities) != required_capabilities or any(not isinstance(value, bool) for value in capabilities.values()):
        raise ValueError("capabilities must contain the closed source set")
    if data["hardStopError"] is not None and data["hardStopError"] not in STOP_ERRORS:
        raise ValueError("hardStopError is invalid")
    claims = [_validate_claim(claim, index) for index, claim in enumerate(data["missingEvidence"])]
    ids = [claim["id"] for claim in claims]
    if len(ids) != len(set(ids)):
        raise ValueError("claim IDs must be unique")
    return {
        "ticketNumber": data["ticketNumber"],
        "targetContextState": data["targetContextState"],
        "sanitizedQuestion": _validate_question(data["sanitizedQuestion"]),
        "safeFacts": [_validate_fact(fact, index) for index, fact in enumerate(data["safeFacts"])],
        "missingEvidence": claims,
        "capabilities": copy.deepcopy(capabilities),
        "s3LogEligibility": _validate_s3_log_eligibility(data["s3LogEligibility"]),
        "hardStopError": data["hardStopError"],
        "targetAttachmentCoverage": data["targetAttachmentCoverage"],
        "decisiveEvidenceAttachmentOnly": data["decisiveEvidenceAttachmentOnly"],
    }


def build_claims(sanitized_question: dict, safe_facts: list[dict], missing_evidence: list[dict]) -> list[dict]:
    """Add only closed signal claims; source content never enters this state."""
    claims = {item["id"]: copy.deepcopy(item) for item in missing_evidence}
    derived = QUESTION_CLAIM_MAP.get((sanitized_question["productArea"], sanitized_question["workflow"], sanitized_question["observedBehavior"], sanitized_question["expectedBehavior"]), ()) if not missing_evidence else ()
    fact_derived = [SAFE_FACT_CLAIM_MAP.get(fact["key"], {}).get(fact["value"]) for fact in safe_facts]
    signals = sorted({*derived, *(fact[0] for fact in fact_derived if fact)})
    lookup_kind = next((fact[1] for fact in fact_derived if fact and fact[1]), None)
    if "runtime_event" in derived and sanitized_question["productArea"] == "order_import":
        lookup_kind = lookup_kind or "order_import"
    existing_kinds = {claim["kind"] for claim in claims.values()}
    for kind in signals:
        if kind in existing_kinds:
            continue
        claim_id = f"signal-{kind}"
        if claim_id in claims or (kind == "runtime_event" and lookup_kind is None):
            continue
        claim = {"id": claim_id, "kind": kind, "status": "unresolved", "safeQueryAvailable": bool(sanitized_question["safeTerms"]), "attempts": []}
        if kind == "runtime_event":
            claim["logLookupKind"] = lookup_kind
        claims[claim_id] = claim
        existing_kinds.add(kind)
    return [claims[key] for key in sorted(claims)]


def _disposition(claim: dict, status: str, source: str | None, reason: str, skipped: list[dict] | None = None) -> dict:
    return {"claimId": claim["id"], "status": status, "source": source, "reason": reason, "skippedSources": skipped or []}


def plan_claim(data: dict, claim: dict) -> tuple[dict, dict | None]:
    if claim["status"] == "resolved" or any(attempt["outcome"] == "resolved" for attempt in claim["attempts"]):
        resolved_attempt = next(
            (attempt for attempt in reversed(claim["attempts"]) if attempt["outcome"] == "resolved"),
            None,
        )
        return _disposition(
            claim,
            "resolved",
            resolved_attempt["source"] if resolved_attempt else None,
            "claim_resolved",
        ), None
    routes = CLAIM_SOURCE_ROUTES[claim["kind"]]
    if not claim["safeQueryAvailable"]:
        skipped = [{"source": source, "reason": "safe_query_unavailable"} for source in routes]
        return _disposition(claim, "exhausted", None, "safe_query_unavailable", skipped), None
    attempted = {attempt["source"] for attempt in claim["attempts"]}
    skipped = []
    for source in routes:
        if source in attempted:
            continue
        if not data["capabilities"][source]:
            reason = (
                "s3_log_lookup_unavailable"
                if source == "s3_logs"
                else "capability_unavailable"
            )
            skipped.append({"source": source, "reason": reason})
            continue
        if source == "s3_logs":
            eligibility = data["s3LogEligibility"]
            if not eligibility["trustedCorrelation"]:
                skipped.append({"source": source, "reason": "correlation_unavailable"})
                continue
            if not eligibility["boundedTimeWindow"]:
                skipped.append({"source": source, "reason": "time_window_unavailable"})
                continue
            if not eligibility["materiallyChangesRoute"]:
                skipped.append({"source": source, "reason": "log_not_material"})
                continue
            if claim["logLookupKind"] not in eligibility["lookupKinds"]:
                skipped.append({"source": source, "reason": "log_kind_unavailable"})
                continue
        step = {"claimId": claim["id"], "claimKind": claim["kind"], "source": source}
        if source == "s3_logs":
            step["logLookupKind"] = claim["logLookupKind"]
        return _disposition(claim, "planned", source, "next_eligible_source", skipped), step
    last = claim["attempts"][-1] if claim["attempts"] else None
    unavailable_reasons = SOURCE_COVERAGE_REASONS["unavailable"]
    last_skipped_reason = skipped[-1]["reason"] if skipped else None
    status = (
        "unavailable"
        if (last and last["outcome"] == "unavailable")
        or last_skipped_reason in unavailable_reasons
        else "exhausted"
    )
    return _disposition(claim, status, None, skipped[-1]["reason"] if skipped else "eligible_sources_exhausted", skipped), None


def promote_coverage(coverage: dict, source: str, status: str, reason: str) -> None:
    if status not in SOURCE_COVERAGE_REASONS or reason not in SOURCE_COVERAGE_REASONS[status]:
        raise ValueError("invalid source coverage disposition")
    if (
        COVERAGE_PRECEDENCE[status] > COVERAGE_PRECEDENCE[coverage[source]["status"]]
        or (
            status == coverage[source]["status"] == "skipped"
            and coverage[source]["reason"] == "not_needed_for_named_claim"
        )
    ):
        coverage[source] = {"status": status, "reason": reason}


def derive_source_coverage(data: dict, dispositions: list[dict]) -> dict:
    coverage = {source: {"status": "skipped", "reason": "not_needed_for_named_claim"} for source in SOURCE_NAMES}
    promote_coverage(coverage, "help_scout_target", "checked", "target_facts_received")
    for item in dispositions:
        for skipped in item["skippedSources"]:
            status = (
                "skipped"
                if skipped["reason"] in SOURCE_COVERAGE_REASONS["skipped"]
                else "unavailable"
            )
            promote_coverage(coverage, skipped["source"], status, skipped["reason"])
    attempts = [attempt for claim in data["missingEvidence"] for attempt in claim["attempts"]]
    for source in SOURCE_NAMES[1:]:
        source_attempts = [attempt for attempt in attempts if attempt["source"] == source]
        if any(attempt["outcome"] in {"resolved", "unresolved"} for attempt in source_attempts):
            promote_coverage(coverage, source, "checked", "governed_result_received")
        elif any(attempt["outcome"] == "unavailable" for attempt in source_attempts):
            promote_coverage(coverage, source, "unavailable", "source_unavailable")
    for item in dispositions:
        if item["status"] == "planned":
            promote_coverage(coverage, item["source"], "planned", "next_eligible_source")
    return coverage


def stopped_plan(data: dict, safe_error: str) -> dict:
    claims = data["missingEvidence"]
    return {
        "ticketNumber": data["ticketNumber"],
        "status": "stopped",
        "steps": [],
        "claimDispositions": [{"claimId": claim["id"], "status": "stopped", "source": None, "reason": safe_error, "skippedSources": []} for claim in claims],
        "sourceCoverage": {source: {"status": "stopped", "reason": safe_error} for source in SOURCE_NAMES},
    }


def plan_investigation(payload: object) -> dict:
    data = validate_planning_state(payload)
    data["missingEvidence"] = build_claims(data["sanitizedQuestion"], data["safeFacts"], data["missingEvidence"])
    safe_error = "support_context_blocked" if data["targetContextState"] == "blocked" else data["hardStopError"]
    if safe_error:
        return stopped_plan(data, safe_error)
    attachment_disposition = copy.deepcopy(
        ATTACHMENT_DISPOSITIONS[data["targetAttachmentCoverage"]]
    )
    if (
        data["decisiveEvidenceAttachmentOnly"]
        and data["targetAttachmentCoverage"] != "complete"
    ):
        if data["targetAttachmentCoverage"] == "none":
            attachment_disposition = {
                "status": "unavailable",
                "reason": "attachment_evidence_unavailable",
            }
        return {
            "ticketNumber": data["ticketNumber"],
            "status": "abstain",
            "steps": [],
            "claimDispositions": [
                _disposition(
                    claim,
                    "unavailable",
                    None,
                    attachment_disposition["reason"],
                )
                for claim in data["missingEvidence"]
            ],
            "sourceCoverage": derive_source_coverage(data, []),
            "targetAttachmentCoverage": data["targetAttachmentCoverage"],
            "targetAttachmentDisposition": attachment_disposition,
            "decisiveEvidenceAttachmentOnly": True,
        }
    dispositions, steps = [], []
    for claim in sorted(data["missingEvidence"], key=lambda item: item["id"]):
        disposition, step = plan_claim(data, claim)
        dispositions.append(disposition)
        if step:
            steps.append(step)
    if any(item["status"] == "planned" for item in dispositions):
        status = "running"
    elif dispositions and all(item["status"] == "resolved" for item in dispositions):
        status = "complete"
    else:
        status = "abstain"
    return {
        "ticketNumber": data["ticketNumber"],
        "status": status,
        "steps": steps,
        "claimDispositions": dispositions,
        "sourceCoverage": derive_source_coverage(data, dispositions),
        "targetAttachmentCoverage": data["targetAttachmentCoverage"],
        "targetAttachmentDisposition": attachment_disposition,
        "decisiveEvidenceAttachmentOnly": data["decisiveEvidenceAttachmentOnly"],
    }


def validate_result(result: object) -> dict[str, str]:
    if not isinstance(result, dict):
        raise ValueError("result must be an object")
    outcome = result.get("outcome")
    expected = {"claimId", "source", "outcome"}
    if outcome == "stopped":
        expected.add("safeError")
    _require_keys(result, expected, "result")
    if outcome not in {"resolved", "unresolved", "unavailable", "stopped"}:
        raise ValueError("result outcome is invalid")
    _non_empty_string(result["claimId"], "result.claimId")
    if result["source"] not in SOURCE_NAMES[1:]:
        raise ValueError("result source is invalid")
    if outcome == "stopped" and result["safeError"] not in STOP_ERRORS:
        raise ValueError("result safeError is invalid")
    return copy.deepcopy(result)


def merge_source_result(payload: object, result: object) -> dict:
    data = validate_planning_state(payload)
    current = plan_investigation(data)
    item = validate_result(result)
    planned = {(step["claimId"], step["source"]) for step in current["steps"]}
    if (item["claimId"], item["source"]) not in planned:
        raise ValueError("result must match a currently planned step")
    claim = next(claim for claim in data["missingEvidence"] if claim["id"] == item["claimId"])
    if item["outcome"] == "stopped":
        data["hardStopError"] = item["safeError"]
    else:
        claim["attempts"].append({"source": item["source"], "outcome": item["outcome"]})
        if item["outcome"] == "unavailable":
            data["capabilities"][item["source"]] = False
    next_plan = plan_investigation(data)
    next_plan["planningState"] = data
    return next_plan
