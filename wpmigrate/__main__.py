"""CLI entry point: python -m wpmigrate --urls urls.txt --out export.wxr"""
from __future__ import annotations

import argparse
import sys

from .config import load_config, validate
from .pipeline import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="wpmigrate",
        description="Scrape web pages into a WordPress Gutenberg WXR import file.",
    )
    parser.add_argument("--urls", required=True, help="Path to a text file of URLs (one per line).")
    parser.add_argument("--out", default="export.wxr", help="Output WXR path.")
    parser.add_argument("--config", help="Optional TOML config (selectors, WP creds, etc.).")
    parser.add_argument(
        "--images",
        choices=["upload", "sideload", "bundle", "remote"],
        help="Image handling: upload (REST to media library) / sideload (WXR "
        "attachment items, importer fetches them) / bundle (local) / remote.",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="Render pages with a headless browser (Playwright) so JavaScript "
        "runs before extraction. Needs: pip install -r requirements-render.txt "
        "&& python -m playwright install chromium.",
    )
    args = parser.parse_args(argv)

    cfg = load_config(args.urls, args.out, args.config, args.images,
                      render=True if args.render else None)
    problems = validate(cfg)
    if problems:
        print("Configuration problems:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 2

    succeeded, failed = run(cfg)
    return 0 if succeeded and not failed else (1 if failed else 0)


if __name__ == "__main__":
    raise SystemExit(main())
