"""Unit tests for the Ollama embedding service.

All HTTP calls are intercepted with the *responses* library so no real
Ollama instance is required.
"""
from __future__ import annotations

import numpy as np
import pytest
import responses as rsps_lib

from app.config import settings

OLLAMA_EMBED_URL = f"{settings.OLLAMA_URL}/api/embed"


def _make_payload(n: int) -> dict:
    """Return a synthetic /api/embed response for *n* texts."""
    rng = np.random.default_rng(0)
    vecs = rng.standard_normal((n, settings.OLLAMA_EMBED_DIM)).tolist()
    return {"model": settings.OLLAMA_EMBED_MODEL, "embeddings": vecs}


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_generate_embeddings_returns_correct_shape():
    texts = ["hello world", "authentication failed", "database timeout"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, json=_make_payload(len(texts)), status=200)

    from app.services.embeddings import generate_embeddings
    result = generate_embeddings(texts)

    assert isinstance(result, np.ndarray)
    assert result.shape == (len(texts), settings.OLLAMA_EMBED_DIM)
    assert result.dtype == np.float32


@rsps_lib.activate
def test_generate_embeddings_single_text():
    texts = ["only one ticket"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, json=_make_payload(1), status=200)

    from app.services.embeddings import generate_embeddings
    result = generate_embeddings(texts)

    assert result.shape == (1, settings.OLLAMA_EMBED_DIM)


@rsps_lib.activate
def test_generate_embeddings_sends_correct_payload():
    """The request body must include the model name and all input texts."""
    texts = ["ticket A", "ticket B"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, json=_make_payload(2), status=200)

    from app.services.embeddings import generate_embeddings
    generate_embeddings(texts)

    req_body = rsps_lib.calls[0].request.body
    import json
    body = json.loads(req_body)
    assert body["model"] == settings.OLLAMA_EMBED_MODEL
    assert body["input"] == texts


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_generate_embeddings_raises_on_http_error(monkeypatch):
    texts = ["some text"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, status=500)
    monkeypatch.setattr("app.services.ollama.time.sleep", lambda *_args, **_kwargs: None)

    from app.services.embeddings import generate_embeddings
    with pytest.raises(Exception):
        generate_embeddings(texts)


@rsps_lib.activate
def test_generate_embeddings_retries_transient_http_error(monkeypatch):
    texts = ["ticket A", "ticket B"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, status=503)
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL, json=_make_payload(2), status=200)

    delays: list[float] = []
    monkeypatch.setattr("app.services.ollama.time.sleep", lambda seconds: delays.append(seconds))

    from app.services.embeddings import generate_embeddings

    result = generate_embeddings(texts)

    assert result.shape == (2, settings.OLLAMA_EMBED_DIM)
    assert delays == [settings.OLLAMA_RETRY_INITIAL_BACKOFF_SECONDS]


@rsps_lib.activate
def test_generate_embeddings_raises_on_missing_embeddings_key():
    """If Ollama returns JSON without 'embeddings', a ValueError should be raised."""
    texts = ["some text"]
    rsps_lib.add(rsps_lib.POST, OLLAMA_EMBED_URL,
                 json={"error": "model not found"}, status=200)

    from app.services.embeddings import generate_embeddings
    with pytest.raises(ValueError, match="embeddings"):
        generate_embeddings(texts)
