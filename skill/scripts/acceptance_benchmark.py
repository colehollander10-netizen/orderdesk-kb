"""Content-free five-case synthetic acceptance benchmark."""

from __future__ import annotations

import json
from pathlib import Path

from .investigation_harness import run_case


def run_acceptance(cases: list[dict]) -> dict:
    rows = []
    for case in cases:
        harness_case = {
            "name": case["alias"],
            "claims": list(case["claims"]),
            "responses": case["responses"],
        }
        for key in ("conflict", "s3LogEligibility", "s3LogsCallable"):
            if key in case:
                harness_case[key] = case[key]
        result = run_case(harness_case)
        trace = [item["source"] for item in result["callTrace"]]
        rows.append({
            "alias": case["alias"],
            "route": result.get("route"),
            "expectedRoute": case["expectedRoute"],
            "routePassed": result.get("route") == case["expectedRoute"],
            "trace": trace,
            "tracePassed": trace == case["expectedTrace"],
            "targetThreadCount": case.get("targetThreadCount", 1),
            "ignoredHistoricalClaimCount": len(
                case.get("historicalClaimKinds", [])
            ),
            "status": result["plan"]["status"],
        })
    return {
        "schemaVersion": 1,
        "caseCount": len(rows),
        "passed": len(rows) == 5
        and all(row["routePassed"] and row["tracePassed"] for row in rows),
        "cases": rows,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    cases = json.loads(
        (root / "tests/fixtures/acceptance_cases.json").read_text(
            encoding="utf-8"
        )
    )
    result = run_acceptance(cases)
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
