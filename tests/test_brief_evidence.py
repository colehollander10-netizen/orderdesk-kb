import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "brief_evidence.py"
FIXTURE = ROOT / "tests" / "fixtures" / "freshness_conflict.json"
BRIEF_TEMPLATE = ROOT / "skill" / "references" / "internal-brief.md"


def evidence_record(record_id, claim_value, *, source_type="notion", source_date="2026-07-01", authority="authoritative"):
    return {
        "id": record_id, "claim_key": "resolution", "claim_value": claim_value,
        "summary": f"Synthetic sanitized evidence for {claim_value}.",
        "source_type": source_type, "safe_reference": f"safe-{record_id}",
        "source_date": source_date, "retrieved_at": "2026-07-21T16:30:00Z",
        "authority": authority, "claim_supported": f"Resolution is {claim_value}.",
        "coverage": "Synthetic bounded fixture.",
    }


class BriefEvidenceContractTests(unittest.TestCase):
    def run_fixture(self, fixture):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump(fixture, handle)
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

    def test_repeated_history_does_not_outvote_current_authority(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), str(FIXTURE)],
            check=True,
            capture_output=True,
            text=True,
        )
        result = json.loads(completed.stdout)

        self.assertFalse(result["contract"]["repetition_is_a_vote"])
        self.assertEqual(len(result["conflicts"]), 1)
        conflict = result["conflicts"][0]
        self.assertEqual(conflict["status"], "conflict")
        self.assertEqual(conflict["preference_status"], "preferred_for_review")
        self.assertEqual(conflict["preferred_source_id"], "current_policy")
        self.assertIn("repetition_is_not_a_vote", conflict["reason"])

        for source in result["evidence"]:
            self.assertIn("source_type", source)
            self.assertIn("source_date", source)
            self.assertIn("authority", source)

    def test_equal_authority_and_date_remains_unresolved(self):
        fixture = {
            "evidence": [
                evidence_record("source_a", "path_a"),
                evidence_record("source_b", "path_b"),
            ]
        }
        completed = self.run_fixture(fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        conflict = json.loads(completed.stdout)["conflicts"][0]
        self.assertEqual(conflict["preference_status"], "unresolved")
        self.assertIsNone(conflict["preferred_source_id"])

    def test_missing_provenance_fails_the_contract(self):
        record = evidence_record("source_a", "path_a")
        record.pop("source_date")
        fixture = {"evidence": [record]}
        completed = self.run_fixture(fixture)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("source_date", completed.stderr)

    def test_extra_private_or_arbitrary_evidence_fields_fail_closed(self):
        for field in ("rawTicketText", "correlationHandle", "extra", "__dict__"):
            record = evidence_record("source_a", "path_a")
            record[field] = "forbidden"
            completed = self.run_fixture({"evidence": [record]})
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("exactly", completed.stderr)

    def test_unknown_authority_remains_unresolved_even_when_dates_differ(self):
        fixture = {
            "evidence": [
                evidence_record("older_unknown", "path_a", source_type="help_scout", source_date="2025-01-01", authority="unknown"),
                evidence_record("newer_unknown", "path_b", source_type="help_scout", source_date="2026-01-01", authority="unknown"),
            ]
        }
        completed = self.run_fixture(fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        conflict = json.loads(completed.stdout)["conflicts"][0]
        self.assertEqual(conflict["preference_status"], "unresolved")
        self.assertIsNone(conflict["preferred_source_id"])
        self.assertEqual(conflict["reason"], "authority_not_established")

    def test_noncanonical_date_fails_the_contract(self):
        fixture = {
            "evidence": [
                evidence_record("source_a", "path_a", source_date="20260701"),
            ]
        }
        completed = self.run_fixture(fixture)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("YYYY-MM-DD", completed.stderr)

    def test_internal_brief_requires_source_ledger_and_conflicts(self):
        template = BRIEF_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("**Source Ledger**", template)
        self.assertIn("**Conflicts**", template)
        self.assertIn("source type", template)
        self.assertIn("source date", template)
        self.assertIn("explicit authority", template)
        self.assertIn("Repetition is not a vote", template)
        self.assertIn("Help Scout attachments: complete|partial|none|blocked|unavailable", template)
        self.assertIn("Attachment extraction: macOS native PDF text/OCR and layout", template)
        self.assertIn("Material ambiguity: none|<closed reason>", template)

    def test_every_governed_source_type_is_accepted(self):
        records = [evidence_record(f"source_{index}", "supported", source_type=source_type) | {"claim_key": f"claim_{index}"} for index, source_type in enumerate(("help_scout", "public_kb", "slack", "notion", "code_context", "s3_logs"), start=1)]
        result = self.run_fixture({"evidence": records})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({item["source_type"] for item in json.loads(result.stdout)["evidence"]}, {"help_scout", "public_kb", "slack", "notion", "code_context", "s3_logs"})

    def test_zero_evidence_coverage_only_abstention_is_valid(self):
        coverage = {
            "help_scout_target": {"status": "checked", "reason": "target_facts_received"},
            "helpscout_history": {"status": "skipped", "reason": "not_needed_for_named_claim"},
            "public_kb": {"status": "skipped", "reason": "safe_query_unavailable"},
            "slack": {"status": "skipped", "reason": "safe_query_unavailable"},
            "notion": {"status": "skipped", "reason": "safe_query_unavailable"},
            "code_context": {"status": "skipped", "reason": "safe_query_unavailable"},
            "s3_logs": {"status": "skipped", "reason": "log_not_material"},
        }
        completed = self.run_fixture({"evidence": [], "sourceCoverage": coverage})
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["sourceCoverage"], coverage)

    def test_source_coverage_rejects_extra_fields_and_unknown_reasons(self):
        coverage = {source: {"status": "skipped", "reason": "not_needed_for_named_claim"} for source in ("help_scout_target", "helpscout_history", "public_kb", "slack", "notion", "code_context", "s3_logs")}
        coverage["help_scout_target"] = {"status": "checked", "reason": "target_facts_received", "detail": "forbidden"}
        completed = self.run_fixture({"evidence": [], "sourceCoverage": coverage})
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("only status and reason", completed.stderr)
        coverage["help_scout_target"] = {"status": "checked", "reason": "invented_reason"}
        completed = self.run_fixture({"evidence": [], "sourceCoverage": coverage})
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("reason is invalid", completed.stderr)


if __name__ == "__main__":
    unittest.main()
