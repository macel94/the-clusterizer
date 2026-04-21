import re
from collections import Counter
from typing import Dict, List, Tuple

import numpy as np
import requests as http
from sklearn.cluster import KMeans

_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "as", "by", "at", "from", "into", "through", "during",
    "and", "or", "but", "not", "this", "that", "these", "those", "it",
    "its", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "nor", "so", "yet", "either", "neither", "once", "upon",
    "after", "before", "above", "below", "between", "while", "if", "then",
    "than", "also", "just", "up", "out", "about", "over", "us", "we",
    "our", "you", "your", "my", "me", "he", "she", "they", "them", "their",
    "i", "his", "her", "any", "what", "there", "here", "get", "got",
    "using", "use", "used", "new", "need", "needs", "please", "per",
}

# Fixed random seed for reproducible cluster results across runs
_KMEANS_RANDOM_SEED = 42


def cluster_embeddings(
    embeddings: np.ndarray, num_clusters: int
) -> Tuple[np.ndarray, np.ndarray]:
    """Run K-means and return (labels, cluster_centers)."""
    actual = min(num_clusters, len(embeddings))
    kmeans = KMeans(n_clusters=actual, random_state=_KMEANS_RANDOM_SEED, n_init=10)
    labels = kmeans.fit_predict(embeddings)
    return labels, kmeans.cluster_centers_


def extract_keywords(texts: List[str], top_n: int = 5) -> List[str]:
    """Return the *top_n* most frequent non-stop words across *texts*."""
    counts: Counter = Counter()
    for text in texts:
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        for word in words:
            if word not in _STOP_WORDS:
                counts[word] += 1
    return [w for w, _ in counts.most_common(top_n)]


def get_representative_tickets(
    embeddings: np.ndarray,
    cluster_labels: np.ndarray,
    cluster_centers: np.ndarray,
    tickets: List[Dict],
    cluster_id: int,
    top_n: int = 3,
) -> List[Dict]:
    """Return the *top_n* tickets closest to the cluster centroid."""
    indices = np.where(cluster_labels == cluster_id)[0]
    if len(indices) == 0:
        return []
    distances = np.linalg.norm(embeddings[indices] - cluster_centers[cluster_id], axis=1)
    closest = indices[np.argsort(distances)[:top_n]]
    return [
        {"key": tickets[i]["key"], "summary": tickets[i]["summary"][:120]}
        for i in closest
    ]


def generate_cluster_label(ticket_summaries: List[str]) -> str:
    """Ask the Ollama LLM to produce a short, descriptive cluster label.

    Sends up to the 5 most representative ticket titles to the model and asks
    for a 3–7 word label.  Raises on any HTTP or parsing error so the caller
    can fall back to keyword-based labelling.
    """
    from ..config import settings  # late import to keep module import-time cheap

    sample = ticket_summaries[:5]
    prompt = (
        "You are a technical project manager.\n"
        "Read the following Jira ticket titles and write a short label "
        "(3 to 7 words) that captures their common theme.\n"
        "Reply with ONLY the label — no explanation, no punctuation.\n\n"
        "Tickets:\n"
        + "\n".join(f"- {s}" for s in sample)
        + "\n\nLabel:"
    )
    resp = http.post(
        f"{settings.OLLAMA_URL}/api/generate",
        json={"model": settings.OLLAMA_LLM_MODEL, "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    label = resp.json().get("response", "").strip()
    if not label:
        raise ValueError("Ollama returned an empty label")
    # Trim to a single line in case the model adds extras
    return label.splitlines()[0].strip()
