import logging
from typing import Callable, List, Optional

import numpy as np

from ..config import settings
from .ollama import post_ollama_json

logger = logging.getLogger(__name__)


def generate_embeddings(
    texts: List[str],
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> np.ndarray:
    """Return an (N, EMBED_DIM) float32 array using the Ollama /api/embed endpoint.

    Splits requests into smaller batches so progress can be surfaced while an
    analysis runs and transient Ollama failures can be retried per batch.
    """
    if not texts:
        return np.empty((0, settings.OLLAMA_EMBED_DIM), dtype=np.float32)

    batch_size = max(1, settings.OLLAMA_EMBED_BATCH_SIZE)
    logger.info(
        "Generating embeddings for %d texts via Ollama model '%s' in batches of %d …",
        len(texts),
        settings.OLLAMA_EMBED_MODEL,
        batch_size,
    )
    vectors_by_batch: list[np.ndarray] = []
    total = len(texts)

    for start in range(0, total, batch_size):
        batch = texts[start:start + batch_size]
        batch_number = start // batch_size + 1
        data = post_ollama_json(
            "/api/embed",
            {"model": settings.OLLAMA_EMBED_MODEL, "input": batch},
            timeout=300,
            operation=f"embedding batch {batch_number}",
        )

        if "embeddings" not in data:
            raise ValueError(
                f"Ollama /api/embed returned unexpected payload (no 'embeddings' key): {data}"
            )

        batch_vectors = np.array(data["embeddings"], dtype=np.float32)
        if batch_vectors.shape[0] != len(batch):
            raise ValueError(
                "Ollama /api/embed returned an unexpected number of embeddings "
                f"for batch {batch_number}: expected {len(batch)}, got {batch_vectors.shape[0]}"
            )

        vectors_by_batch.append(batch_vectors)

        if progress_callback is not None:
            progress_callback(min(start + len(batch), total), total)

    vectors = np.vstack(vectors_by_batch)
    logger.info("Embeddings generated: shape=%s", vectors.shape)
    return vectors
