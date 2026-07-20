"""Fast, offline unit tests for the pure-logic pieces.

These don't hit the network or defuddle — they pin the behaviors that the
de-risk runs surfaced as load-bearing: heading vs. paragraph chunking, video /
empty stub removal, stopword-aware querying, and relative-gap confidence.

Run: python3 -m pytest tests/  (or python3 -m unittest discover tests)
"""

import unittest
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import nullcontext
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

from orderdesk_kb.extract import _chunk, _is_video_stub, _strip_images, Section
from orderdesk_kb import index as index_mod
from orderdesk_kb.index import _query_terms, _escape_query, _match_candidates
from orderdesk_kb.cli import (
    _confidence,
    _source_kind,
    _triage_payload,
    _sync_lock,
    build_parser,
    cmd_sync,
    SyncAlreadyRunning,
)
from orderdesk_kb.index import Hit


def _hit(rank: float) -> Hit:
    return Hit(rank=rank, title="t", heading_path="p", anchor_url="u",
               snippet="s", text="body text here")


class ChunkingTests(unittest.TestCase):
    def test_paragraphs_pack_when_no_headings(self):
        content = "\n\n".join(["Para one is reasonably long." * 4,
                               "Para two is also a full sentence." * 4])
        sections = list(_chunk(content, "http://x/", "Title"))
        self.assertGreaterEqual(len(sections), 1)
        self.assertTrue(all(s.heading == "" for s in sections))

    def test_headings_become_section_boundaries(self):
        content = "intro line that is long enough to keep here.\n\n" \
                  "## First\nbody of first section goes here, plenty long.\n\n" \
                  "## Second\nbody of the second section, also long enough."
        sections = list(_chunk(content, "http://x/", "T"))
        headings = [s.heading for s in sections]
        self.assertIn("First", headings)
        self.assertIn("Second", headings)
        first = next(s for s in sections if s.heading == "First")
        self.assertEqual(first.anchor_url, "http://x/#first")

    def test_video_stub_detected(self):
        stub = Section(url="u", anchor_url="u#w", title="T", heading="Watch and Learn",
                       heading_path="T > Watch and Learn",
                       text="Are you a visual learner? Watch below.")
        self.assertTrue(_is_video_stub(stub))

    def test_short_useful_section_not_a_video_stub(self):
        useful = Section(url="u", anchor_url="u#r", title="T", heading="Remove Users",
                         heading_path="T > Remove Users",
                         text="Click Remove Access next to the user name.")
        self.assertFalse(_is_video_stub(useful))

    def test_strip_images_and_iframes(self):
        text = "Real text.\n\n![alt](http://x/img.png)\n\n" \
               '<iframe src="http://v"></iframe>\n\nMore real text.'
        cleaned = _strip_images(text)
        self.assertIn("Real text.", cleaned)
        self.assertIn("More real text.", cleaned)
        self.assertNotIn("iframe", cleaned)
        self.assertNotIn("img.png", cleaned)


class QueryTests(unittest.TestCase):
    def test_stopwords_removed(self):
        self.assertEqual(_query_terms("how do I connect Shopify"), ["connect", "shopify"])

    def test_all_stopwords_falls_back(self):
        # Never return an empty MATCH; fall back to raw words.
        self.assertTrue(_query_terms("how do I"))

    def test_escape_quotes_each_term(self):
        self.assertEqual(_escape_query("split orders"), '"split" OR "orders"')

    def test_match_candidates_try_and_before_or(self):
        self.assertEqual(
            _match_candidates("split orders"),
            ['"split" AND "orders"', '"split" OR "orders"'],
        )

    def test_match_candidates_single_term(self):
        self.assertEqual(_match_candidates("shopify"), ['"shopify"'])


