from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GOVERNED_CONTEXT = ROOT / "skill" / "references" / "governed-context.md"
INTERNAL_BRIEF = ROOT / "skill" / "references" / "internal-brief.md"
PUBLIC_KB = ROOT / "skill" / "references" / "public-kb.md"
HELP_SCOUT = ROOT / "skill" / "references" / "help-scout.md"
SKILL = ROOT / "skill" / "SKILL.md"


class MultiSourceBriefContractTests(unittest.TestCase):
    def test_bounded_slack_read_is_reported_as_limited_coverage(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text(encoding="utf-8").split())
        template = " ".join(INTERNAL_BRIEF.read_text(encoding="utf-8").split())

        self.assertIn("no match within the checked window", governed)
        self.assertIn("not a workspace-wide search", governed)
        self.assertIn("bounded conversation/time/message window", template)
        self.assertIn("not workspace-wide", template)
        self.assertIn("Never use bare `not found` for Slack or Notion", template)

    def test_notion_title_search_is_reported_as_limited_coverage(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text(encoding="utf-8").split())
        template = " ".join(INTERNAL_BRIEF.read_text(encoding="utf-8").split())

        self.assertIn("searches approved page titles only", governed)
        self.assertIn("no title match in the bounded query", governed)
        self.assertIn("page bodies remained unchecked", governed)
        self.assertIn("title-only query and result cap", template)
        self.assertIn("not a comprehensive Notion absence", template)

    def test_bitbucket_source_failure_remains_unchecked(self):
        governed = " ".join(GOVERNED_CONTEXT.read_text(encoding="utf-8").split())
        template = " ".join(INTERNAL_BRIEF.read_text(encoding="utf-8").split())

        self.assertIn("Bitbucket remained unchecked", governed)
        self.assertIn("Do not infer code behavior or code absence", governed)
        self.assertIn("safe failure code and remained unchecked", template)
        self.assertIn("no code-behavior inference", template)

    def test_every_multi_source_brief_records_public_kb_freshness(self):
        template = " ".join(INTERNAL_BRIEF.read_text(encoding="utf-8").split())
        public_kb = " ".join(PUBLIC_KB.read_text(encoding="utf-8").split())
        skill = " ".join(SKILL.read_text(encoding="utf-8").split())

        self.assertIn("Public KB freshness", template)
        self.assertIn("health checked at", template)
        self.assertIn("newest and oldest `fetched_at`", template)
        self.assertIn("Always retain this freshness line", template)
        self.assertIn("every multi-source brief", public_kb)
        self.assertIn("public-KB freshness record", skill)

    def test_top_level_skill_preserves_source_specific_coverage_limits(self):
        skill = " ".join(SKILL.read_text(encoding="utf-8").split())

        self.assertIn("bounded Slack window", skill)
        self.assertIn("title-only Notion search", skill)
        self.assertIn("Bitbucket remained unchecked", skill)
        self.assertIn("Never turn limited discovery into comprehensive absence", skill)


class HelpScoutWorkflowContractTests(unittest.TestCase):
    def assert_fact_only_help_scout_contract(self, document):
        folded = document.casefold()
        for phrase in (
            "fact-only",
            "raw Help Scout prose never reaches the model",
            "closed enums, counts, missing-evidence codes, and rule IDs",
            "zero or more safe facts",
            "not route-ready",
            "fixed missing-evidence codes",
            "zero-fact partial does not produce history search terms",
            "actual closed safe public term",
            "partial is not `masking_failed`",
            "internal notes and attachments are ignored",
            "operator-only local diagnostic",
            "never model context",
            "not a fallback",
            "metadata and handles remain bounded",
            "blocked stops the workflow safely",
        ):
            self.assertIn(phrase.casefold(), folded)

        for stale in (
            "includeTargetBodies",
            "historicalTicketNumbers",
            "800 characters per body",
            "eight target threads",
            "four threads per historical",
            "For CLI fallback",
            "CLI fallback is not an atomic",
        ):
            self.assertNotIn(stale, document)

    def test_top_level_skill_teaches_fact_only_help_scout_workflow(self):
        skill = " ".join(SKILL.read_text(encoding="utf-8").split())

        self.assert_fact_only_help_scout_contract(skill)
        self.assertIn("`historicalSelectionHandles`", skill)
        self.assertIn("process-local", skill)
        self.assertIn("five minutes", skill)
        self.assertIn("one-time", skill)

    def test_help_scout_reference_teaches_fact_only_workflow(self):
        reference = " ".join(HELP_SCOUT.read_text(encoding="utf-8").split())

        self.assert_fact_only_help_scout_contract(reference)
        self.assertIn("`historySelectionHandle`", reference)
        self.assertIn("`historicalSelectionHandles`", reference)
        self.assertIn("Expired, unissued, or reused", reference)


if __name__ == "__main__":
    unittest.main()
