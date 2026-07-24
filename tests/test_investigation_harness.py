import json
from pathlib import Path
import unittest

from skill.scripts.investigation_harness import run_case


ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests" / "fixtures" / "orchestration_cases.json").read_text(encoding="utf-8"))


class InvestigationHarnessTests(unittest.TestCase):
    @staticmethod
    def recent_slack_evidence():
        return {
            "id": "slack-workaround",
            "claim_key": "recent_team_context",
            "claim_value": "temporary_retry_after_connection_refresh",
            "summary": "A recent bounded Slack result describes a temporary retry after refreshing the provider connection.",
            "source_type": "slack",
            "safe_reference": "synthetic-slack-workaround",
            "source_date": "2026-07-20",
            "retrieved_at": "2026-07-22T15:00:00Z",
            "authority": "supporting",
            "claim_supported": "A recent team workaround was discussed.",
            "coverage": "Message-only Slack search, 30-day window, one of at most ten results.",
        }

    @staticmethod
    def code_retry_evidence():
        commit = "1111111111111111111111111111111111111111"
        return [
            {
                "id": "code-submission-handler",
                "claim_key": "implementation_behavior",
                "claim_value": "explicit_rejections_are_not_automatically_retried",
                "summary": "The synthetic submission handler records an explicit provider rejection as a failed submission and does not enqueue an automatic retry.",
                "source_type": "code_context",
                "safe_reference": f"synthetic/orderdesk-v3:src/Fulfillment/SubmissionHandler.php:120-146@{commit}",
                "source_date": "2026-07-21",
                "retrieved_at": "2026-07-22T16:00:00Z",
                "authority": "supporting",
                "claim_supported": "Explicit provider rejections enter the failed-submission path.",
                "coverage": "Approved default-branch snapshot; one bounded passage from the submission handler.",
            },
            {
                "id": "code-retry-selector",
                "claim_key": "implementation_behavior",
                "claim_value": "explicit_rejections_are_not_automatically_retried",
                "summary": "The synthetic retry selector includes transient transport failures but excludes explicit provider rejections.",
                "source_type": "code_context",
                "safe_reference": f"synthetic/orderdesk-v3:src/Jobs/RetryFailedSubmission.php:44-68@{commit}",
                "source_date": "2026-07-21",
                "retrieved_at": "2026-07-22T16:00:00Z",
                "authority": "supporting",
                "claim_supported": "Only transient transport failures are selected for automatic retry.",
                "coverage": "Approved default-branch snapshot; one bounded passage from the retry selector.",
            },
        ]

    @staticmethod
    def notion_code_mismatch_evidence():
        notion = {
            "id": "notion-retry-policy",
            "claim_key": "provider_rejection_retry_policy",
            "claim_value": "explicit_rejections_should_retry_once",
            "summary": "The current Support process says an explicit provider rejection should receive one bounded retry after refreshing the provider connection.",
            "source_type": "notion",
            "safe_reference": "synthetic-notion-retry-policy",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T17:00:00Z",
            "authority": "authoritative",
            "claim_supported": "The intended process requires one bounded retry for explicit provider rejections.",
            "coverage": "Approved Support-profile page; first 20 text blocks; current process section.",
        }
        code = [
            dict(item, claim_key="provider_rejection_retry_policy")
            for item in InvestigationHarnessTests.code_retry_evidence()
        ]
        return notion, code

    @staticmethod
    def slack_notion_mismatch_evidence():
        slack = {
            "id": "slack-recent-workaround",
            "claim_key": "provider_connection_retry_process",
            "claim_value": "refresh_then_retry_immediately",
            "summary": "A recent Slack thread recommends refreshing the provider connection and retrying immediately.",
            "source_type": "slack",
            "safe_reference": "synthetic-slack-recent-workaround",
            "source_date": "2026-07-22",
            "retrieved_at": "2026-07-22T18:00:00Z",
            "authority": "supporting",
            "claim_supported": "A recent informal workaround recommends an immediate refresh and retry.",
            "coverage": "Message-only Slack search, 14-day window, one of at most ten results.",
        }
        notion = {
            "id": "notion-current-retry-process",
            "claim_key": "provider_connection_retry_process",
            "claim_value": "verify_connection_then_retry_once",
            "summary": "The current Support process requires verifying connection state before one bounded retry.",
            "source_type": "notion",
            "safe_reference": "synthetic-notion-current-retry-process",
            "source_date": "2026-07-21",
            "retrieved_at": "2026-07-22T18:00:00Z",
            "authority": "authoritative",
            "claim_supported": "The intended process requires connection verification before one bounded retry.",
            "coverage": "Approved Support-profile page; owner-backed current process section.",
        }
        return slack, notion

    def test_synthetic_cases_have_exact_ordered_calls_and_no_private_transit(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                result = run_case(case)
                self.assertEqual([item["source"] for item in result["callTrace"]], case["expectedTrace"])
                self.assertEqual(result["plan"]["status"], case["expectedStatus"])
                self.assertEqual(result["route"], case["expectedRoute"])
                self.assertEqual(set(result["sourceCoverage"]), {"help_scout_target", "helpscout_history", "public_kb", "slack", "notion", "code_context", "s3_logs"})
                self.assertEqual(result["claims"], result["plan"]["claimDispositions"])
                if result["plan"]["status"] != "stopped":
                    self.assertIn("**Reply Boundary**", result["brief"])
                    for record in result["evidence"]:
                        self.assertEqual(set(record), {"id", "claim_key", "claim_value", "summary", "source_type", "safe_reference", "source_date", "retrieved_at", "authority", "claim_supported", "coverage"})
                self.assertNotIn("opaque-test-handle", json.dumps(result))
                for forbidden in ("rawtickettext", "correlationhandle", "opaque-test-handle", "credential"):
                    self.assertNotIn(forbidden, json.dumps(result).casefold())

    def test_brief_projects_attachment_coverage_without_attachment_artifacts(self):
        case = {
            "name": "attachment-coverage",
            "claims": ["documented_behavior"],
            "targetAttachmentCoverage": "partial",
            "decisiveEvidenceAttachmentOnly": False,
            "responses": {"public_kb": [{"outcome": "resolved"}]},
        }
        result = run_case(case)
        self.assertIn("Help Scout attachments: partial", result["brief"])
        self.assertIn("Attachment extraction: macOS native PDF text/OCR and layout", result["brief"])
        self.assertIn("Material ambiguity: attachment_understanding_incomplete", result["brief"])
        for forbidden in ("ocr dump", "attachment.pdf", "https://", "sha256", "/tmp/", "bounding box"):
            self.assertNotIn(forbidden, result["brief"].casefold())

    def test_decisive_incomplete_attachment_coverage_asks_one_focused_human_question(self):
        for coverage, reason in (
            ("partial", "attachment_understanding_incomplete"),
            ("blocked", "attachment_evidence_blocked"),
            ("unavailable", "attachment_evidence_unavailable"),
            ("none", "attachment_evidence_unavailable"),
        ):
            with self.subTest(coverage=coverage):
                result = run_case({
                    "name": f"decisive-{coverage}",
                    "claims": ["documented_behavior"],
                    "targetAttachmentCoverage": coverage,
                    "decisiveEvidenceAttachmentOnly": True,
                    "responses": {},
                })
                self.assertEqual(result["plan"]["status"], "abstain")
                self.assertEqual(result["plan"]["targetAttachmentDisposition"], {
                    "status": "blocked" if coverage == "blocked" else "unavailable",
                    "reason": reason,
                })
                self.assertEqual(
                    result["nextStep"],
                    "Ask a human reviewer: what visible error or event -> filters -> actions step does the attachment show?",
                )
                self.assertIn(f"Material ambiguity: {reason}", result["brief"])
                self.assertNotIn("Obtain the smallest missing governed fact", result["brief"])

    def test_s3_logs_callback_gets_a_private_handle_that_never_enters_the_result(self):
        calls = []

        def s3_logs(step, handle):
            calls.append((step, handle))
            return {"outcome": "resolved"}

        case = next(item for item in CASES if item["name"] == "target_s3_runtime")
        result = run_case(case, {"s3_logs": s3_logs})

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0]["logLookupKind"], "order_import")
        self.assertEqual(calls[0][1], "opaque-test-handle")
        self.assertTrue(result["callTrace"][-1]["handleTransit"])
        serialized = json.dumps(result)
        self.assertNotIn("opaque-test-handle", serialized)
        self.assertNotIn("correlationHandle", serialized)

    def test_unavailable_s3_logs_never_runs_a_callback_or_transits_a_handle(self):
        calls = []

        def s3_logs(step, handle):
            calls.append((step, handle))
            return {"outcome": "resolved"}

        case = next(item for item in CASES if item["name"] == "target_s3_unavailable_and_code")
        result = run_case(case, {"s3_logs": s3_logs})

        self.assertEqual(calls, [])
        self.assertFalse(any(item["handleTransit"] for item in result["callTrace"]))
        self.assertEqual(
            result["sourceCoverage"]["s3_logs"],
            {"status": "unavailable", "reason": "s3_log_lookup_unavailable"},
        )

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
        self.assertEqual(missing_schema["plan"]["sourceCoverage"]["s3_logs"], {"status": "unavailable", "reason": "log_kind_unavailable"})
        self.assertEqual(missing_schema["nextStep"], "Hand off to the S3 Logs contract owner")
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

    def test_rich_slack_evidence_survives_into_a_calibrated_nonrepetitive_brief(self):
        case = {
            "name": "bakeoff_01_recent_import_workaround",
            "claims": ["recent_team_context"],
            "responses": {
                "slack": [
                    {
                        "outcome": "resolved",
                        "evidence": [self.recent_slack_evidence()],
                    }
                ]
            },
        }
        result = run_case(case)

        self.assertEqual([item["source"] for item in result["callTrace"]], ["help_scout_target", "slack"])
        self.assertEqual(result["claims"][0]["source"], "slack")
        self.assertEqual(result["evidence"], [self.recent_slack_evidence()])
        self.assertEqual(result["route"], "Insufficient evidence — abstain")
        self.assertIn("temporary retry after refreshing the provider connection", result["brief"])
        self.assertIn("2026-07-20", result["brief"])
        self.assertIn("30-day window", result["brief"])
        self.assertIn("supporting", result["brief"])
        self.assertIn("does not establish policy, deployment, runtime cause, or a confirmed fix", result["brief"])
        self.assertIn("public_kb: skipped (not_needed_for_named_claim)", result["brief"])
        coverage_dump = "help_scout_target: checked (target_facts_received); helpscout_history: skipped"
        self.assertEqual(result["brief"].count(coverage_dump), 0)

    def test_nonresolved_callbacks_cannot_smuggle_evidence(self):
        case = {"name": "envelope", "claims": ["recent_team_context"], "responses": {}}
        with self.assertRaises(ValueError):
            run_case(
                case,
                {
                    "slack": lambda step, handle: {
                        "outcome": "unresolved",
                        "evidence": [self.recent_slack_evidence()],
                    }
                },
            )

    def test_code_only_evidence_is_synthesized_but_cannot_claim_deployment_or_a_change(self):
        case = {
            "name": "bakeoff_02_code_retry_behavior",
            "claims": ["implementation_behavior"],
            "responses": {
                "code_context": [
                    {
                        "outcome": "resolved",
                        "evidence": self.code_retry_evidence(),
                    }
                ]
            },
        }
        result = run_case(case)

        self.assertEqual([item["source"] for item in result["callTrace"]], ["help_scout_target", "code_context"])
        self.assertEqual(result["claims"][0]["source"], "code_context")
        self.assertEqual(result["route"], "Insufficient evidence — abstain")
        self.assertEqual(
            result["nextStep"],
            "Ask Engineering to confirm whether the cited behavior is intentional and whether the cited commit is deployed for the affected path",
        )
        self.assertIn(
            "Across the cited commit-pinned passages, the implementation evidence consistently supports that explicit rejections are not automatically retried.",
            result["brief"],
        )
        self.assertIn(
            "does not establish deployment, runtime cause, design intent, or that a code change is warranted",
            result["brief"],
        )
        self.assertIn(
            "The deployed commit, runtime path, intended behavior, and whether a change is desirable remain unknown.",
            result["brief"],
        )
        for record in self.code_retry_evidence():
            self.assertIn(record["safe_reference"], result["brief"])

    def test_code_and_slack_supporting_evidence_cannot_route_to_a_code_change(self):
        case = {
            "name": "bakeoff_code_and_slack_supporting",
            "claims": ["implementation_behavior", "recent_team_context"],
            "responses": {
                "code_context": [
                    {
                        "outcome": "resolved",
                        "evidence": self.code_retry_evidence(),
                    }
                ],
                "slack": [
                    {
                        "outcome": "resolved",
                        "evidence": [self.recent_slack_evidence()],
                    }
                ],
            },
        }

        result = run_case(case)

        self.assertEqual(
            [item["source"] for item in result["callTrace"]],
            ["help_scout_target", "code_context", "slack"],
        )
        self.assertEqual(result["route"], "Insufficient evidence — abstain")
        self.assertIn("authoritative process source or runtime evidence", result["nextStep"])

    def test_notion_code_mismatch_renders_a_structured_finding_and_engineering_handoff(self):
        notion, code = self.notion_code_mismatch_evidence()
        case = {
            "name": "bakeoff_03_intended_process_vs_code",
            "claims": ["intended_process", "implementation_behavior"],
            "responses": {
                "notion": [{"outcome": "resolved", "evidence": [notion]}],
                "code_context": [{"outcome": "resolved", "evidence": code}],
            },
        }
        result = run_case(case)

        self.assertEqual(
            [item["source"] for item in result["callTrace"]],
            ["help_scout_target", "notion", "code_context"],
        )
        self.assertEqual(result["findings"][0]["findingType"], "intended_vs_implemented")
        self.assertEqual(result["findings"][0]["relationship"], "mismatch")
        self.assertEqual(result["route"], "Likely code change")
        self.assertEqual(
            result["nextStep"],
            "Ask Engineering to verify the deployed commit and reconcile the cited implementation with the authoritative intended process",
        )
        self.assertIn(
            "At the cited commit, implementation appears inconsistent with the intended process.",
            result["brief"],
        )
        self.assertIn(
            "Notion establishes intended process; code describes implementation at the cited commit. Neither source establishes runtime behavior or deployment.",
            result["brief"],
        )
        self.assertIn(
            "The deployed commit, runtime path, and correct remediation remain unknown.",
            result["brief"],
        )
        self.assertNotIn("explicit_authority_then_recency", result["brief"])

    def test_slack_notion_mismatch_preserves_roles_and_routes_the_workaround_for_review(self):
        slack, notion = self.slack_notion_mismatch_evidence()
        case = {
            "name": "bakeoff_04_informal_workaround_vs_process",
            "claims": ["recent_team_context", "intended_process"],
            "responses": {
                "slack": [{"outcome": "resolved", "evidence": [slack]}],
                "notion": [{"outcome": "resolved", "evidence": [notion]}],
            },
        }
        result = run_case(case)

        self.assertEqual(
            [item["source"] for item in result["callTrace"]],
            ["help_scout_target", "slack", "notion"],
        )
        self.assertEqual(result["findings"][0]["findingType"], "informal_vs_intended")
        self.assertEqual(result["findings"][0]["relationship"], "mismatch")
        self.assertEqual(result["route"], "Store configuration / Rule Builder")
        self.assertEqual(
            result["nextStep"],
            "Follow the authoritative process and send the informal workaround to the process owner for review",
        )
        self.assertIn(
            "Slack describes a recent informal workaround; Notion establishes the intended process.",
            result["brief"],
        )
        self.assertIn(
            "The informal workaround differs from the authoritative process.",
            result["brief"],
        )
        self.assertIn(
            "The runtime outcome and whether the workaround is approved remain unknown.",
            result["brief"],
        )
        self.assertNotIn("explicit_authority_then_recency", result["brief"])
