"""Fast, offline unit tests for the pure-logic pieces.

These don't hit the network or defuddle — they pin the behaviors that the
de-risk runs surfaced as load-bearing: heading vs. paragraph chunking, video /
empty stub removal, stopword-aware querying, and relative-gap confidence.

Run: python3 -m pytest tests/  (or python3 -m unittest discover tests)
"""

import unittest

from orderdesk_kb.extract import _chunk, _is_video_stub, _strip_images, Section
from orderdesk_kb import index as index_mod
from orderdesk_kb.index import _query_terms, _escape_query, _match_candidates
from orderdesk_kb.cli import _confidence
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


class LexicalSearchTests(unittest.TestCase):
    """AND-first precision with OR fallback, against a real FTS5 index."""

    def setUp(self):
        self.conn = index_mod.connect(":memory:")
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
