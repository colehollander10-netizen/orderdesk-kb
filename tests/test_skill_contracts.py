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

    def test_code_context_and_aws_are_governed(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text().split())
        for phrase in ("`code_context`", "repository, path, line, and immutable commit", "approved default-branch snapshot", "does not prove deployment", "Code-only supporting evidence does not establish deployment, runtime cause, design intent, or that a code change is warranted", "`aws_log_lookup`", "`runtime_event`", "correlation availability", "schema-specific capability", "generic S3 browsing is forbidden", "raw log lines never reach the model"):
            self.assertIn(phrase, governed)

    def test_brief_records_plan_and_complete_source_disposition(self):
        template = INTERNAL_BRIEF.read_text()
        self.assertIn("**Investigation Plan**", template)
        for source in ("Help Scout target", "Help Scout history", "Public KB", "Slack", "Notion", "Code context", "AWS logs"):
            self.assertIn(f"- {source}:", template)
        self.assertIn("checked, planned, skipped, unavailable, or stopped", template)
        self.assertIn("retrieval time", template)
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
    def test_correlation_capability_is_versioned_and_fact_only(self):
        text = " ".join(HELP_SCOUT.read_text().split())
        for phrase in ("helpscout.support-context.typed-facts.v1", "helpscout.support-correlation.opaque-handle.v1", "opaque-correlation-envelope", "before accepting or passing a correlation handle", "mark correlation unavailable", "raw Help Scout prose never reaches the model", "internal notes and attachments are ignored"):
            self.assertIn(phrase, text)

    def test_investigation_manifest_is_closed(self):
        manifest = json.loads((ROOT / "skill" / "contracts" / "investigation.json").read_text())
        self.assertEqual(manifest["replyDrafting"], "outside_skill")
        self.assertEqual(set(manifest["sources"]), {"help_scout_target", "helpscout_history", "public_kb", "slack", "notion", "code_context", "aws_logs"})
