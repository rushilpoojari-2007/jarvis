from __future__ import annotations

from itertools import count

import httpx

from app.config import settings

_key_rotation = count()


async def summarize_text(text: str, max_items: int = 5) -> str:
    if not settings.NVIDIA_API_KEYS:
        return "AI summary unavailable: NVIDIA API key is not configured."

    payload = {
        "model": settings.NVIDIA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are JARVIS. Write a concise daily briefing from the supplied weather and news data. "
                    f"Use no more than {max_items} headlines. Mention the weather and summarize the most useful "
                    "news in 2-3 short sentences. Use only the supplied facts; do not greet the user or ask a question. "
                    "If data is unavailable, say so briefly."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create today's briefing in 2-3 sentences using the weather and up to {max_items} headlines below. "
                    "Include concrete details from the data, with no greeting or follow-up question.\n\n"
                    f"DATA:\n{text[:8000]}"
                ),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 200,
    }
    if settings.NVIDIA_MODEL.startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    else:
        payload["reasoning_budget"] = 64

    try:
        async with httpx.AsyncClient(timeout=settings.NVIDIA_TIMEOUT_SECONDS) as client:
            keys = settings.NVIDIA_API_KEYS
            first_key = next(_key_rotation) % len(keys)
            last_error = ""
            for offset in range(len(keys)):
                api_key = keys[(first_key + offset) % len(keys)]
                try:
                    response = await client.post(
                        f"{settings.NVIDIA_BASE_URL.rstrip('/')}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=payload,
                    )
                except httpx.HTTPError as exc:
                    last_error = f"network error ({type(exc).__name__})"
                    # A network failure is independent of the key; avoid serial
                    # timeout waits for every fallback key.
                    break

                if response.status_code != 200:
                    last_error = f"provider returned HTTP {response.status_code}"
                    if response.status_code in {401, 403, 404, 408, 409, 425, 429} or response.status_code >= 500:
                        continue
                    return f"AI summary unavailable: {last_error}."

                try:
                    content = response.json()
                except ValueError:
                    last_error = "provider returned invalid JSON"
                    continue
                if not isinstance(content, dict):
                    last_error = "provider returned an invalid response"
                    continue
                choices = content.get("choices") or []
                if not choices:
                    last_error = "provider returned an empty response"
                    continue

                choice = choices[0]
                if not isinstance(choice, dict):
                    last_error = "provider returned an invalid choice"
                    continue
                message = choice.get("message") or {}
                if not isinstance(message, dict):
                    last_error = "provider returned an invalid message"
                    continue
                result = message.get("content")
                if isinstance(result, list):
                    result = "".join(
                        part["text"]
                        for part in result
                        if isinstance(part, dict) and isinstance(part.get("text"), str)
                    )
                if isinstance(result, str):
                    if result.strip():
                        return result.strip()
                last_error = "provider returned no user-facing content"

            return f"AI summary unavailable: all configured provider keys failed ({last_error})."
    except httpx.HTTPError as exc:
        return f"AI summary unavailable: network error ({type(exc).__name__})."
