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

    def test_opt_in_help_scout_contract_compares_exact_closed_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = self.make_clean_skill_copy(directory)
            connector = Path(directory) / "help-scout-mcp"
            executable = connector / "bin" / "help-scout-mcp.js"
            executable.parent.mkdir(parents=True)
            contract = {
                "schemaVersion": 1,
                "capability": "helpscout.support-context.typed-facts.v1",
                "outputMode": "typed-facts",
                "safety": {
                    "rawProseModelVisible": False,
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


if __name__ == "__main__":
    unittest.main()
