import logging
from typing import List

import numpy as np
import requests as http

from ..config import settings

logger = logging.getLogger(__name__)


def generate_embeddings(texts: List[str]) -> np.ndarray:
    """Return an (N, EMBED_DIM) float32 array using the Ollama /api/embed endpoint.

    Sends the whole batch in one request; Ollama processes them efficiently
    and returns ``{"embeddings": [[...], ...]}``.
    """
    url = f"{settings.OLLAMA_URL}/api/embed"
    logger.info(
        "Generating embeddings for %d texts via Ollama model '%s' …",
        len(texts),
        settings.OLLAMA_EMBED_MODEL,
    )
    resp = http.post(
        url,
        json={"model": settings.OLLAMA_EMBED_MODEL, "input": texts},
        timeout=300,  # large batches may take a while
    )
    resp.raise_for_status()
    data = resp.json()

    if "embeddings" not in data:
        raise ValueError(
            f"Ollama /api/embed returned unexpected payload (no 'embeddings' key): {data}"
        )

    vectors = np.array(data["embeddings"], dtype=np.float32)
    logger.info("Embeddings generated: shape=%s", vectors.shape)
    return vectors
