"""Optional semantic embeddings for the KB index.

Lexical BM25 (index.py) matches the words you typed; it cannot know that
"connect my store" and "Shopify integration" mean the same thing. Embeddings
fix that: each section is mapped to a fixed-length vector such that texts with
similar MEANING land close together, and a query is answered by nearest-vector
lookup (cosine similarity) instead of term overlap.

Design constraints, in priority order:

  1. The core CLI stays zero-dependency. Semantic search is an OPTIONAL extra
     (`pip install -e ".[semantic]"`); without it everything degrades to the
     existing lexical search instead of erroring.
  2. Offline at query time. model2vec "static" embeddings (potion-base-8M,
     ~30 MB) are downloaded once, cached locally, and after that embedding a
     text is a CPU table lookup — no API, no GPU, no network.
  3. `kb.db` stays the single portable artifact: vectors live in an
     `embeddings` table beside the FTS index as little-endian float32 BLOBs.

Static embeddings trade some quality versus a full transformer, but on a
~6,000-section help-docs corpus, hybrid retrieval (BM25 + vectors fused in
index.py) beats either signal alone — and stays fast enough to feel instant.
"""

from __future__ import annotations

import math
import os
import struct

# Keep model loading silent: huggingface_hub otherwise prints a "Fetching N
# files" progress bar that would pollute a caller's output (the agent skill
# parses stdout as JSON). Set before the first hub import so it takes effect.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

# Pinned by name so the index can detect a model change (embedding spaces are
# not compatible across models — mixing them would silently corrupt ranking).
MODEL_NAME = "minishlab/potion-base-8M"

_model = None  # lazy singleton; loading reads ~30 MB from the local HF cache


class EmbedderUnavailable(RuntimeError):
    """Raised when semantic search is requested but the model can't load."""


def is_available() -> bool:
    """True when the optional `semantic` extra (model2vec) is installed."""
    try:
        import model2vec  # noqa: F401

        return True
    except ImportError:
        return False


def get_model():
    """Load the static embedding model once per process."""
    global _model
    if _model is None:
        try:
            from model2vec import StaticModel
        except ImportError as exc:
            raise EmbedderUnavailable(
                "model2vec is not installed — run: pip install -e '.[semantic]'"
            ) from exc
        try:
            _model = StaticModel.from_pretrained(MODEL_NAME)
        except Exception as exc:  # noqa: BLE001 — first run needs one download
            raise EmbedderUnavailable(
                f"could not load {MODEL_NAME} (first use downloads ~30 MB; "
                f"check network): {exc}"
            ) from exc
    return _model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts into unit-length vectors (so dot product == cosine)."""
    model = get_model()
    vectors = model.encode(texts)
    return [_normalize([float(x) for x in vec]) for vec in vectors]


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


# --- BLOB serialization (stdlib only, so lexical-only installs can still
# --- read/inspect the table and tests never need numpy) -----------------


def pack(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack(blob: bytes) -> list[float]:
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


def top_k(
    query_vec: list[float],
    rows: list[tuple[int, bytes]],
    k: int,
) -> list[tuple[int, float]]:
    """Best-first [(section_id, cosine)] for (section_id, vector-blob) rows.

    Vectors are unit-normalized at write time, so cosine is a plain dot
    product. numpy (a model2vec transitive dep) does the whole corpus in one
    matrix multiply; the pure-Python fallback keeps this importable and
    testable without it (~6k x 256 floats is still well under a second).
    """
    if not rows:
        return []
    try:
        import numpy as np

        ids = [section_id for section_id, _ in rows]
        matrix = np.frombuffer(
            b"".join(blob for _, blob in rows), dtype="<f4"
        ).reshape(len(rows), -1)
        sims = matrix @ np.asarray(query_vec, dtype="<f4")
        order = np.argsort(-sims)[:k]
        return [(ids[i], float(sims[i])) for i in order]
    except ImportError:
        scored = [
            (section_id, sum(a * b for a, b in zip(unpack(blob), query_vec)))
            for section_id, blob in rows
        ]
        scored.sort(key=lambda pair: -pair[1])
        return scored[:k]