class SyncSafetyTests(unittest.TestCase):
    def test_sync_defaults_are_site_safe(self):
        args = build_parser().parse_args(["sync"])
        self.assertEqual(args.workers, 1)
        self.assertEqual(args.delay, 2.0)

    def test_cmd_sync_passes_safety_settings_to_crawler(self):
        args = build_parser().parse_args(["--db", ":memory:", "--json", "sync"])
        conn = Mock()
        result = Mock(fetched=0, skipped=0, empty=0, failed=0, errors=[])

        with patch("orderdesk_kb.cli.index_mod.connect", return_value=conn), \
             patch("orderdesk_kb.cli.run_sync", return_value=result) as run_sync, \
             patch("orderdesk_kb.cli.index_mod.stats", return_value={"pages": 0, "sections": 0}), \
             patch("orderdesk_kb.cli.embed_mod.is_available", return_value=False), \
             patch("orderdesk_kb.cli._sync_lock", return_value=nullcontext()):
            with redirect_stdout(io.StringIO()):
                cmd_sync(args)

        run_sync.assert_called_once()
        self.assertEqual(run_sync.call_args.kwargs["max_workers"], 1)
        self.assertEqual(run_sync.call_args.kwargs["min_interval"], 2.0)
        conn.close.assert_called_once()

    def test_sync_lock_contends_across_absolute_relative_and_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "kb.db"
            symlink_path = Path(directory) / "kb-alias.db"
            symlink_path.symlink_to(db_path)
            relative_path = Path(os.path.relpath(db_path, Path.cwd()))

            with _sync_lock(db_path):
                for alias in (relative_path, symlink_path):
                    with self.subTest(alias=alias):
                        with self.assertRaises(SyncAlreadyRunning):
                            with _sync_lock(alias):
                                self.fail("alias acquired an already-held sync lock")


class MissingLockBackendTests(unittest.TestCase):
    def run_without_fcntl(self, *arguments):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            shim = Path(directory) / "fcntl.py"
            shim.write_text("raise ImportError('fcntl unavailable for test')\n", encoding="utf-8")
            db_path = Path(directory) / "portable.db"
            env = os.environ.copy()
            env["PYTHONPATH"] = os.pathsep.join((directory, str(root)))
            return subprocess.run(
                [sys.executable, "-m", "orderdesk_kb", "--db", str(db_path), *arguments],
                cwd=root,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_non_sync_command_runs_without_fcntl(self):
        completed = self.run_without_fcntl("--json", "stats")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["pages"], 0)

    def test_sync_fails_closed_without_supported_lock_backend(self):
        completed = self.run_without_fcntl("--json", "sync")

        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertIn("sync locking is unavailable", completed.stderr)


class TriageTests(unittest.TestCase):
    def test_source_kind_labels_common_doc_areas(self):
        self.assertEqual(
            _source_kind("https://help.orderdesk.com/order-desk-101/how-to-split-orders/"),
            "general",
        )
        self.assertEqual(
            _source_kind("https://help.orderdesk.com/integration-setup-guides/x/"),
            "integration",
        )

    def test_triage_command_defaults_to_support_brief_limit(self):
        args = build_parser().parse_args(["triage", "how do I split an order?"])
        self.assertEqual(args.limit, 6)
        self.assertEqual(args.mode, "auto")

    def test_triage_payload_carries_boundary_and_sources(self):
        payload = _triage_payload(
            "how do I split an order?",
            "hybrid",
            [
                Hit(
                    rank=-1.0,
                    title="Split Orders",
                    heading_path="Split Orders > How",
                    anchor_url="https://help.orderdesk.com/x#how",
                    snippet="Split orders into multiple shipments.",
                    text="Split orders into multiple shipments.",
                    similarity=0.72,
                    lastmod="2026-07-10T12:00:00+00:00",
                    published="2025-06-01T09:30:00+00:00",
                    synced_at="2026-07-14T16:45:00+00:00",
                )
            ],
        )

        self.assertEqual(payload["confidence"], "high")
        self.assertIn("Public Order Desk docs only", payload["boundary"])
        self.assertEqual(payload["sources"][0]["section"], "Split Orders > How")
        self.assertEqual(payload["sources"][0]["kind"], "public-doc")
        self.assertEqual(payload["sources"][0]["similarity"], 0.72)
        self.assertEqual(
            payload["sources"][0]["source_dates"],
            {
                "published_at": "2025-06-01T09:30:00+00:00",
                "modified_at": "2026-07-10T12:00:00+00:00",
                "fetched_at": "2026-07-14T16:45:00+00:00",
            },
        )
        self.assertIn(
            "does not prove the live page is unchanged",
            payload["freshness_note"],
        )

    def test_triage_payload_handles_no_public_kb_match(self):
        payload = _triage_payload("private customer billing issue", "hybrid", [])
        self.assertEqual(payload["confidence"], "none")
        self.assertEqual(payload["sources"], [])
        self.assertIn("did not surface coverage", payload["recommended_next_step"])

    def test_triage_source_dates_remain_unknown_when_index_metadata_is_missing(self):
        payload = _triage_payload(
            "split an order",
            "lexical",
            [
                Hit(
                    rank=-1.0,
                    title="Split Orders",
                    heading_path="Split Orders > How",
                    anchor_url="https://help.orderdesk.com/x#how",
                    snippet="Split orders into multiple shipments.",
                    text="Split orders into multiple shipments.",
                )
            ],
        )

        self.assertEqual(
            payload["sources"][0]["source_dates"],
            {"published_at": None, "modified_at": None, "fetched_at": None},
        )


