import logging
from typing import List

import numpy as np

logger = logging.getLogger(__name__)

_model = None
_MODEL_NAME = "BAAI/bge-small-en-v1.5"


def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding  # lazy import — heavy module

        logger.info("Loading embedding model %s …", _MODEL_NAME)
        _model = TextEmbedding(_MODEL_NAME)
        logger.info("Embedding model loaded.")
    return _model


def generate_embeddings(texts: List[str]) -> np.ndarray:
    """Return an (N, 384) float32 numpy array of embeddings."""
    model = _get_model()
    embeddings = list(model.embed(texts))
    return np.array(embeddings, dtype=np.float32)
