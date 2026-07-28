import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GOVERNED_CONTEXT = ROOT / "skill" / "references" / "governed-context.md"
INTERNAL_BRIEF = ROOT / "skill" / "references" / "internal-brief.md"
PUBLIC_KB = ROOT / "skill" / "references" / "public-kb.md"
HELP_SCOUT = ROOT / "skill" / "references" / "help-scout.md"
SKILL = ROOT / "skill" / "SKILL.md"


class MultiSourceBriefContractTests(unittest.TestCase):
    def test_slack_search_is_claim_routed_and_bounded(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text().split())
        for phrase in ("`slack_search`", "`recent_team_context`", "safe product, provider, behavior, workflow, rule, or error-family terms", "files and attachments remain withheld", "no match within the bounded search", "not a comprehensive Slack absence", "Slack-only supporting evidence does not establish policy, deployment, runtime cause, or a confirmed fix"):
            self.assertIn(phrase, governed)

    def test_code_context_and_s3_logs_are_governed_without_claiming_live_readiness(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text().split())
        for phrase in ("`code_context`", "repository, path, line, and immutable commit", "approved default-branch snapshot", "does not prove deployment", "Code-only supporting evidence does not establish deployment, runtime cause, design intent, or that a code change is warranted", "`s3_log_lookup` is conditional", "synthetic vertical slice", "concrete unresolved `runtime_event` claim", "bounded time window", "correlation candidate", "owner-side orchestrator", "The model cannot grant", "S3 API", "generic S3 browsing is forbidden", "raw log lines never reach the model", "human-only evidence artifact"):
            self.assertIn(phrase, governed)
        self.assertNotIn("aws_log_lookup", governed)

    def test_support_brief_renders_from_a_hidden_converged_decision(self):
        template = INTERNAL_BRIEF.read_text()
        manifest = json.loads(
            (ROOT / "skill" / "contracts" / "investigation.json").read_text()
        )
        self.assertEqual(
            manifest["decisionFrame"],
            {
                "backgroundOnly": True,
                "naturalLanguageMayVary": True,
                "fields": [
                    "sanitized_question",
                    "claim_dispositions",
                    "source_coverage",
                    "accepted_evidence",
                    "conflicts",
                    "unknowns",
                    "route",
                    "next_step_owner",
                ],
            },
        )
        self.assertEqual(
            manifest["requiredBriefSections"],
            [
                "What the customer needs",
                "What I found",
                "What this means",
                "Recommended next step",
                "Reply Boundary",
            ],
        )
        for section in manifest["requiredBriefSections"]:
            self.assertIn(f"**{section}**", template)
        for operator_section in (
            "**Investigation Plan**",
            "**What I Checked**",
            "**Coverage and Freshness**",
            "**Source Ledger**",
        ):
            self.assertNotIn(operator_section, template)
        self.assertIn("kept in the background", template)
        self.assertIn("source name and safe reference", template)
        self.assertIn("Customer-reply drafting is outside `/orderdesk`", template)

    def test_cross_source_findings_preserve_claim_roles_instead_of_global_winners(self):
        skill = " ".join(SKILL.read_text().split())
        for phrase in (
            "intended process",
            "implementation at the cited commit",
            "neither source globally wins",
            "deployed commit",
            "runtime path",
            "correct remediation",
        ):
            self.assertIn(phrase, skill)
        for phrase in (
            "informal Slack context",
            "authoritative intended process",
            "runtime outcome",
            "workaround approval",
            "process owner for review",
        ):
            self.assertIn(phrase, skill)


class InvestigationEntrypointContractTests(unittest.TestCase):
    def test_positive_ticket_number_is_the_only_required_support_input(self):
        skill = " ".join(SKILL.read_text().split())
        agent = (ROOT / "skill" / "agents" / "openai.yaml").read_text()
        self.assertIn("one positive Help Scout ticket number", skill)
        self.assertIn("Do not ask the rep to restate the symptom", skill)
        self.assertIn("/orderdesk <positive Help Scout ticket number>", agent)
        self.assertIn("internal investigation brief", agent)

    def test_ticket_authority_is_conditional_and_governed(self):
        skill = " ".join(SKILL.read_text().split())
        for phrase in ("task-scoped authority", "smallest sufficient governed source set", "one unresolved claim", "configured company-governed", "Do not substitute a personal plugin", "Do not dispatch private-source subagents"):
            self.assertIn(phrase, skill)

    def test_skill_has_no_customer_copy_or_reply_drafting_mode(self):
        for document in (SKILL, ROOT / "skill" / "agents" / "openai.yaml"):
            text = document.read_text()
            for phrase in ("**Customer copy:**", "Separate customer-copy follow-up", "After a separate customer-copy request", "A later customer-copy request", "reply coaching", "paste-ready customer follow-ups"):
                self.assertNotIn(phrase, text)