class LexicalSearchTests(unittest.TestCase):
    """AND-first precision with OR fallback, against a real FTS5 index."""

    def setUp(self):
        self.conn = index_mod.connect(":memory:")
        self.addCleanup(self.conn.close)
        index_mod.init_schema(self.conn)
        index_mod.upsert_page(
            self.conn,
            url="http://kb/split",
            title="Split Orders",
            lastmod="x", published="", word_count=10,
            synced_at="2026-01-01T00:00:00Z",
            sections=[Section(
                url="http://kb/split", anchor_url="http://kb/split#how",
                title="Split Orders", heading="How",
                heading_path="Split Orders > How",
                text="You can split orders into multiple shipments.",
            )],
        )
        index_mod.upsert_page(
            self.conn,
            url="http://kb/general",
            title="Working With Orders",
            lastmod="x", published="", word_count=10,
            synced_at="2026-01-01T00:00:00Z",
            sections=[Section(
                url="http://kb/general", anchor_url="http://kb/general#intro",
                title="Working With Orders", heading="Intro",
                heading_path="Working With Orders > Intro",
                text="Orders arrive in the folder. Orders can be edited.",
            )],
        )
        self.conn.commit()

    def test_and_filters_out_partial_matches(self):
        hits = index_mod.search(self.conn, "split orders")
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].anchor_url, "http://kb/split#how")
        self.assertEqual(hits[0].lastmod, "x")
        self.assertEqual(hits[0].published, "")
        self.assertEqual(hits[0].synced_at, "2026-01-01T00:00:00Z")

    def test_or_fallback_when_a_term_is_off_corpus(self):
        # "zorblat" appears nowhere; AND yields nothing, OR still rescues
        # the query instead of returning an empty result set.
        hits = index_mod.search(self.conn, "split zorblat")
        self.assertTrue(hits)
        self.assertEqual(hits[0].anchor_url, "http://kb/split#how")


class ConfidenceTests(unittest.TestCase):
    def test_clear_separation_is_high(self):
        # #1 far stronger (more negative) than #2.
        self.assertEqual(_confidence([_hit(-10.0), _hit(-2.0)]), "high")

    def test_tight_cluster_is_low(self):
        self.assertEqual(_confidence([_hit(-5.0), _hit(-4.9)]), "low")

    def test_no_hits_is_none(self):
        self.assertEqual(_confidence([]), "none")

    def test_never_high_on_tie(self):
        self.assertNotEqual(_confidence([_hit(-3.0), _hit(-3.0)]), "high")


if __name__ == "__main__":
    unittest.main()
