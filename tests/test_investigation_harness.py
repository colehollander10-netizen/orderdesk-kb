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
                self.assertEqual(set(result["sourceCoverage"]), {"help_scout_target", "helpscout_history", "public_kb", "slack", "notion", "code_context", "aws_logs"})
                self.assertEqual(result["claims"], result["plan"]["claimDispositions"])
                if result["plan"]["status"] != "stopped":
                    self.assertIn("**Reply Boundary**", result["brief"])
                    for record in result["evidence"]:
                        self.assertEqual(set(record), {"id", "claim_key", "claim_value", "summary", "source_type", "safe_reference", "source_date", "retrieved_at", "authority", "claim_supported", "coverage"})
                self.assertNotIn("opaque-test-handle", json.dumps(result))
                for forbidden in ("rawtickettext", "correlationhandle", "opaque-test-handle", "credential"):
                    self.assertNotIn(forbidden, json.dumps(result).casefold())

    def test_only_aws_receives_handle_transit(self):
        case = next(item for item in CASES if item["name"] == "target_aws_and_code")
        trace = run_case(case)["callTrace"]
        self.assertEqual([item["source"] for item in trace if item["handleTransit"]], ["aws_logs"])

    def test_aws_gets_private_object_once_and_second_runtime_claim_is_skipped(self):
        received = []
        def aws(step, handle):
            received.append(handle)
            return {"outcome": "resolved"}
        case = {"name": "two_runtime", "claims": ["runtime_event", "runtime_event"], "correlationAvailable": True, "responses": {}}
        result = run_case(case, {"aws_logs": aws})
        self.assertEqual(len(received), 1)
        self.assertIsNotNone(received[0])
        self.assertEqual([item["source"] for item in result["callTrace"] if item["handleTransit"]], ["aws_logs"])
        self.assertIn("correlation_unavailable", [item["reason"] for item in result["claims"]])

    def test_conflicts_preserve_authority_and_freshness(self):
        for name in ("slack_notion_conflict", "history_current_policy_conflict"):
            result = run_case(next(item for item in CASES if item["name"] == name))
            conflict = result["evidenceResult"]["conflicts"][0]
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(conflict["preference_status"], "preferred_for_review")
            self.assertEqual(conflict["preferred_source_id"], "notion-evidence")

    def test_brief_renderer_contains_required_safe_sections_and_boundary(self):
        result = run_case(next(item for item in CASES if item["name"] == "target_kb"))
        brief = result["brief"]
        for section in ("**Investigation Plan**", "**What I Checked**", "**Coverage and Freshness**", "**Evidence Status**", "**Source Ledger**", "**Conflicts**", "**Unknowns**", "**Public KB Links**", "**Suggested Next Step**", "**Reply Boundary**"):
            self.assertIn(section, brief)
        self.assertIn("Customer-reply drafting is outside `/orderdesk`; no customer-facing wording was produced.", brief)
        self.assertIn("synthetic-public_kb", brief)
        self.assertNotIn("correlationHandle", brief)
        self.assertNotIn("rawTicketText", brief)

    def test_missing_schema_and_hard_stop_never_continue_private_calls_or_render(self):
        missing_schema = run_case(next(item for item in CASES if item["name"] == "runtime_without_schema"))
        self.assertEqual(missing_schema["plan"]["sourceCoverage"]["aws_logs"], {"status": "skipped", "reason": "log_contract_unavailable"})
        self.assertEqual(missing_schema["nextStep"], "Hand off to the AWS log-contract owner")
        stopped = run_case({"name": "masking_hard_stop", "claims": ["recent_team_context"], "responses": {"slack": [{"outcome": "stopped", "safeError": "masking_failed"}]}})
        self.assertEqual(stopped["plan"]["status"], "stopped")
        self.assertTrue(all(item["status"] == "stopped" for item in stopped["sourceCoverage"].values()))
        self.assertNotIn("brief", stopped)

    def test_hard_stop_erases_earlier_evidence_and_never_runs_later_callback(self):
        calls = []
        def resolved(step, handle):
            calls.append(step["source"])
            return {"outcome": "resolved"}
        def stopped(step, handle):
            calls.append(step["source"])
            return {"outcome": "stopped", "safeError": "masking_failed"}
        def forbidden(step, handle):
            raise AssertionError("later private callback must not run")
        result = run_case(
            {"name": "hard_stop_after_evidence", "claims": ["documented_behavior", "recent_team_context", "intended_process"], "responses": {}},
            {"public_kb": resolved, "slack": stopped, "notion": forbidden},
        )
        self.assertEqual(calls, ["public_kb", "slack"])
        self.assertEqual(result["plan"]["status"], "stopped")
        self.assertTrue(all(item["status"] == "stopped" for item in result["sourceCoverage"].values()))
        self.assertNotIn("evidence", result)
        self.assertNotIn("evidenceResult", result)
        self.assertNotIn("route", result)
        self.assertNotIn("nextStep", result)
        self.assertNotIn("brief", result)

    def test_callback_envelopes_are_closed_and_stops_require_closed_error(self):
        case = {"name": "envelope", "claims": ["recent_team_context"], "responses": {}}
        for envelope in ({"outcome": "stopped", "safeError": "arbitrary"}, {"outcome": "resolved", "extra": True}, "stopped:masking_failed"):
            with self.assertRaises(ValueError):
                run_case(case, {"slack": lambda step, handle, value=envelope: value})
