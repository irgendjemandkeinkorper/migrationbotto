"""Orchestrate the full migration: URLs in, WXR out.

`run()` optionally takes a `progress` callback so a UI (or any caller) can watch
the migration live. Events are plain dicts:
  {"type": "start",  "total": N}
  {"type": "page",   "index": i, "total": N, "url": u,
                     "status": "ok"|"failed"|"skipped", "title": t,
                     "images": k, "message": str}
  {"type": "done",   "succeeded": s, "failed": f}
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import anthropic

from . import blocks, clean_llm, extract as extract_mod, wxr
from .config import Config
from .fetch import Fetcher
from .images import ImagePipeline

Progress = Callable[[dict], None]


def read_urls(path: Path) -> list[tuple[str, str | None]]:
    """Read the URL list. Each line is a URL, optionally followed by
    ` | Title` to force the page title (useful for pages whose markup has no
    usable heading, so auto-detection would fall back to a generic <title>)."""
    urls: list[tuple[str, str | None]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, sep, title = line.partition("|")
        urls.append((url.strip(), title.strip() if sep else None))
    return urls


def _emit(progress: Progress | None, event: dict) -> None:
    if progress is not None:
        progress(event)


def run(cfg: Config, progress: Progress | None = None) -> tuple[int, int]:
    """Run the pipeline. Returns (succeeded, failed) page counts."""
    urls = read_urls(cfg.urls_file)
    total = len(urls)
    mode = "playwright" if cfg.render else "static"
    print(f"Loaded {total} URL(s). Model: {cfg.model}. Images: {cfg.image_mode}. "
          f"Fetch: {mode}.")
    _emit(progress, {"type": "start", "total": total})

    if cfg.render:
        from .render import PlaywrightFetcher
        fetcher = PlaywrightFetcher(
            cfg.user_agent, cfg.request_timeout, cfg.rate_limit_seconds,
            wait_ms=cfg.render_wait_ms, scroll=cfg.render_scroll,
        )
    else:
        fetcher = Fetcher(cfg.user_agent, cfg.request_timeout, cfg.rate_limit_seconds)
    images = ImagePipeline(cfg, fetcher)
    client = anthropic.Anthropic()

    pages: list[wxr.Page] = []
    failed = 0

    try:
        for i, (url, title_override) in enumerate(urls, start=1):
            print(f"[{i}/{total}] {url}")
            try:
                raw = fetcher.get_html(url)
                ex = extract_mod.extract(raw, url, cfg.selectors, title_override)
                if not ex.html.strip():
                    print("    ! no main content extracted; skipping")
                    failed += 1
                    _emit(progress, {"type": "page", "index": i, "total": total,
                                     "url": url, "status": "skipped",
                                     "message": "no main content extracted"})
                    continue

                media_map = images.process(ex.images)
                cleaned = clean_llm.clean(client, cfg, ex.title, ex.html)
                block_markup = blocks.to_blocks(cleaned, media_map)
                if not block_markup.strip():
                    print("    ! empty after conversion; skipping")
                    failed += 1
                    _emit(progress, {"type": "page", "index": i, "total": total,
                                     "url": url, "status": "skipped",
                                     "message": "empty after conversion"})
                    continue

                page_images = (
                    [(img.src, img.alt) for img in ex.images]
                    if cfg.image_mode == "sideload"
                    else []
                )
                pages.append(
                    wxr.Page(title=ex.title, link=url,
                             content_blocks=block_markup, images=page_images)
                )
                print("    ok")
                _emit(progress, {"type": "page", "index": i, "total": total,
                                 "url": url, "status": "ok", "title": ex.title,
                                 "images": len(ex.images)})
            except Exception as exc:
                print(f"    ! failed: {exc}")
                failed += 1
                _emit(progress, {"type": "page", "index": i, "total": total,
                                 "url": url, "status": "failed",
                                 "message": str(exc)})
    finally:
        images.close()
        fetcher.close()

    if pages:
        doc = wxr.build_wxr(
            pages,
            author=cfg.author,
            post_type=cfg.post_type,
            status=cfg.post_status,
            emit_attachments=(cfg.image_mode == "sideload"),
        )
        cfg.out_file.write_text(doc, encoding="utf-8")
        print(f"\nWrote {len(pages)} page(s) to {cfg.out_file}")
    else:
        print("\nNo pages succeeded; no WXR written.")

    _emit(progress, {"type": "done", "succeeded": len(pages), "failed": failed})
    return len(pages), failed
