"""Derive closed cross-source findings from already-normalized safe evidence."""

from __future__ import annotations

import re
from typing import Any


_COMMIT_REFERENCE = re.compile(r"@[0-9a-f]{40}$")
_NOT_ESTABLISHED = ["deployed_commit", "runtime_path", "correct_remediation"]


def _role(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sourceIds": sorted(item["id"] for item in records),
        "values": sorted({item["claim_value"] for item in records}),
        "statements": [item["claim_supported"] for item in sorted(records, key=lambda item: item["id"])],
    }


def derive_cross_source_findings(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Relate source-specific claim roles without choosing one global winner."""
    claim_keys = sorted({item["claim_key"] for item in evidence})
    findings = []
    for claim_key in claim_keys:
        records = [item for item in evidence if item["claim_key"] == claim_key]
        intended_records = [
            item
            for item in records
            if item["source_type"] == "notion" and item["authority"] == "authoritative"
        ]
        implemented_records = [
            item
            for item in records
            if item["source_type"] == "code_context" and item["authority"] == "supporting"
        ]
        if not intended_records or not implemented_records:
            continue

        intended = _role(intended_records)
        implemented = _role(implemented_records)
        implemented["commitPinned"] = all(
            bool(_COMMIT_REFERENCE.search(item["safe_reference"]))
            for item in implemented_records
        )
        relationship = "aligned" if set(intended["values"]) == set(implemented["values"]) else "mismatch"
        if relationship == "mismatch":
            route = "Likely code change"
            next_step = "Ask Engineering to verify the deployed commit and reconcile the cited implementation with the authoritative intended process"
        else:
            route = "Insufficient evidence — abstain"
            next_step = "Verify the deployed commit and runtime path before treating aligned intent and implementation as the event cause"
        findings.append({
            "findingType": "intended_vs_implemented",
            "claimKey": claim_key,
            "relationship": relationship,
            "intended": intended,
            "implemented": implemented,
            "established": intended["statements"] + implemented["statements"],
            "notEstablished": list(_NOT_ESTABLISHED),
            "route": route,
            "nextStep": next_step,
        })
    return findings
