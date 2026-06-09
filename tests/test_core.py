"""Fast, offline unit tests for the pure-logic pieces.

These don't hit the network or defuddle — they pin the behaviors that the
de-risk runs surfaced as load-bearing: heading vs. paragraph chunking, video /
empty stub removal, stopword-aware querying, and relative-gap confidence.

Run: python3 -m pytest tests/  (or python3 -m unittest discover tests)
"""

import unittest

from orderdesk_kb.extract import _chunk, _is_video_stub, _strip_images, Section
from orderdesk_kb.index import _query_terms, _escape_query
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
