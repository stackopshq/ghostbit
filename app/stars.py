"""Server-side stargazer count for the footer.

The footer used to fetch api.github.com from the visitor's browser. On a
zero-knowledge paste service that is the wrong shape: it disclosed the IP of
every visitor to GitHub, including someone opening a secret paste link, and it
cost a third-party connection on the critical path of every page load.

The server now fetches the count at most once an hour and renders it into the
page. Deployments with no egress, or self-hosters who want no outbound calls at
all, set GITHUB_REPO="" and the footer simply omits the number.

Uses urllib rather than httpx: httpx is a test-only dependency here, and
webhook.py already establishes stdlib HTTP as the convention for outbound calls.
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request

from .config import settings

log = logging.getLogger(__name__)

_REFRESH_INTERVAL = 3600  # GitHub allows 60 unauthenticated calls/hour/IP
_TIMEOUT = 5

# None means "no number to show": either never fetched, or every attempt
# failed. The template omits the count rather than rendering a misleading 0.
_count: int | None = None


def get_count() -> int | None:
    """Last known stargazer count, or None if unavailable."""
    return _count


def _fetch_blocking(repo: str) -> int | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "ghostbit"},
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:  # noqa: S310 - fixed https host
        data = json.load(r)
    count = data.get("stargazers_count")
    return int(count) if isinstance(count, int) else None


async def _refresh_loop() -> None:
    global _count
    while True:
        try:
            # to_thread so a slow or hanging GitHub never blocks the event loop.
            fetched = await asyncio.to_thread(_fetch_blocking, settings.github_repo)
            if fetched is not None:
                _count = fetched
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
            # Keep the previous value: a stale count beats a disappearing one,
            # and this must never affect serving pastes.
            log.warning("stargazer count refresh failed: %s", e)
        await asyncio.sleep(_REFRESH_INTERVAL)


def start(loop_task_holder: list) -> None:
    """Start the background refresher unless GITHUB_REPO is empty."""
    if not settings.github_repo:
        return
    # Keep a strong reference: bare asyncio tasks can be garbage-collected
    # mid-flight (same reason webhook.py holds its delivery tasks).
    loop_task_holder.append(asyncio.create_task(_refresh_loop()))
