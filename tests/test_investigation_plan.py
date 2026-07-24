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

    def test_attachment_coverage_is_closed_and_decisive_attachment_only_claims_require_complete_coverage(self):
        payload = self.case("public_only")["input"]
        partial = self.module.plan_investigation({
            **payload,
            "targetAttachmentCoverage": "partial",
            "decisiveEvidenceAttachmentOnly": True,
        })
        self.assertEqual(partial["status"], "abstain")
        self.assertEqual(
            partial["targetAttachmentDisposition"],
            {"status": "unavailable", "reason": "attachment_understanding_incomplete"},
        )
        complete = self.module.plan_investigation({
            **payload,
            "targetAttachmentCoverage": "complete",
            "decisiveEvidenceAttachmentOnly": True,
        })
        self.assertEqual(complete["status"], "running")
        self.assertEqual(
            complete["targetAttachmentDisposition"],
            {"status": "complete", "reason": "attachment_evidence_complete"},
        )

    def test_attachment_coverage_blocks_only_attachment_dependent_claims_and_rejects_contract_drift(self):
        payload = self.case("public_only")["input"]
        for coverage, reason in (
            ("blocked", "attachment_evidence_blocked"),
            ("unavailable", "attachment_evidence_unavailable"),
        ):
            with self.subTest(coverage=coverage):
                result = self.module.plan_investigation({
                    **payload,
                    "targetAttachmentCoverage": coverage,
                    "decisiveEvidenceAttachmentOnly": True,
                })
                self.assertEqual(result["status"], "abstain")
                self.assertEqual(result["targetAttachmentDisposition"]["reason"], reason)
        text_supported = self.module.plan_investigation({
            **payload,
            "targetAttachmentCoverage": "none",
            "decisiveEvidenceAttachmentOnly": False,
        })
        self.assertEqual(text_supported["status"], "running")
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            self.module.plan_investigation({key: value for key, value in payload.items() if key != "targetAttachmentCoverage"})
        with self.assertRaisesRegex(ValueError, "invalid"):
            self.module.plan_investigation({**payload, "targetAttachmentCoverage": "invented"})

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

    def test_build_claims_uses_closed_missing_evidence_codes_without_connector_signals(self):
        payload = self.case("full_context_slack")["input"]
        facts = [{"key": "missing_evidence_code", "value": "runtime_order_import"}]
        claims = self.module.build_claims(payload["sanitizedQuestion"], facts, [])
        self.assertEqual([claim["kind"] for claim in claims], ["implementation_behavior", "recent_team_context", "runtime_event"])
        with self.assertRaisesRegex(ValueError, "undeclared"):
            self.module.plan_investigation({**payload, "safeFacts": [{"key": "investigation_signal", "value": "recent_team_context"}]})

    def test_closed_target_context_derives_claims_without_connector_only_signals(self):
        payload = self.case("full_context_slack")["input"]
        eligibility = {
            "trustedCorrelation": True,
            "boundedTimeWindow": True,
            "materiallyChangesRoute": True,
            "lookupKinds": ["order_import"],
        }
        result = self.module.plan_investigation({**payload, "missingEvidence": [], "safeFacts": [], "s3LogEligibility": eligibility})
        self.assertEqual([step["source"] for step in result["steps"]], ["code_context", "slack", "s3_logs"])
        self.assertEqual(
            result["sourceCoverage"]["s3_logs"],
            {"status": "planned", "reason": "next_eligible_source"},
        )
        unknown = self.module.plan_investigation({**payload, "missingEvidence": [], "safeFacts": [], "sanitizedQuestion": {**payload["sanitizedQuestion"], "observedBehavior": "unmapped"}, "s3LogEligibility": eligibility})
        self.assertEqual(unknown["steps"], [])
        expected_unknown = self.module.plan_investigation({**payload, "missingEvidence": [], "safeFacts": [], "sanitizedQuestion": {**payload["sanitizedQuestion"], "expectedBehavior": "unmapped"}, "s3LogEligibility": eligibility})
        self.assertEqual(expected_unknown["steps"], [])

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

    def test_resolved_claim_retains_the_source_that_resolved_it(self):
        payload = self.case("full_context_slack")["input"]
        merged = self.module.merge_source_result(
            payload,
            {"claimId": "c1", "source": "slack", "outcome": "resolved"},
        )
        self.assertEqual(
            merged["claimDispositions"][0],
            {
                "claimId": "c1",
                "status": "resolved",
                "source": "slack",
                "reason": "claim_resolved",
                "skippedSources": [],
            },
        )

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

    def test_runtime_claim_selects_s3_log_lookup_only_after_all_closed_gates_pass(self):
        payload = self.case("s3_runtime")["input"]
        result = self.module.plan_investigation(payload)
        self.assertEqual(
            result["steps"],
            [{
                "claimId": "c1",
                "claimKind": "runtime_event",
                "source": "s3_logs",
                "logLookupKind": "order_import",
            }],
        )
        self.assertEqual(
            result["sourceCoverage"]["s3_logs"],
            {"status": "planned", "reason": "next_eligible_source"},
        )

    def test_runtime_claim_fails_each_closed_eligibility_gate_with_an_exact_reason(self):
        payload = self.case("s3_runtime")["input"]
        cases = (
            ({"capabilities": {**payload["capabilities"], "s3_logs": False}}, "s3_log_lookup_unavailable", "unavailable"),
            ({"s3LogEligibility": {**payload["s3LogEligibility"], "trustedCorrelation": False}}, "correlation_unavailable", "unavailable"),
            ({"s3LogEligibility": {**payload["s3LogEligibility"], "boundedTimeWindow": False}}, "time_window_unavailable", "unavailable"),
            ({"s3LogEligibility": {**payload["s3LogEligibility"], "materiallyChangesRoute": False}}, "log_not_material", "skipped"),
            ({"s3LogEligibility": {**payload["s3LogEligibility"], "lookupKinds": []}}, "log_kind_unavailable", "unavailable"),
        )
        for override, reason, coverage_status in cases:
            with self.subTest(reason=reason):
                result = self.module.plan_investigation({**payload, **override})
                self.assertEqual(result["steps"], [])
                self.assertEqual(result["claimDispositions"][0]["reason"], reason)
                self.assertEqual(
                    result["sourceCoverage"]["s3_logs"],
                    {"status": coverage_status, "reason": reason},
                )

    def test_blocked_and_hard_stop_return_complete_stopped_dispositions(self):
        payload = self.case("mixed_smallest_set")["input"]
        for stopped in ({**payload, "targetContextState": "blocked"}, {**payload, "hardStopError": "masking_failed"}):
            result = self.module.plan_investigation(stopped)
            self.assertEqual(result["status"], "stopped")
            self.assertEqual(set(result["sourceCoverage"]), set(self.module.SOURCE_NAMES))
            self.assertTrue(all(item["status"] == "stopped" for item in result["sourceCoverage"].values()))

    def test_runtime_contract_mismatch_is_a_hard_stop(self):
        payload = self.case("public_only")["input"]
        self.assertIn("runtime_contract_mismatch", self.module.STOP_ERRORS)

        result = self.module.plan_investigation(
            {**payload, "hardStopError": "runtime_contract_mismatch"}
        )

        self.assertEqual(result["status"], "stopped")
        self.assertTrue(
            all(item["status"] == "stopped" for item in result["sourceCoverage"].values())
        )

    def test_invalid_ticket_and_private_fields_fail_closed(self):
        payload = self.case("public_only")["input"]
        for invalid in (0, -1, "12345", True):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                self.module.plan_investigation({**payload, "ticketNumber": invalid})
        with self.assertRaisesRegex(ValueError, "unexpected fields"):
            self.module.plan_investigation({**payload, "rawTicketText": "synthetic"})
