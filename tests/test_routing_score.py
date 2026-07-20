import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "routing_score.py"
FIXTURES = ROOT / "tests" / "fixtures"


class RoutingScoreContractTests(unittest.TestCase):
    def run_fixture(self, name):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURES / name)],
            check=False,
            capture_output=True,
            text=True,
        )

    def run_payload(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(payload, handle)
            fixture_path = Path(handle.name)
        try:
            return subprocess.run(
                [sys.executable, str(SCRIPT), str(fixture_path)],
                check=False,
                capture_output=True,
                text=True,
            )
        finally:
            fixture_path.unlink(missing_ok=True)

    def test_permission_case_routes_to_manual_admin_product_gap(self):
        completed = self.run_fixture("routing_permission_admin.json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        score = json.loads(completed.stdout)
        self.assertEqual(score["expected_route"], "manual_admin_product_gap")
        self.assertEqual(score["observed_route"], "manual_admin_product_gap")
        self.assertTrue(score["correct_route"])

    def test_complete_source_references_are_observable(self):
        completed = self.run_fixture("routing_permission_admin.json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        score = json.loads(completed.stdout)
        self.assertTrue(score["useful_sources_present"])

    def test_complete_but_irrelevant_source_is_not_scored_as_useful(self):
        completed = self.run_payload(
            {
                "scenario": "An invented result cites a complete but irrelevant source.",
                "expected_route": "insufficient_evidence",
                "observed_result": {
                    "route": "insufficient_evidence",
                    "sources": [
                        {
                            "title": "Invented unrelated guide",
                            "url": "https://example.invalid/unrelated-guide",
                            "useful": False,
                        }
                    ],
                },
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        score = json.loads(completed.stdout)
        self.assertFalse(score["useful_sources_present"])

    def test_explicit_uncertainty_is_observable(self):
        completed = self.run_fixture("routing_permission_admin.json")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        score = json.loads(completed.stdout)
        self.assertTrue(score["uncertainty_explicit"])

    def test_high_confidence_unsupported_diagnosis_is_flagged(self):
        completed = self.run_payload(
            {
                "scenario": "An invented routing result asserts a cause without evidence.",
                "expected_route": "insufficient_evidence",
                "observed_result": {
                    "route": "support_answerable",
                    "diagnosis": {
                        "confidence": "high",
                        "supported_by_sources": False,
                    },
                },
            }
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        score = json.loads(completed.stdout)
        self.assertTrue(score["confident_wrong_diagnosis"])

    def test_route_outside_taxonomy_is_rejected(self):
        completed = self.run_payload(
            {
                "scenario": "An invented result uses an unsupported routing label.",
                "expected_route": "insufficient_evidence",
                "observed_result": {"route": "send_to_someone"},
            }
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("unsupported route", completed.stderr)

    def test_three_sanitized_examples_emit_complete_scorecards(self):
        expected_routes = {
            "routing_permission_admin.json": "manual_admin_product_gap",
            "routing_frozen_workaround.json": "support_answerable",
            "routing_hidden_configuration.json": "store_configuration",
        }

        for fixture_name, expected_route in expected_routes.items():
            with self.subTest(fixture=fixture_name):
                completed = self.run_fixture(fixture_name)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                score = json.loads(completed.stdout)
                self.assertEqual(score["expected_route"], expected_route)
                self.assertTrue(score["correct_route"])
                self.assertTrue(score["useful_sources_present"])
                self.assertTrue(score["uncertainty_explicit"])
                self.assertFalse(score["confident_wrong_diagnosis"])


if __name__ == "__main__":
    unittest.main()
