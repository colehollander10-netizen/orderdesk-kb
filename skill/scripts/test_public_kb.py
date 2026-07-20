import argparse
import json
import sqlite3
import sys
import tempfile
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
        with patch.object(public_kb, "resolve_binary", return_value=Path("/tmp/orderdesk-kb")), \
             patch.object(public_kb, "resolve_db", return_value=Path("/tmp/alternate.db")):
            argv = public_kb.build_argv(args, query)
        self.assertEqual(argv[-1], query)
        self.assertEqual(argv.count(query), 1)
        self.assertIn("--limit", argv)
        self.assertEqual(
            argv,
            [
                "/tmp/orderdesk-kb",
                "--db",
                "/tmp/alternate.db",
                "--json",
                "search",
                "--limit",
                "8",
                "--mode",
                "auto",
                query,
            ],
        )

    def test_env_database_is_shared_by_health_and_query_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "alternate.db"
            connection = sqlite3.connect(db_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE pages (synced_at TEXT);
                    CREATE TABLE sections (body TEXT);
                    CREATE TABLE embeddings (vector BLOB);
                    INSERT INTO pages VALUES ('2026-07-20T00:00:00Z');
                    INSERT INTO sections VALUES ('safe public text');
                    """
                )
                connection.commit()
            finally:
                connection.close()

            args = argparse.Namespace(command="ask", limit=8, mode="lexical")
            with patch.dict("os.environ", {"ORDERDESK_KB_DB": str(db_path)}), \
                 patch.object(
                     public_kb, "resolve_binary", return_value=Path("/repo/bin/orderdesk-kb")
                 ):
                health = public_kb.health_payload()
                argv = public_kb.build_argv(args, "How do folders work?")

            resolved = str(db_path.resolve())
            self.assertEqual(health["db"], resolved)
            self.assertEqual(argv[1:3], ["--db", resolved])

    def test_prefers_canonical_repo_launcher_over_path_binary(self):
        with patch.object(public_kb.shutil, "which", return_value="/usr/local/bin/orderdesk-kb"):
            self.assertEqual(public_kb.resolve_binary(), public_kb.FALLBACK_BIN.resolve())


if __name__ == "__main__":
    unittest.main()
