"""Polite HTTP fetching: per-host rate limiting, retries, sane timeouts."""
from __future__ import annotations

import time
from urllib.parse import urlparse

import httpx


class Fetcher:
    def __init__(self, user_agent: str, timeout: float, rate_limit_seconds: float):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
        )
        self._rate_limit = rate_limit_seconds
        self._last_hit: dict[str, float] = {}

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self._rate_limit - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def get_html(self, url: str, retries: int = 3) -> str:
        """Fetch a page as text. Raises on persistent failure."""
        self._throttle(url)
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPError,) as exc:  # includes timeouts, status errors
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch {url}: {last_exc}")

    def get_bytes(self, url: str, retries: int = 3) -> tuple[bytes, str]:
        """Fetch a binary asset. Returns (content, content_type)."""
        self._throttle(url)
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                ctype = resp.headers.get("content-type", "").split(";")[0].strip()
                return resp.content, ctype
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Failed to fetch asset {url}: {last_exc}")

    def close(self) -> None:
        self._client.close()
