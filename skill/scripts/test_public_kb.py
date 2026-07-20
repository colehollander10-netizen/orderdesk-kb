import argparse
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import public_kb


class PublicKbInputTests(unittest.TestCase):
    def test_preserves_shell_metacharacters_as_one_value(self):
        mark = chr(96)
        raw = f'subject:"test" {mark}whoami{mark} $(id) --help\nnext line'
        parsed = public_kb.parse_query_line(json.dumps(raw))
        self.assertEqual(
            parsed,
            f'subject:"test" {mark}whoami{mark} $(id) --help next line',
        )

    def test_rejects_empty_non_string_and_nul(self):
        for value in ("", {}, "bad\x00query"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    public_kb.parse_query_line(json.dumps(value))

    def test_builds_argv_without_shell_interpolation(self):
        args = argparse.Namespace(command="search", limit=8, mode="auto")
        query = f'"quoted" {chr(96)}whoami{chr(96)} $(id)'
        with patch.object(public_kb, "resolve_binary", return_value=Path("/tmp/orderdesk-kb")):
            argv = public_kb.build_argv(args, query)
        self.assertEqual(argv[-1], query)
        self.assertEqual(argv.count(query), 1)
        self.assertIn("--limit", argv)


if __name__ == "__main__":
    unittest.main()
