"""Dashboard API transport. Short timeouts and actionable errors."""

import os

import httpx


def call(method: str, path: str, **kwargs):
    base = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
    try:
        response = httpx.request(
            method, base + path, timeout=35 if path == "/creative/draft" else 15, **kwargs
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", "Request failed")
        raise RuntimeError(f"API {exc.response.status_code}: {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            "API unavailable. Start uvicorn paid_media.api:app --port 8000, then refresh."
        ) from exc
