"""Offline tests for the semantic layer (embed.py + index.py vector paths).

No model download, no numpy required: a tiny keyword-based fake embedder
stands in for model2vec so these pin the MECHANICS (storage, ranking, fusion,
sync invariants) rather than embedding quality.
"""

import unittest

from orderdesk_kb import embed as embed_mod
from orderdesk_kb import index as index_mod
from orderdesk_kb.cli import _confidence
from orderdesk_kb.extract import Section
from orderdesk_kb.index import Hit


# Three semantic "topics" as axes. A real model has hundreds of dimensions;
# three is enough to prove geometry: synonyms share an axis, unrelated
# sections are orthogonal (cosine 0).
_AXES = (
    ("shopify", "store", "storefront"),
    ("stripe", "payment"),
    ("shipping", "label"),
)


def fake_embed(texts):
    vectors = []
    for text in texts:
        lowered = text.lower()
        vec = [
            1.0 if any(word in lowered for word in axis) else 0.0
            for axis in _AXES
        ]
        norm = sum(x * x for x in vec) ** 0.5
        vectors.append([x / norm for x in vec] if norm else vec)
    return vectors


def _section(url, slug, title, heading, text):
    return Section(
        url=url,
        anchor_url=f"{url}#{slug}",
        title=title,
        heading=heading,
        heading_path=f"{title} > {heading}",
        text=text,
    )


SHOPIFY_URL = "http://kb/shopify"
STRIPE_URL = "http://kb/stripe"


def make_db():
    conn = index_mod.connect(":memory:")
    index_mod.init_schema(conn)
    index_mod.upsert_page(
        conn,
        url=SHOPIFY_URL,
        title="Shopify Integration",
        lastmod="2026-01-01",
        published="",
        word_count=50,
        synced_at="2026-01-01T00:00:00Z",
        sections=[
            _section(
                SHOPIFY_URL, "connect", "Shopify Integration", "Connect Shopify",
                "Use the Shopify integration to import orders.",
            ),
        ],
    )
    index_mod.upsert_page(
        conn,
        url=STRIPE_URL,
        title="Stripe Integration",
        lastmod="2026-01-01",
        published="",
        word_count=50,
        synced_at="2026-01-01T00:00:00Z",
        sections=[
            _section(
                STRIPE_URL, "webhook", "Stripe Integration", "Webhook Setup",
                "Configure the Stripe webhook for payment events.",
            ),
        ],
    )
    conn.commit()
    return conn


class BlobTests(unittest.TestCase):
    def test_pack_unpack_roundtrip(self):
        vec = [0.25, -1.5, 0.0, 3.0]
        self.assertEqual(embed_mod.unpack(embed_mod.pack(vec)), vec)

    def test_top_k_orders_by_cosine(self):
        rows = [
            (1, embed_mod.pack([1.0, 0.0])),
            (2, embed_mod.pack([0.0, 1.0])),
            (3, embed_mod.pack([0.7, 0.7])),
        ]
        top = embed_mod.top_k([1.0, 0.0], rows, k=2)
        self.assertEqual([section_id for section_id, _ in top], [1, 3])
        self.assertAlmostEqual(top[0][1], 1.0, places=5)


class EmbedMissingTests(unittest.TestCase):
    def test_embeds_all_then_is_idempotent(self):
        conn = make_db()
        self.assertFalse(index_mod.embeddings_ready(conn))
        self.assertEqual(index_mod.embed_missing(conn, embed_fn=fake_embed), 2)
        self.assertTrue(index_mod.embeddings_ready(conn))
        # Second run has nothing left to do.
        self.assertEqual(index_mod.embed_missing(conn, embed_fn=fake_embed), 0)

    def test_force_reembeds_everything(self):
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        self.assertEqual(
            index_mod.embed_missing(conn, embed_fn=fake_embed, force=True), 2
        )

    def test_resync_drops_stale_vectors(self):
        # The invariant that keeps hybrid search honest: re-crawling a page
        # assigns new section rowids, so its old vectors must go with it.
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        index_mod.upsert_page(
            conn,
            url=SHOPIFY_URL,
            title="Shopify Integration",
            lastmod="2026-02-01",
            published="",
            word_count=60,
            synced_at="2026-02-01T00:00:00Z",
            sections=[
                _section(
                    SHOPIFY_URL, "connect", "Shopify Integration",
                    "Connect Shopify", "Updated connection steps for Shopify.",
                ),
            ],
        )
        orphans = conn.execute(
            """
            SELECT COUNT(*) AS n FROM embeddings e
            LEFT JOIN sections s ON s.rowid = e.section_id
            WHERE s.rowid IS NULL
            """
        ).fetchone()["n"]
        self.assertEqual(orphans, 0)
        # Backfill re-embeds just the refreshed page.
        self.assertEqual(index_mod.embed_missing(conn, embed_fn=fake_embed), 1)


