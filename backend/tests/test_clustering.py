"""Unit tests for clustering functions.

K-Means / keyword tests are pure NumPy/scikit-learn — no DB or HTTP required.
``generate_cluster_label`` tests use the *responses* library to mock Ollama.
"""
from __future__ import annotations

import numpy as np
import pytest
import responses as rsps_lib

from app.services.clustering import (
    cluster_embeddings,
    extract_keywords,
    get_representative_tickets,
    generate_cluster_label,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_two_group_embeddings(n_per_group: int = 15, dims: int = 8) -> np.ndarray:
    """Return embeddings for 2 clearly-separated clusters."""
    rng = np.random.default_rng(0)
    group_a = rng.standard_normal((n_per_group, dims)) + 10.0
    group_b = rng.standard_normal((n_per_group, dims)) - 10.0
    return np.vstack([group_a, group_b]).astype(np.float32)


def _make_five_group_embeddings(n_per_group: int = 12, dims: int = 16) -> np.ndarray:
    """Return embeddings for 5 clearly-separated clusters."""
    rng = np.random.default_rng(1)
    centres = np.eye(5, dims) * 20.0
    groups = [rng.standard_normal((n_per_group, dims)) * 0.5 + centres[i] for i in range(5)]
    return np.vstack(groups).astype(np.float32)


# ---------------------------------------------------------------------------
# cluster_embeddings
# ---------------------------------------------------------------------------

class TestClusterEmbeddings:
    def test_returns_correct_number_of_labels(self):
        emb = _make_two_group_embeddings()
        labels, centers = cluster_embeddings(emb, 2)
        assert labels.shape == (len(emb),)

    def test_returns_correct_number_of_centers(self):
        emb = _make_two_group_embeddings()
        _, centers = cluster_embeddings(emb, 2)
        assert centers.shape[0] == 2

    def test_two_clear_clusters_are_separated(self):
        emb = _make_two_group_embeddings(n_per_group=15)
        labels, _ = cluster_embeddings(emb, 2)
        # Each half should be in the same cluster
        group_a_labels = set(labels[:15].tolist())
        group_b_labels = set(labels[15:].tolist())
        assert len(group_a_labels) == 1
        assert len(group_b_labels) == 1
        assert group_a_labels != group_b_labels

    def test_requested_cluster_count_is_treated_as_upper_bound(self):
        emb = _make_two_group_embeddings(n_per_group=15)
        labels, centers = cluster_embeddings(emb, 6)
        assert centers.shape[0] == 2
        assert len(set(labels.tolist())) == 2

    def test_num_clusters_capped_at_sample_count(self):
        emb = np.random.default_rng(2).standard_normal((3, 8)).astype(np.float32)
        labels, centers = cluster_embeddings(emb, num_clusters=10)
        assert centers.shape[0] <= 3
        assert len(set(labels.tolist())) <= 3

    def test_five_clusters(self):
        emb = _make_five_group_embeddings()
        labels, centers = cluster_embeddings(emb, 5)
        assert centers.shape[0] == 5
        # All 5 clusters should be populated
        assert len(set(labels.tolist())) == 5

    def test_single_cluster_allowed(self):
        emb = np.random.default_rng(3).standard_normal((5, 4)).astype(np.float32)
        labels, centers = cluster_embeddings(emb, 1)
        assert all(label == 0 for label in labels)
        assert centers.shape[0] == 1

    def test_groups_by_direction_not_vector_magnitude(self):
        emb = np.array(
            [
                [100.0, 0.0],
                [90.0, 0.0],
                [1.0, 0.0],
                [1.1, 0.0],
                [0.0, 1.0],
                [0.0, 1.1],
            ],
            dtype=np.float32,
        )

        labels, _ = cluster_embeddings(emb, 2)

        x_axis_labels = set(labels[:4].tolist())
        y_axis_labels = set(labels[4:].tolist())
        assert len(x_axis_labels) == 1
        assert len(y_axis_labels) == 1
        assert x_axis_labels != y_axis_labels


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
    def test_returns_most_frequent_words(self):
        texts = [
            "login authentication error password reset",
            "login failed authentication token expired",
            "authentication login session invalid",
        ]
        keywords = extract_keywords(texts, top_n=3)
        assert "login" in keywords
        assert "authentication" in keywords

    def test_stop_words_excluded(self):
        texts = ["the quick brown fox jumps over the lazy dog"] * 5
        keywords = extract_keywords(texts, top_n=10)
        for stop in ("the", "over", "and", "is", "for"):
            assert stop not in keywords

    def test_returns_at_most_top_n(self):
        texts = ["one two three four five six seven eight nine ten"] * 3
        assert len(extract_keywords(texts, top_n=5)) <= 5

    def test_empty_input_returns_empty_list(self):
        assert extract_keywords([], top_n=5) == []

    def test_short_words_excluded(self):
        """Words shorter than 3 characters should not appear in keywords."""
        texts = ["to do it by me is on at go we up hi"] * 3
        keywords = extract_keywords(texts, top_n=10)
        for w in keywords:
            assert len(w) >= 3

    def test_case_insensitive(self):
        texts = ["Login FAILED", "login error", "LOGIN timeout"]
        keywords = extract_keywords(texts, top_n=5)
        assert "login" in keywords

    def test_url_noise_excluded(self):
        texts = [
            "https portal login issue on example.com",
            "www.example.com login timeout over https",
        ]
        keywords = extract_keywords(texts, top_n=10)
        for stop in ("https", "www", "com"):
            assert stop not in keywords


# ---------------------------------------------------------------------------
# get_representative_tickets
# ---------------------------------------------------------------------------

class TestGetRepresentativeTickets:
    def _make_fixtures(self, n_per_group: int = 10):
        emb = _make_two_group_embeddings(n_per_group=n_per_group)
        labels, centers = cluster_embeddings(emb, 2)
        tickets = [{"key": f"T-{i}", "summary": f"Ticket {i}"} for i in range(len(emb))]
        return emb, labels, centers, tickets

    def test_returns_correct_number_of_tickets(self):
        emb, labels, centers, tickets = self._make_fixtures()
        rep = get_representative_tickets(emb, labels, centers, tickets, cluster_id=0, top_n=3)
        assert len(rep) <= 3

    def test_returned_tickets_belong_to_cluster(self):
        emb, labels, centers, tickets = self._make_fixtures()
        for cid in (0, 1):
            rep = get_representative_tickets(emb, labels, centers, tickets, cluster_id=cid, top_n=5)
            rep_keys = {r["key"] for r in rep}
            for ticket in rep:
                idx = int(ticket["key"].split("-")[1])
                assert labels[idx] == cid, f"Ticket {ticket['key']} not in cluster {cid}"
            assert rep_keys  # not empty

    def test_empty_cluster_returns_empty_list(self):
        emb = np.ones((5, 4), dtype=np.float32)
        labels = np.zeros(5, dtype=int)  # all in cluster 0
        centers = np.array([[1.0, 1.0, 1.0, 1.0], [10.0, 10.0, 10.0, 10.0]], dtype=np.float32)
        tickets = [{"key": f"T-{i}", "summary": f"Ticket {i}"} for i in range(5)]
        rep = get_representative_tickets(emb, labels, centers, tickets, cluster_id=1, top_n=3)
        assert rep == []

    def test_summary_truncated_to_120_chars(self):
        emb, labels, centers, tickets = self._make_fixtures()
        long_summary = "X" * 200
        for t in tickets:
            t["summary"] = long_summary
        rep = get_representative_tickets(emb, labels, centers, tickets, cluster_id=0, top_n=3)
        for r in rep:
            assert len(r["summary"]) <= 120


# ---------------------------------------------------------------------------
# generate_cluster_label (Ollama LLM)
# ---------------------------------------------------------------------------

class TestGenerateClusterLabel:
    from app.config import settings as _cfg
    _OLLAMA_GENERATE_URL = f"{_cfg.OLLAMA_URL}/api/generate"

    @rsps_lib.activate
    def test_returns_label_from_llm(self):
        rsps_lib.add(
            rsps_lib.POST,
            self._OLLAMA_GENERATE_URL,
            json={"response": "Authentication and Login Failures", "done": True},
            status=200,
        )
        label = generate_cluster_label(["Login fails", "SSO redirect loop"])
        assert label == "Authentication and Login Failures"

    @rsps_lib.activate
    def test_trims_whitespace_and_extra_lines(self):
        rsps_lib.add(
            rsps_lib.POST,
            self._OLLAMA_GENERATE_URL,
            json={"response": "  Slow API Responses  \nExtra line ignored", "done": True},
            status=200,
        )
        label = generate_cluster_label(["Slow query", "Timeout error"])
        assert label == "Slow API Responses"

    @rsps_lib.activate
    def test_raises_on_http_error(self, monkeypatch):
        rsps_lib.add(rsps_lib.POST, self._OLLAMA_GENERATE_URL, status=503)
        monkeypatch.setattr("app.services.ollama.time.sleep", lambda *_args, **_kwargs: None)
        with pytest.raises(Exception):
            generate_cluster_label(["some ticket"])

    @rsps_lib.activate
    def test_retries_transient_http_error(self, monkeypatch):
        rsps_lib.add(rsps_lib.POST, self._OLLAMA_GENERATE_URL, status=503)
        rsps_lib.add(
            rsps_lib.POST,
            self._OLLAMA_GENERATE_URL,
            json={"response": "Release Coordination Work", "done": True},
            status=200,
        )

        delays: list[float] = []
        monkeypatch.setattr("app.services.ollama.time.sleep", lambda seconds: delays.append(seconds))

        label = generate_cluster_label(["Coordinate the release checklist"])

        assert label == "Release Coordination Work"
        assert delays == [self._cfg.OLLAMA_RETRY_INITIAL_BACKOFF_SECONDS]

    @rsps_lib.activate
    def test_raises_on_empty_response(self):
        rsps_lib.add(
            rsps_lib.POST,
            self._OLLAMA_GENERATE_URL,
            json={"response": "", "done": True},
            status=200,
        )
        with pytest.raises(ValueError, match="empty"):
            generate_cluster_label(["some ticket"])

    @rsps_lib.activate
    def test_uses_at_most_five_tickets(self):
        """Only the first 5 summaries should appear in the prompt."""
        rsps_lib.add(
            rsps_lib.POST,
            self._OLLAMA_GENERATE_URL,
            json={"response": "UI Layout Bugs", "done": True},
            status=200,
        )
        summaries = [f"Ticket {i}" for i in range(10)]
        generate_cluster_label(summaries)

        import json
        body = json.loads(rsps_lib.calls[0].request.body)
        prompt = body["prompt"]
        # Summaries 0-4 must appear; summary 5 must not
        for i in range(5):
            assert f"Ticket {i}" in prompt
        assert "Ticket 5" not in prompt
