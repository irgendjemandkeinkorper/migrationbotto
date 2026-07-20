"""Headless-browser fetching via Playwright, for JavaScript-rendered pages.

`PlaywrightFetcher` is a drop-in replacement for `Fetcher`: it exposes the same
`get_html` / `get_bytes` / `close` surface, so the pipeline doesn't change. The
difference is `get_html` loads the page in headless Chromium, runs its
JavaScript, scrolls to trigger lazy-loaded content, waits for the network to
settle, then returns the fully-rendered DOM. Images (`get_bytes`) still go over
plain HTTP — they don't need a browser.

Playwright is an optional dependency. It's imported lazily so the rest of the
tool works without it; if `--render` is used without it installed, the user gets
a clear install hint.
"""
from __future__ import annotations

import time
from urllib.parse import urlparse

from .fetch import Fetcher

_INSTALL_HINT = (
    "Playwright is required for --render. Install it with:\n"
    "    pip install -r requirements-render.txt\n"
    "    python -m playwright install chromium"
)


class PlaywrightFetcher:
    def __init__(
        self,
        user_agent: str,
        timeout: float,
        rate_limit_seconds: float,
        *,
        wait_ms: int = 1500,
        scroll: bool = True,
        max_scrolls: int = 30,
    ):
        # Plain-HTTP client handles image bytes (and gives a clear error surface).
        self._http = Fetcher(user_agent, timeout, rate_limit_seconds)
        self._ua = user_agent
        self._timeout_ms = int(timeout * 1000)
        self._networkidle_ms = min(self._timeout_ms, 15000)
        self._rate_limit = rate_limit_seconds
        self._wait_ms = wait_ms
        self._scroll = scroll
        self._max_scrolls = max_scrolls
        self._last_hit: dict[str, float] = {}
        self._pw = None
        self._browser = None
        self._context = None

    # -- lazy browser startup -------------------------------------------------
    def _ensure_browser(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(_INSTALL_HINT) from exc
        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:  # browser binary missing, etc.
            raise RuntimeError(f"{_INSTALL_HINT}\n\n(underlying error: {exc})") from exc
        self._context = self._browser.new_context(
            user_agent=self._ua,
            viewport={"width": 1440, "height": 900},
        )

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self._rate_limit - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _auto_scroll(self, page) -> None:
        """Scroll to the bottom in steps so lazy-loaded content/images fire."""
        try:
            prev = 0
            for _ in range(self._max_scrolls):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(400)
                height = page.evaluate("() => document.body.scrollHeight")
                if height <= prev:
                    break
                prev = height
            page.evaluate("window.scrollTo(0, 0)")
        except Exception:
            pass  # scrolling is best-effort; never fail the fetch over it

    # -- Fetcher-compatible surface ------------------------------------------
    def get_html(self, url: str, retries: int = 2) -> str:
        self._ensure_browser()
        self._throttle(url)
        last_exc: Exception | None = None
        for attempt in range(retries):
            page = self._context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
                try:
                    page.wait_for_load_state("networkidle", timeout=self._networkidle_ms)
                except Exception:
                    pass  # some sites never go fully idle; proceed anyway
                if self._scroll:
                    self._auto_scroll(page)
                if self._wait_ms:
                    page.wait_for_timeout(self._wait_ms)
                return page.content()
            except Exception as exc:
                last_exc = exc
            finally:
                page.close()
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Playwright failed to render {url}: {last_exc}")

    def get_bytes(self, url: str, retries: int = 3) -> tuple[bytes, str]:
        return self._http.get_bytes(url, retries=retries)

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
            if self._pw is not None:
                self._pw.stop()
        finally:
            self._http.close()
