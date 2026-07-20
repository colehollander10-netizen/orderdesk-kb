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
                {
                    "id": "source_a",
                    "claim_key": "resolution",
                    "claim_value": "path_a",
                    "summary": "Sanitized path A.",
                    "source_type": "policy",
                    "source_date": "2026-07-01",
                    "authority": "authoritative",
                },
                {
                    "id": "source_b",
                    "claim_key": "resolution",
                    "claim_value": "path_b",
                    "summary": "Sanitized path B.",
                    "source_type": "policy",
                    "source_date": "2026-07-01",
                    "authority": "authoritative",
                },
            ]
        }
        completed = self.run_fixture(fixture)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        conflict = json.loads(completed.stdout)["conflicts"][0]
        self.assertEqual(conflict["preference_status"], "unresolved")
        self.assertIsNone(conflict["preferred_source_id"])

    def test_missing_provenance_fails_the_contract(self):
        fixture = {
            "evidence": [
                {
                    "id": "source_a",
                    "claim_key": "resolution",
                    "claim_value": "path_a",
                    "summary": "Sanitized path A.",
                    "source_type": "policy",
                    "authority": "authoritative",
                }
            ]
        }
        completed = self.run_fixture(fixture)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("source_date", completed.stderr)

    def test_unknown_authority_remains_unresolved_even_when_dates_differ(self):
        fixture = {
            "evidence": [
                {
                    "id": "older_unknown",
                    "claim_key": "resolution",
                    "claim_value": "path_a",
                    "summary": "Sanitized older source.",
                    "source_type": "ticket",
                    "source_date": "2025-01-01",
                    "authority": "unknown",
                },
                {
                    "id": "newer_unknown",
                    "claim_key": "resolution",
                    "claim_value": "path_b",
                    "summary": "Sanitized newer source.",
                    "source_type": "ticket",
                    "source_date": "2026-01-01",
                    "authority": "unknown",
                },
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
                {
                    "id": "source_a",
                    "claim_key": "resolution",
                    "claim_value": "path_a",
                    "summary": "Sanitized path A.",
                    "source_type": "policy",
                    "source_date": "20260701",
                    "authority": "authoritative",
                }
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


if __name__ == "__main__":
    unittest.main()
