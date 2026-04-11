"""
Webhook delivery — fire-and-forget POST on paste read.

Payload (JSON):
  {
    "event":      "paste.read",
    "paste_id":   "abc123",
    "view_count": 1,
    "burned":     false,
    "timestamp":  1712345678
  }

- Non-blocking: runs in a background task, never delays the response.
- Single attempt with a 5s timeout — no retries to avoid hammering.
"""

import asyncio
import json
import time
import urllib.request
from typing import Optional


def fire(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    """Schedule a webhook delivery without awaiting it."""
    asyncio.create_task(_deliver(url, paste_id, view_count, burned))


async def _deliver(
    url: str,
    paste_id: str,
    view_count: int,
    burned: bool,
) -> None:
    payload = json.dumps({
        "event":      "paste.read",
        "paste_id":   paste_id,
        "view_count": view_count,
        "burned":     burned,
        "timestamp":  int(time.time()),
    }).encode()

    try:
        await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None, _post, url, payload
            ),
            timeout=5.0,
        )
    except Exception:
        pass  # Silent fail — never impact the user response


def _post(url: str, payload: bytes) -> None:
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent":   "Ghostbit-Webhook/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        resp.read()