class HelpScoutContractTests(unittest.TestCase):
    def test_correlation_and_readable_target_capabilities_are_versioned(self):
        skill = " ".join(SKILL.read_text().split())
        text = " ".join(HELP_SCOUT.read_text().split())
        for phrase in ("helpscout.support-context.typed-facts.v1", "helpscout.support-context.complete-target.v1", "helpscout.support-context.readable-masked-target.v3", "readable_masked_transcript", "typed_facts_fallback", "helpscout.support-correlation.opaque-handle.v1", "opaque-correlation-envelope", "before accepting or passing a correlation handle", "correlation candidate", "does not grant an S3 Logs read", "owner-side orchestrator", "mark correlation unavailable", "raw Help Scout prose never reaches the model", "attachmentEvidence", "excludedUnrecognizedThread", "exact receipt arithmetic", "Internal notes never contribute evidence"):
            self.assertIn(phrase, text)
        self.assertIn("normal product output remains readable", text.casefold())
        self.assertIn("fallback contains no transcript", text.casefold())
        self.assertIn("typed-facts fallback is quarantine", skill.casefold())
        self.assertIn("do not open another live ticket", skill.casefold())

    def test_whole_product_benchmark_requires_a_content_free_runtime_preflight(self):
        skill = " ".join(SKILL.read_text().split())
        help_scout = " ".join(HELP_SCOUT.read_text().split())
        governed = " ".join(GOVERNED_CONTEXT.read_text().split())

        for text in (skill, help_scout, governed):
            lowered = text.lower()
            self.assertIn("runtime_contract_mismatch", lowered)
            self.assertIn("whole-product benchmark", lowered)
            self.assertIn("before selecting or opening a ticket", lowered)
            self.assertIn("helpscouttargetoutputmodes", lowered)
            self.assertIn("helpscoutcorrelationoutputmode", lowered)
            self.assertIn("standard input", lowered)
        self.assertIn("fresh Codex task/runtime", skill)
        self.assertIn(
            "capability names, target output modes, correlation output mode, and tool names only",
            help_scout,
        )
        self.assertIn(
            "tool registration does not prove s3 logs readiness",
            governed.lower(),
        )

    def test_investigation_manifest_is_closed(self):
        manifest = json.loads((ROOT / "skill" / "contracts" / "investigation.json").read_text())
        self.assertEqual(manifest["replyDrafting"], "outside_skill")
        self.assertEqual(set(manifest["sources"]), {"help_scout_target", "helpscout_history", "public_kb", "slack", "notion", "code_context", "s3_logs"})
        self.assertEqual(
            manifest["sources"]["help_scout_target"],
            {
                "requiredTool": "helpscout_get_support_context",
                "mandatory": True,
                "outputModes": [
                    "readable_masked_transcript",
                    "typed_facts_fallback",
                ],
                "completeProviderPages": True,
            },
        )
        self.assertEqual(
            manifest["sources"]["s3_logs"],
            {
                "claimKinds": ["runtime_event"],
                "requiredTool": "s3_log_lookup",
                "status": "conditional",
            },
        )
        self.assertEqual(
            manifest["runtimePreflight"],
            {
                "scope": "whole_product_benchmark",
                "before": "ticket_selection_or_body_read",
                "onMismatch": "runtime_contract_mismatch",
                "contentFree": True,
            },
        )
        self.assertIn("runtime_contract_mismatch", manifest["stopErrors"])
        self.assertFalse(manifest["safety"]["rawLogLinesModelVisible"])
        self.assertTrue(manifest["safety"]["humanOnlyExactLogEvidenceSeparate"])
