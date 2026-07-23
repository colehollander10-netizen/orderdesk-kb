import json
from pathlib import Path
import subprocess
import sys
import unittest

from skill.scripts.runtime_preflight import (
    GATEWAY_TOOLS,
    HELP_SCOUT_CAPABILITIES,
    HELP_SCOUT_CORRELATION_OUTPUT_MODE,
    evaluate_runtime_contract,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skill" / "scripts" / "runtime_preflight.py"


class RuntimePreflightTests(unittest.TestCase):
    def valid_payload(self):
        return {
            "helpScoutCapabilities": list(HELP_SCOUT_CAPABILITIES),
            "helpScoutCorrelationOutputMode": HELP_SCOUT_CORRELATION_OUTPUT_MODE,
            "gatewayTools": list(GATEWAY_TOOLS),
        }

    def test_accepts_the_exact_reviewed_runtime_surface(self):
        payload = self.valid_payload()
        payload["helpScoutCapabilities"].reverse()
        payload["gatewayTools"].reverse()

        self.assertEqual(evaluate_runtime_contract(payload), {"ok": True})

    def test_rejects_the_observed_stale_help_scout_surface(self):
        payload = self.valid_payload()
        payload["helpScoutCapabilities"].remove(
            "helpscout.support-correlation.opaque-handle.v1"
        )

        self.assertEqual(
            evaluate_runtime_contract(payload),
            {"ok": False, "error": "runtime_contract_mismatch"},
        )

    def test_rejects_the_observed_stale_gateway_surface(self):
        payload = self.valid_payload()
        payload["gatewayTools"] = payload["gatewayTools"][:7]

        self.assertEqual(
            evaluate_runtime_contract(payload),
            {"ok": False, "error": "runtime_contract_mismatch"},
        )

    def test_rejects_a_missing_or_wrong_correlation_output_mode(self):
        missing = self.valid_payload()
        missing.pop("helpScoutCorrelationOutputMode")
        wrong = self.valid_payload()
        wrong["helpScoutCorrelationOutputMode"] = "invented-wrong-mode"

        for candidate in (missing, wrong):
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    evaluate_runtime_contract(candidate),
                    {"ok": False, "error": "runtime_contract_mismatch"},
                )

    def test_fails_closed_on_extra_duplicate_or_non_string_values(self):
        candidates = []

        extra = self.valid_payload()
        extra["unexpected"] = []
        candidates.append(extra)

        duplicate = self.valid_payload()
        duplicate["gatewayTools"].append(duplicate["gatewayTools"][0])
        candidates.append(duplicate)

        non_string = self.valid_payload()
        non_string["helpScoutCapabilities"][0] = 1
        candidates.append(non_string)

        tuple_value = self.valid_payload()
        tuple_value["gatewayTools"] = tuple(tuple_value["gatewayTools"])
        candidates.append(tuple_value)

        class AccessorLike(dict):
            def keys(self):
                raise AssertionError("must not inspect mapping subclasses")

        candidates.append(AccessorLike(self.valid_payload()))

        for candidate in candidates:
            with self.subTest(candidate_type=type(candidate).__name__):
                self.assertEqual(
                    evaluate_runtime_contract(candidate),
                    {"ok": False, "error": "runtime_contract_mismatch"},
                )

    def test_failure_output_never_reflects_submitted_values(self):
        marker = "invented-private-marker"
        result = evaluate_runtime_contract(
            {
                "helpScoutCapabilities": [marker],
                "gatewayTools": [marker],
            }
        )

        self.assertEqual(
            result,
            {"ok": False, "error": "runtime_contract_mismatch"},
        )
        self.assertNotIn(marker, str(result))

    def test_cli_returns_only_the_content_free_result_and_exit_status(self):
        accepted = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(self.valid_payload()),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual(json.loads(accepted.stdout), {"ok": True})

        marker = "invented-private-marker"
        rejected = subprocess.run(
            [sys.executable, str(SCRIPT)],
            input=json.dumps(
                {
                    "helpScoutCapabilities": [marker],
                    "helpScoutCorrelationOutputMode": marker,
                    "gatewayTools": [marker],
                }
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(rejected.returncode, 1)
        self.assertEqual(
            json.loads(rejected.stdout),
            {"ok": False, "error": "runtime_contract_mismatch"},
        )
        self.assertNotIn(marker, rejected.stdout + rejected.stderr)

    def test_expected_values_are_derived_from_the_reviewed_manifests(self):
        contracts = ROOT / "skill" / "contracts"
        help_scout = json.loads((contracts / "help-scout.json").read_text())
        correlation = json.loads(
            (contracts / "help-scout-correlation.json").read_text()
        )
        runtime = json.loads((contracts / "runtime-preflight.json").read_text())

        self.assertEqual(
            HELP_SCOUT_CAPABILITIES,
            frozenset(
                [
                    help_scout["requiredCapability"],
                    *help_scout["requiredTargetCapabilities"],
                    correlation["requiredCapability"],
                ]
            ),
        )
        self.assertEqual(
            HELP_SCOUT_CAPABILITIES,
            frozenset(
                {
                    "helpscout.support-context.typed-facts.v1",
                    "helpscout.support-context.complete-target.v1",
                    "helpscout.support-context.masked-target-transcript.v1",
                    "helpscout.support-correlation.opaque-handle.v1",
                }
            ),
        )
        self.assertEqual(
            HELP_SCOUT_CORRELATION_OUTPUT_MODE,
            correlation["requiredOutputMode"],
        )
        self.assertEqual(
            HELP_SCOUT_CORRELATION_OUTPUT_MODE,
            "opaque-correlation-envelope",
        )
        self.assertEqual(GATEWAY_TOOLS, frozenset(runtime["gatewayTools"]))
        self.assertEqual(
            GATEWAY_TOOLS,
            frozenset(
                {
                    "slack_search",
                    "slack_conversations",
                    "slack_recent_messages",
                    "slack_thread",
                    "notion_search",
                    "notion_page",
                    "bitbucket_directory",
                    "bitbucket_file",
                    "code_context",
                    "s3_log_lookup",
                }
            ),
        )
        self.assertEqual(runtime["ordering"], "unordered_exact")


if __name__ == "__main__":
    unittest.main()
