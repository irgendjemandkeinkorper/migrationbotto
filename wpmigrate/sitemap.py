"""Discover page URLs from an XML sitemap.

Handles both <urlset> (a flat list of pages) and <sitemapindex> (a list of
child sitemaps, which we recurse into). Gzipped sitemaps (.xml.gz) are supported.
Namespaces are ignored by matching on the tag's local name, so slightly
non-standard sitemaps still parse.
"""
from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET

from .fetch import Fetcher

MAX_SITEMAPS = 50       # guard against runaway sitemap-index recursion
MAX_URLS = 5000         # overall cap on discovered page URLs


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _maybe_gunzip(url: str, content: bytes) -> bytes:
    if url.endswith(".gz") or content[:2] == b"\x1f\x8b":
        try:
            return gzip.decompress(content)
        except OSError:
            return content
    return content


def _parse(content: bytes) -> tuple[str, list[str]]:
    """Return (root_localname, [loc strings])."""
    root = ET.fromstring(content)
    locs: list[str] = []
    for el in root.iter():
        if _localname(el.tag) == "loc" and el.text:
            locs.append(el.text.strip())
    return _localname(root.tag), locs


def discover(fetcher: Fetcher, sitemap_url: str) -> list[str]:
    """Return a de-duplicated, ordered list of page URLs from a sitemap.

    If `sitemap_url` is a sitemap index, its child sitemaps are fetched too.
    """
    seen_sitemaps: set[str] = set()
    out: list[str] = []
    seen_urls: set[str] = set()
    queue: list[str] = [sitemap_url]

    while queue and len(seen_sitemaps) < MAX_SITEMAPS and len(out) < MAX_URLS:
        current = queue.pop(0)
        if current in seen_sitemaps:
            continue
        seen_sitemaps.add(current)

        content, _ = fetcher.get_bytes(current)
        content = _maybe_gunzip(current, content)
        try:
            root_name, locs = _parse(content)
        except ET.ParseError as exc:
            raise RuntimeError(f"Could not parse sitemap {current}: {exc}") from exc

        if root_name == "sitemapindex":
            # Children are more sitemaps; queue them.
            for loc in locs:
                if loc not in seen_sitemaps:
                    queue.append(loc)
        else:
            # urlset (or anything else with <loc>): treat as page URLs.
            for loc in locs:
                if loc not in seen_urls:
                    seen_urls.add(loc)
                    out.append(loc)
                    if len(out) >= MAX_URLS:
                        break

    return out