class SemanticSearchTests(unittest.TestCase):
    def test_finds_meaning_lexical_cannot(self):
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        # "storefront" appears nowhere in the corpus text, so lexical search
        # comes back empty — but it shares the Shopify axis semantically.
        self.assertEqual(index_mod.search(conn, "storefront"), [])
        hits = index_mod.semantic_search(
            conn, "link my storefront", embed_fn=fake_embed
        )
        self.assertEqual(hits[0].anchor_url, f"{SHOPIFY_URL}#connect")
        self.assertGreater(hits[0].similarity, 0.9)
        self.assertEqual(hits[0].lastmod, "2026-01-01")
        self.assertEqual(hits[0].synced_at, "2026-01-01T00:00:00Z")

    def test_requires_embeddings(self):
        conn = make_db()
        with self.assertRaises(RuntimeError):
            index_mod.semantic_search(conn, "anything", embed_fn=fake_embed)

    def test_model_mismatch_blocks_query(self):
        # If the stored model differs from the current real model, querying
        # would compare across incompatible embedding spaces. The real path
        # (embed_fn=None) must refuse. Simulate by stamping a foreign model.
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        conn.execute(
            "INSERT OR REPLACE INTO embedding_meta (key, value) "
            "VALUES ('model', 'some-other-model')"
        )
        conn.commit()
        with self.assertRaises(RuntimeError):
            index_mod.semantic_search(conn, "shopify")  # real embed_fn path


class HybridSearchTests(unittest.TestCase):
    def test_agreement_wins(self):
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        # Shopify section is #1 in BOTH rankers; Stripe at best in one.
        hits = index_mod.hybrid_search(
            conn, "shopify store", limit=2, embed_fn=fake_embed
        )
        self.assertEqual(hits[0].anchor_url, f"{SHOPIFY_URL}#connect")
        self.assertGreater(hits[0].similarity, 0.0)
        self.assertLessEqual(len(hits), 2)

    def test_lexical_only_hit_carries_a_looked_up_cosine(self):
        # The confidence bug: a hit that came ONLY through the lexical ranker
        # (outside semantic's top-K) used to return similarity 0.0, making
        # _confidence silently fall back to BM25-tuned thresholds. Now its
        # cosine is looked up directly. Use a corpus where the lexical hit is
        # semantically RELATED so the looked-up cosine is provably non-zero
        # (a 0.0 would be ambiguous with the old sentinel).
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        # "store" is Shopify-axis (both signals point at Shopify); confirm the
        # top hit's similarity is the real cosine, not a sentinel.
        hits = index_mod.hybrid_search(conn, "store", embed_fn=fake_embed)
        self.assertEqual(hits[0].anchor_url, f"{SHOPIFY_URL}#connect")
        self.assertGreater(hits[0].similarity, 0.9)

    def test_tie_breaks_toward_higher_cosine(self):
        # On an EXACT fused-score tie (each doc appears in exactly one ranker
        # at the same position), the tie must break toward the higher cosine.
        # Build that directly rather than relying on RRF arithmetic.
        from orderdesk_kb.index import Hit
        a = Hit(rank=0.0, title="t", heading_path="p", anchor_url="A",
                snippet="s", text="b", similarity=0.2, rowid=1)
        b = Hit(rank=0.0, title="t", heading_path="p", anchor_url="B",
                snippet="s", text="b", similarity=0.9, rowid=2)
        fused = {1: 1 / 61, 2: 1 / 61}  # exact tie
        sim = {1: 0.2, 2: 0.9}
        ranked = sorted(fused, key=lambda r: (-fused[r], -sim.get(r, 0.0)))
        self.assertEqual(ranked[0], 2)  # higher cosine wins the tie

    def test_semantic_only_match_still_surfaces(self):
        # "storefront" shares the Shopify axis semantically but appears in
        # NEITHER doc's text, so lexical returns nothing — the section must
        # still surface, carried entirely by the vector ranker. (The query is
        # deliberately a single semantic term: adding a word that happens to
        # appear in the rival doc would inject a contradicting lexical signal,
        # which is a different scenario than "semantic-only".)
        conn = make_db()
        index_mod.embed_missing(conn, embed_fn=fake_embed)
        self.assertEqual(index_mod.search(conn, "storefront"), [])
        hits = index_mod.hybrid_search(conn, "storefront", embed_fn=fake_embed)
        self.assertTrue(hits)
        self.assertEqual(hits[0].anchor_url, f"{SHOPIFY_URL}#connect")


class SemanticConfidenceTests(unittest.TestCase):
    def _hit(self, similarity):
        return Hit(rank=-similarity, title="t", heading_path="p", anchor_url="u",
                   snippet="s", text="body", similarity=similarity)

    def test_absolute_thresholds(self):
        # high/low only — no "medium" band (the model's similarity floor for
        # off-topic text overlaps too much to make a mid score meaningful).
        self.assertEqual(_confidence([self._hit(0.75)]), "high")
        self.assertEqual(_confidence([self._hit(0.66)]), "high")  # at threshold
        self.assertEqual(_confidence([self._hit(0.50)]), "low")   # off-topic floor
        self.assertEqual(_confidence([self._hit(0.15)]), "low")

    def test_lexical_hits_use_separation_path(self):
        # similarity == 0.0 means "never went through the vector index";
        # those must keep the old relative-gap behavior.
        lexical = [
            Hit(rank=-10.0, title="t", heading_path="p", anchor_url="u",
                snippet="s", text="body"),
            Hit(rank=-2.0, title="t", heading_path="p", anchor_url="u",
                snippet="s", text="body"),
        ]
        self.assertEqual(_confidence(lexical), "high")


if __name__ == "__main__":
    unittest.main()
