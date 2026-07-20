"""Orchestrate the full migration: URLs in, WXR out."""
from __future__ import annotations

from pathlib import Path

import anthropic

from . import blocks, clean_llm, extract as extract_mod, wxr
from .config import Config
from .fetch import Fetcher
from .images import ImagePipeline


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def run(cfg: Config) -> tuple[int, int]:
    """Run the pipeline. Returns (succeeded, failed) page counts."""
    urls = read_urls(cfg.urls_file)
    print(f"Loaded {len(urls)} URL(s). Model: {cfg.model}. Images: {cfg.image_mode}.")

    fetcher = Fetcher(cfg.user_agent, cfg.request_timeout, cfg.rate_limit_seconds)
    images = ImagePipeline(cfg, fetcher)
    client = anthropic.Anthropic()

    pages: list[wxr.Page] = []
    failed = 0

    try:
        for i, url in enumerate(urls, start=1):
            print(f"[{i}/{len(urls)}] {url}")
            try:
                raw = fetcher.get_html(url)
                ex = extract_mod.extract(raw, url, cfg.selectors)
                if not ex.html.strip():
                    print("    ! no main content extracted; skipping")
                    failed += 1
                    continue
                print(f"    title: {ex.title!r}  images: {len(ex.images)}")

                media_map = images.process(ex.images)
                cleaned = clean_llm.clean(client, cfg, ex.title, ex.html)
                block_markup = blocks.to_blocks(cleaned, media_map)
                if not block_markup.strip():
                    print("    ! empty after conversion; skipping")
                    failed += 1
                    continue

                pages.append(
                    wxr.Page(title=ex.title, link=url, content_blocks=block_markup)
                )
                print("    ok")
            except Exception as exc:
                print(f"    ! failed: {exc}")
                failed += 1
    finally:
        images.close()
        fetcher.close()

    if pages:
        doc = wxr.build_wxr(
            pages,
            author=cfg.author,
            post_type=cfg.post_type,
            status=cfg.post_status,
        )
        cfg.out_file.write_text(doc, encoding="utf-8")
        print(f"\nWrote {len(pages)} page(s) to {cfg.out_file}")
    else:
        print("\nNo pages succeeded; no WXR written.")

    return len(pages), failed
