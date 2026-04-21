import logging
import time
from typing import Any

import requests as http

from ..config import settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})


def _format_response_error(response: http.Response) -> str:
    body = response.text.strip()
    if not body:
        return f"HTTP {response.status_code}"
    if len(body) > 200:
        body = body[:197].rstrip() + "..."
    return f"HTTP {response.status_code}: {body}"


def post_ollama_json(
    path: str,
    payload: dict[str, Any],
    *,
    timeout: int,
    operation: str,
) -> dict[str, Any]:
    url = f"{settings.OLLAMA_URL}{path}"
    max_attempts = max(1, settings.OLLAMA_RETRY_ATTEMPTS)
    delay_seconds = max(0.0, settings.OLLAMA_RETRY_INITIAL_BACKOFF_SECONDS)

    for attempt in range(1, max_attempts + 1):
        try:
            response = http.post(url, json=payload, timeout=timeout)
        except (http.Timeout, http.ConnectionError) as exc:
            if attempt >= max_attempts:
                raise
            logger.warning(
                "Ollama %s attempt %d/%d failed: %s. Retrying in %.1fs.",
                operation,
                attempt,
                max_attempts,
                exc,
                delay_seconds,
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            delay_seconds = min(
                max(delay_seconds, 0.0) * settings.OLLAMA_RETRY_BACKOFF_MULTIPLIER,
                settings.OLLAMA_RETRY_MAX_BACKOFF_SECONDS,
            )
            continue
        except http.RequestException:
            raise

        try:
            response.raise_for_status()
        except http.HTTPError:
            if response.status_code not in _RETRYABLE_STATUS_CODES or attempt >= max_attempts:
                raise
            logger.warning(
                "Ollama %s attempt %d/%d failed: %s. Retrying in %.1fs.",
                operation,
                attempt,
                max_attempts,
                _format_response_error(response),
                delay_seconds,
            )
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            delay_seconds = min(
                max(delay_seconds, 0.0) * settings.OLLAMA_RETRY_BACKOFF_MULTIPLIER,
                settings.OLLAMA_RETRY_MAX_BACKOFF_SECONDS,
            )
            continue

        return response.json()

    raise RuntimeError(f"Ollama {operation} exhausted retry attempts without returning a response")