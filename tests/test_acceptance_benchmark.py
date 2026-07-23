import json
import unittest
from pathlib import Path

from skill.scripts.acceptance_benchmark import run_acceptance


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads(
    (ROOT / "tests/fixtures/acceptance_cases.json").read_text(encoding="utf-8")
)


class AcceptanceBenchmarkTests(unittest.TestCase):
    def test_five_cases_pass_exact_routes_and_traces(self):
        result = run_acceptance(CASES)

        self.assertEqual(result["schemaVersion"], 1)
        self.assertEqual(result["caseCount"], 5)
        self.assertTrue(result["passed"])
        self.assertEqual(
            [row["alias"] for row in result["cases"]],
            [
                "Docs-History",
                "Slack-Notion",
                "Notion-Code",
                "Synthetic-S3",
                "Long-T3",
            ],
        )
        self.assertTrue(all(row["routePassed"] for row in result["cases"]))
        self.assertTrue(all(row["tracePassed"] for row in result["cases"]))

    def test_two_long_t3_cases_ignore_historical_claim_kinds(self):
        result = run_acceptance(CASES)
        long_rows = [
            row for row in result["cases"] if row["targetThreadCount"] >= 60
        ]

        self.assertEqual([row["alias"] for row in long_rows], [
            "Notion-Code",
            "Long-T3",
        ])
        self.assertEqual(long_rows[0]["ignoredHistoricalClaimCount"], 2)
        self.assertEqual(long_rows[1]["ignoredHistoricalClaimCount"], 3)
        self.assertEqual(long_rows[1]["trace"], [
            "help_scout_target",
            "code_context",
        ])

    def test_result_contains_no_evidence_text_or_handle(self):
        serialized = json.dumps(run_acceptance(CASES)).casefold()
        for forbidden in (
            "summary",
            "safe_reference",
            "correlationhandle",
            "opaque-test-handle",
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
