import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "skill" / "scripts" / "investigation_plan.py"
FIXTURES = ROOT / "tests" / "fixtures" / "investigation_cases.json"


def load_module():
    spec = importlib.util.spec_from_file_location("investigation_plan", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class InvestigationPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        cls.cases = json.loads(FIXTURES.read_text(encoding="utf-8"))

    def case(self, name):
        return next(case for case in self.cases if case["name"] == name)

    def test_fixture_selects_expected_initial_sources(self):
        for case in self.cases:
            with self.subTest(case=case["name"]):
                result = self.module.plan_investigation(case["input"])
                self.assertEqual([step["source"] for step in result["steps"]], case["expectedSources"])
                self.assertEqual(result["status"], case["expectedStatus"])
                self.assertEqual(set(result["sourceCoverage"]), set(self.module.SOURCE_NAMES))

    def test_full_context_can_select_private_source(self):
        payload = self.case("full_context_slack")["input"]
        self.assertEqual(payload["sanitizedQuestion"]["observedBehavior"], "orders_delayed")
        result = self.module.plan_investigation(payload)
        self.assertEqual([step["source"] for step in result["steps"]], ["slack"])

    def test_build_claims_uses_full_context_signals_without_missing_code(self):
        payload = self.case("full_context_slack")["input"]
        facts = [
            {"key": "investigation_signal", "value": "recent_team_context"},
            {"key": "investigation_signal", "value": "implementation_behavior"},
            {"key": "investigation_signal", "value": "runtime_event"},
            {"key": "log_lookup_kind", "value": "order_import"},
        ]
        claims = self.module.build_claims(payload["sanitizedQuestion"], facts, [])
        self.assertEqual([claim["kind"] for claim in claims], ["implementation_behavior", "recent_team_context", "runtime_event"])
        result = self.module.plan_investigation({**payload, "safeFacts": facts, "missingEvidence": [], "correlationAvailable": True, "enabledLogKinds": ["order_import"]})
        self.assertEqual([step["source"] for step in result["steps"]], ["code_context", "slack", "aws_logs"])

    def test_closed_target_context_derives_claims_without_connector_only_signals(self):
        payload = self.case("full_context_slack")["input"]
        result = self.module.plan_investigation({**payload, "missingEvidence": [], "safeFacts": [], "correlationAvailable": True, "enabledLogKinds": ["order_import"]})
        self.assertEqual([step["source"] for step in result["steps"]], ["code_context", "slack", "aws_logs"])
        unknown = self.module.plan_investigation({**payload, "missingEvidence": [], "safeFacts": [], "sanitizedQuestion": {**payload["sanitizedQuestion"], "observedBehavior": "unmapped"}, "correlationAvailable": True, "enabledLogKinds": ["order_import"]})
        self.assertEqual(unknown["steps"], [])

    def test_history_is_optional_and_requires_prior_case_claim(self):
        public = self.module.plan_investigation(self.case("public_only")["input"])
        self.assertEqual(public["sourceCoverage"]["help_scout_target"]["status"], "checked")
        self.assertEqual(public["sourceCoverage"]["helpscout_history"], {"status": "skipped", "reason": "not_needed_for_named_claim"})
        history = self.module.plan_investigation(self.case("history_only")["input"])
        self.assertEqual(history["sourceCoverage"]["helpscout_history"]["status"], "planned")

    def test_unresolved_result_replans_then_exhausts_authoritative_route(self):
        merged = self.module.merge_source_result(self.case("full_context_slack")["input"], {"claimId": "c1", "source": "slack", "outcome": "unresolved"})
        self.assertEqual(merged["steps"], [])
        self.assertEqual(merged["status"], "abstain")
        self.assertEqual(merged["sourceCoverage"]["slack"]["status"], "checked")

    def test_unavailable_result_abstains_and_merge_rejects_wrong_step(self):
        payload = self.case("full_context_slack")["input"]
        merged = self.module.merge_source_result(payload, {"claimId": "c1", "source": "slack", "outcome": "unavailable"})
        self.assertEqual(merged["status"], "abstain")
        self.assertEqual(merged["sourceCoverage"]["slack"]["status"], "unavailable")
        with self.assertRaisesRegex(ValueError, "currently planned step"):
            self.module.merge_source_result(payload, {"claimId": "c1", "source": "notion", "outcome": "resolved"})

    def test_stopped_result_promotes_every_disposition_to_stopped(self):
        merged = self.module.merge_source_result(self.case("full_context_slack")["input"], {"claimId": "c1", "source": "slack", "outcome": "stopped", "safeError": "masking_failed"})
        self.assertEqual(merged["status"], "stopped")
        self.assertTrue(all(item["status"] == "stopped" for item in merged["sourceCoverage"].values()))
        self.assertTrue(all(item["status"] == "stopped" for item in merged["claimDispositions"]))

    def test_source_coverage_is_independent_of_claim_order(self):
        payload = self.case("mixed_smallest_set")["input"]
        forward = self.module.plan_investigation(payload)
        reverse = self.module.plan_investigation({**payload, "missingEvidence": list(reversed(payload["missingEvidence"]))})
        self.assertEqual(forward["sourceCoverage"], reverse["sourceCoverage"])

    def test_coverage_precedence_prevents_planned_from_overwriting_checked_or_unavailable(self):
        payload = self.case("full_context_slack")["input"]
        checked_claim = {**payload["missingEvidence"][0], "id": "a", "attempts": [{"source": "slack", "outcome": "unresolved"}]}
        planned_claim = {**payload["missingEvidence"][0], "id": "b", "attempts": []}
        checked = self.module.plan_investigation({**payload, "missingEvidence": [checked_claim, planned_claim]})
        self.assertEqual(checked["sourceCoverage"]["slack"]["status"], "checked")
        unavailable_claim = {**checked_claim, "attempts": [{"source": "slack", "outcome": "unavailable"}]}
        unavailable = self.module.plan_investigation({**payload, "missingEvidence": [unavailable_claim, planned_claim]})
        self.assertEqual(unavailable["sourceCoverage"]["slack"]["status"], "unavailable")

    def test_runtime_requires_correlation_and_enabled_contract(self):
        payload = self.case("aws_runtime")["input"]
        self.assertEqual(self.module.plan_investigation({**payload, "correlationAvailable": False})["claimDispositions"][0]["reason"], "correlation_unavailable")
        self.assertEqual(self.module.plan_investigation({**payload, "enabledLogKinds": []})["claimDispositions"][0]["reason"], "log_contract_unavailable")

    def test_blocked_and_hard_stop_return_complete_stopped_dispositions(self):
        payload = self.case("mixed_smallest_set")["input"]
        for stopped in ({**payload, "targetContextState": "blocked"}, {**payload, "hardStopError": "masking_failed"}):
            result = self.module.plan_investigation(stopped)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(set(result["sourceCoverage"]), set(self.module.SOURCE_NAMES))
            self.assertTrue(all(item["status"] == "stopped" for item in result["sourceCoverage"].values()))

    def test_invalid_ticket_and_private_fields_fail_closed(self):
        payload = self.case("public_only")["input"]
        for invalid in (0, -1, "12345", True):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                self.module.plan_investigation({**payload, "ticketNumber": invalid})
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            self.module.plan_investigation({**payload, "rawTicketText": "synthetic"})
