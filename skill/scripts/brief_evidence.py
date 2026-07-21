#!/usr/bin/env python3
"""Evaluate already-sanitized brief evidence without accessing private sources.

The caller assigns claim keys, claim values, and authority labels. This module
does not infer semantic contradiction or source authority. It only enforces the
brief contract, exposes explicit conflicts, and ranks review candidates by
explicit authority followed by source date. It does not sanitize input.
Repetition count is never used.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import re
from typing import Any


AUTHORITY_RANK = {
    "historical": 0,
    "unknown": 1,
    "supporting": 2,
    "authoritative": 3,
}

SOURCE_TYPES = {"help_scout", "public_kb", "slack", "notion", "code_context", "aws_logs"}

REQUIRED_FIELDS = {
    "id",
    "claim_key",
    "claim_value",
    "summary",
    "source_type",
    "safe_reference",
    "source_date",
    "retrieved_at",
    "authority",
    "claim_supported",
    "coverage",
}

try:
    from .investigation_plan import SOURCE_COVERAGE_REASONS, SOURCE_NAMES
except ImportError:  # Direct CLI execution.
    from investigation_plan import SOURCE_COVERAGE_REASONS, SOURCE_NAMES


def _required_string(record: dict[str, Any], field: str, index: int) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"evidence[{index}].{field} must be a non-empty string")
    return value.strip()


def _date_rank(value: str, index: int) -> int:
    if value == "unknown":
        return date.min.toordinal()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(
            f"evidence[{index}].source_date must be YYYY-MM-DD or unknown"
        )
    try:
        return date.fromisoformat(value).toordinal()
    except ValueError as error:
        raise ValueError(
            f"evidence[{index}].source_date must be YYYY-MM-DD or unknown"
        ) from error


def _retrieval_time(value: str, index: int) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError(f"evidence[{index}].retrieved_at must be UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as error:
        raise ValueError(f"evidence[{index}].retrieved_at must be UTC YYYY-MM-DDTHH:MM:SSZ") from error
    return value


def _normalize_record(record: Any, index: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError(f"evidence[{index}] must be an object")

    missing = REQUIRED_FIELDS - record.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(f"evidence[{index}] missing required fields: {names}")

    normalized = {
        field: _required_string(record, field, index) for field in REQUIRED_FIELDS
    }

    if normalized["source_type"] not in SOURCE_TYPES:
        allowed = ", ".join(sorted(SOURCE_TYPES))
        raise ValueError(
            f"evidence[{index}].source_type must be one of: {allowed}"
        )
    if normalized["authority"] not in AUTHORITY_RANK:
        allowed = ", ".join(AUTHORITY_RANK)
        raise ValueError(
            f"evidence[{index}].authority must be one of: {allowed}"
        )

    normalized["_date_rank"] = _date_rank(normalized["source_date"], index)
    normalized["retrieved_at"] = _retrieval_time(normalized["retrieved_at"], index)
    return normalized


def _normalize_source_coverage(source_coverage: Any) -> dict[str, dict[str, str]]:
    if not isinstance(source_coverage, dict) or set(source_coverage) != set(SOURCE_NAMES):
        raise ValueError("sourceCoverage must contain the complete source set")
    normalized = {}
    for source in SOURCE_NAMES:
        item = source_coverage[source]
        if not isinstance(item, dict) or set(item) != {"status", "reason"}:
            raise ValueError(f"sourceCoverage.{source} must contain only status and reason")
        if item["status"] not in SOURCE_COVERAGE_REASONS:
            raise ValueError(f"sourceCoverage.{source}.status is invalid")
        if item["reason"] not in SOURCE_COVERAGE_REASONS[item["status"]]:
            raise ValueError(f"sourceCoverage.{source}.reason is invalid for status")
        normalized[source] = dict(item)
    return normalized


def _preference_key(record: dict[str, Any]) -> tuple[int, int, str]:
    return (
        AUTHORITY_RANK[record["authority"]],
        record["_date_rank"],
        record["id"],
    )


def evaluate_evidence(records: Any, source_coverage: Any = None) -> dict[str, Any]:
    """Validate evidence and expose deterministic conflict-review preferences."""

    if not isinstance(records, list):
        raise ValueError("evidence must be a list")
    coverage = _normalize_source_coverage(source_coverage) if source_coverage is not None else None
    if not records:
        if coverage is None:
            raise ValueError("empty evidence requires source coverage")
        return {
            "evidence": [], "conflicts": [], "sourceCoverage": coverage,
            "contract": {"authority_is_caller_supplied": True, "semantic_conflicts_are_caller_supplied": True, "repetition_is_a_vote": False},
        }

    normalized = [_normalize_record(record, index) for index, record in enumerate(records)]
    ids = [record["id"] for record in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("evidence ids must be unique")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized:
        grouped[record["claim_key"]].append(record)

    conflicts = []
    for claim_key, claim_records in sorted(grouped.items()):
        claim_values = sorted({record["claim_value"] for record in claim_records})
        if len(claim_values) < 2:
            continue

        ranked = sorted(claim_records, key=_preference_key, reverse=True)
        top = ranked[0]
        top_rank = _preference_key(top)[:2]
        top_ties = [record for record in ranked if _preference_key(record)[:2] == top_rank]
        tied_values = {record["claim_value"] for record in top_ties}

        unresolved_for_unknown_authority = top["authority"] == "unknown"
        unresolved_for_tie = len(tied_values) > 1
        unresolved = unresolved_for_unknown_authority or unresolved_for_tie
        if unresolved_for_unknown_authority:
            reason = "authority_not_established"
        elif unresolved_for_tie:
            reason = "equal_authority_and_date_require_human_review"
        else:
            reason = "explicit_authority_then_recency; repetition_is_not_a_vote"
        conflicts.append(
            {
                "claim_key": claim_key,
                "status": "conflict",
                "preference_status": "unresolved" if unresolved else "preferred_for_review",
                "preferred_source_id": None if unresolved else top["id"],
                "competing_claim_values": claim_values,
                "source_ids": [record["id"] for record in ranked],
                "reason": reason,
            }
        )

    evidence = []
    for record in sorted(normalized, key=_preference_key, reverse=True):
        evidence.append({key: value for key, value in record.items() if key != "_date_rank"})

    result = {
        "evidence": evidence,
        "conflicts": conflicts,
        "contract": {
            "authority_is_caller_supplied": True,
            "semantic_conflicts_are_caller_supplied": True,
            "repetition_is_a_vote": False,
        },
    }
    if coverage is not None:
        result["sourceCoverage"] = coverage
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate an already-sanitized source/date/authority fixture."
    )
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.fixture.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            records = payload.get("evidence")
            source_coverage = payload.get("sourceCoverage")
        else:
            records = payload
            source_coverage = None
        result = evaluate_evidence(records, source_coverage)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
