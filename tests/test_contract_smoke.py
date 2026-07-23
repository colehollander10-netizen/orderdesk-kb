import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ContractSmokePortabilityTests(unittest.TestCase):
    def make_clean_skill_copy(self, directory):
        skill = Path(directory) / "checkout" / "skill"
        skill.parent.mkdir()
        shutil.copytree(ROOT / "skill", skill)
        return skill

    def run_smoke(self, skill, *arguments):
        env = os.environ.copy()
        env.pop("ORDERDESK_KB_DB", None)
        env.pop("ORDERDESK_KB_BIN", None)
        return subprocess.run(
            [sys.executable, str(skill / "scripts" / "contract_smoke.py"), *arguments],
            cwd=skill.parent,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_default_smoke_passes_from_clean_skill_only_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)

            completed = self.run_smoke(skill)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertNotIn("kb_health", payload)

    def test_portable_smoke_requires_ticket_driven_investigation_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            manifest = skill / "contracts" / "investigation.json"
            self.assertTrue(manifest.is_file())
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(payload["entrypoint"], {"input": "positive_help_scout_ticket_number", "output": "internal_investigation_brief"})
            self.assertEqual(payload["replyDrafting"], "outside_skill")
            correlation = json.loads((skill / "contracts" / "help-scout-correlation.json").read_text(encoding="utf-8"))
            self.assertEqual(correlation["requiredCapability"], "helpscout.support-correlation.opaque-handle.v1")
            completed = self.run_smoke(skill)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["investigationSchemaVersion"], 1)

    def test_portable_smoke_rejects_reply_drafting_in_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            manifest = skill / "contracts" / "investigation.json"
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            payload["replyDrafting"] = "inside_skill"
            manifest.write_text(json.dumps(payload), encoding="utf-8")
            completed = self.run_smoke(skill)
        self.assertEqual(completed.returncode, 1)
        self.assertIn("reply drafting boundary mismatch", completed.stderr)

    def test_portable_smoke_rejects_reply_mode_or_missing_source_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            skill_file = skill / "SKILL.md"
            skill_file.write_text(skill_file.read_text(encoding="utf-8") + "\n**Customer copy:** paste-ready customer follow-ups.\n", encoding="utf-8")
            completed = self.run_smoke(skill)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("customer-copy mode is outside this skill", completed.stderr)
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            governed = skill / "references" / "governed-context.md"
            governed.write_text(governed.read_text(encoding="utf-8").replace("`slack_search`", "`slack_recent_messages`"), encoding="utf-8")
            completed = self.run_smoke(skill)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("required governed tool missing: slack_search", completed.stderr)

    def test_opt_in_help_scout_contract_compares_exact_closed_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            connector = Path(directory) / "help-scout-mcp"
            executable = connector / "bin" / "help-scout-mcp.js"
            executable.parent.mkdir(parents=True)
            contract = {
                "schemaVersion": 1,
                "capability": "helpscout.support-context.typed-facts.v1",
                "targetCapabilities": [
                    "helpscout.support-context.complete-target.v1",
                    "helpscout.support-context.masked-target-transcript.v1",
                ],
                "outputMode": "masked-target-transcript-and-typed-history-facts",
                "safety": {
                    "rawProseModelVisible": False,
                    "maskedTargetProseModelVisible": True,
                    "internalNotesUsedAsEvidence": False,
                    "attachmentsAccessed": False,
                    "failClosed": True,
                },
            }
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                f"print(json.dumps({contract!r}))\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            completed = self.run_smoke(
                skill, "--help-scout-root", str(connector)
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["help_scout_integration"])

    def test_opt_in_help_scout_contract_rejects_capability_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            connector = Path(directory) / "help-scout-mcp"
            executable = connector / "bin" / "help-scout-mcp.js"
            executable.parent.mkdir(parents=True)
            executable.write_text(
                "#!/usr/bin/env python3\n"
                "import json\n"
                "print(json.dumps({'schemaVersion': 1, 'capability': 'wrong', "
                "'outputMode': 'typed-facts', "
                "'safety': {'rawProseModelVisible': False, "
                "'internalNotesUsedAsEvidence': False, 'attachmentsAccessed': False, "
                "'failClosed': True}}))\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)

            completed = self.run_smoke(
                skill, "--help-scout-root", str(connector)
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("capability mismatch", completed.stderr)

    def test_opt_in_help_scout_contract_rejects_incomplete_target_capability_set(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            connector = Path(directory) / "help-scout-mcp"
            executable = connector / "bin" / "help-scout-mcp.js"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/usr/bin/env python3\nimport json\nprint(json.dumps({'schemaVersion': 1, 'capability': 'helpscout.support-context.typed-facts.v1', 'targetCapabilities': ['helpscout.support-context.masked-target-transcript.v1'], 'outputMode': 'masked-target-transcript-and-typed-history-facts', 'safety': {'rawProseModelVisible': False, 'maskedTargetProseModelVisible': True, 'internalNotesUsedAsEvidence': False, 'attachmentsAccessed': False, 'failClosed': True}}))\n", encoding="utf-8")
            executable.chmod(0o755)
            completed = self.run_smoke(skill, "--help-scout-root", str(connector))
        self.assertEqual(completed.returncode, 1)
        self.assertIn("Help Scout target capabilities mismatch", completed.stderr)


if __name__ == "__main__":
    unittest.main()
