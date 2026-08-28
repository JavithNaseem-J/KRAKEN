from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx


def _failure_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"status {response.status_code}"

    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            code = error.get("code") or error.get("type") or "provider_error"
            message = str(error.get("message") or "").strip()
            return f"status {response.status_code}: {code}" + (
                f" ({message[:120]})" if message else ""
            )
        detail = body.get("detail") or body.get("message")
        if detail:
            return f"status {response.status_code}: {str(detail)[:120]}"
    return f"status {response.status_code}"


async def probe_chat_completion(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    api_key: str,
    models: Sequence[str],
    timeout_seconds: float,
) -> tuple[bool, str | None]:
    """Verify that at least one configured OpenAI-compatible chat model can compose."""
    clean_models = [model.strip() for model in models if model and model.strip()]
    if not api_key.strip():
        return False, "not configured"
    if not clean_models:
        return False, "no model configured"

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    failures: list[str] = []
    for model in clean_models:
        try:
            response = await client.post(
                endpoint,
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Reply with KRAKEN_OK only."},
                        {"role": "user", "content": "health"},
                    ],
                    "temperature": 0,
                    "max_tokens": 32,
                },
                timeout=timeout_seconds,
            )
        except Exception as exc:
            failures.append(f"{model}: {exc.__class__.__name__}")
            continue

        if response.status_code != 200:
            failures.append(f"{model}: {_failure_detail(response)}")
            continue

        try:
            payload: dict[str, Any] = response.json()
        except ValueError:
            failures.append(f"{model}: non-json response")
            continue

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                return True, None
        failures.append(f"{model}: empty completion")

    return False, "; ".join(failures[:3]) or "provider unavailable"
