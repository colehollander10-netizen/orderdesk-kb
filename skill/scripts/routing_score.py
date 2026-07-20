#!/usr/bin/env python3
"""Score one sanitized routing fixture through a small JSON CLI."""

import json
from pathlib import Path
import sys


ROUTES = {
    "support_answerable",
    "store_configuration",
    "logs_runtime",
    "code_change",
    "manual_admin_product_gap",
    "insufficient_evidence",
}


def main() -> int:
    fixture = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    expected_route = fixture["expected_route"]
    observed_result = fixture["observed_result"]
    observed_route = observed_result["route"]
    for label, route in (
        ("expected_route", expected_route),
        ("observed_result.route", observed_route),
    ):
        if route not in ROUTES:
            print(f"unsupported route in {label}: {route!r}", file=sys.stderr)
            return 2
    sources = observed_result.get("sources", [])
    diagnosis = observed_result.get("diagnosis", {})
    json.dump(
        {
            "expected_route": expected_route,
            "observed_route": observed_route,
            "correct_route": observed_route == expected_route,
            "useful_sources_present": bool(sources)
            and any(
                source.get("title")
                and source.get("url")
                and source.get("useful") is True
                for source in sources
            ),
            "uncertainty_explicit": bool(
                str(observed_result.get("uncertainty", "")).strip()
            ),
            "confident_wrong_diagnosis": diagnosis.get("confidence") == "high"
            and diagnosis.get("supported_by_sources") is False,
        },
        sys.stdout,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
