import json
from pathlib import Path
import unittest

from skill.scripts.investigation_harness import run_case


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "fixtures" / "orchestration_cases.json").read_text(encoding="utf-8"))


class InvestigationHarnessTests(unittest.TestCase):
    def test_synthetic_cases_have_exact_ordered_calls_and_no_private_transit(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                result = run_case(case)
                self.assertEqual([item["source"] for item in result["callTrace"]], case["expectedTrace"])
                self.assertEqual(result["plan"]["status"], case["expectedStatus"])
                self.assertEqual(result["route"], case["expectedRoute"])
                self.assertNotIn("opaque-test-handle", json.dumps(result))
                self.assertNotIn("customer", json.dumps(result).casefold())

    def test_only_aws_receives_handle_transit(self):
        case = next(item for item in CASES if item["name"] == "target_aws_and_code")
        trace = run_case(case)["callTrace"]
        self.assertEqual([item["source"] for item in trace if item["handleTransit"]], ["aws_logs"])

    def test_conflicts_preserve_authority_and_freshness(self):
        for name in ("slack_notion_conflict", "history_current_policy_conflict"):
            result = run_case(next(item for item in CASES if item["name"] == name))
            conflict = result["evidenceResult"]["conflicts"][0]
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(conflict["preference_status"], "preferred_for_review")
            self.assertEqual(conflict["preferred_source_id"], "notion-evidence")

    def test_missing_schema_and_hard_stop_never_continue_private_calls_or_render(self):
        missing_schema = run_case(next(item for item in CASES if item["name"] == "runtime_without_schema"))
        self.assertEqual(missing_schema["plan"]["sourceCoverage"]["aws_logs"], {"status": "skipped", "reason": "log_contract_unavailable"})
        self.assertEqual(missing_schema["nextStep"], "Hand off to the AWS log-contract owner")
        stopped = run_case(next(item for item in CASES if item["name"] == "masking_hard_stop"))
        self.assertEqual(stopped["plan"]["status"], "stopped")
        self.assertTrue(all(item["status"] == "stopped" for item in stopped["sourceCoverage"].values()))
        self.assertIsNone(stopped["brief"])
