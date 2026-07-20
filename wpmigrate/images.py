"""Image handling: download originals, then (optionally) upload into the WP
media library via the REST API so pages reference real attachments.

Returns a mapping token-index -> MediaResult that the block builder uses to emit
wp:image blocks. A per-URL cache dedupes assets shared across pages.
"""
from __future__ import annotations

import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .extract import ImageRef
from .fetch import Fetcher

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class MediaResult:
    url: str            # URL to reference in the block (new media URL, or source)
    media_id: int | None = None   # WP attachment id when uploaded
    alt: str = ""


def _filename_for(url: str, ctype: str) -> str:
    name = os.path.basename(urlparse(url).path)
    name = unquote(name)
    if not name or "." not in name:
        ext = mimetypes.guess_extension(ctype or "") or ".jpg"
        name = f"image{ext}"
    name = _SAFE.sub("-", name).strip("-")
    return name or "image.jpg"


class ImagePipeline:
    def __init__(self, cfg, fetcher: Fetcher):
        self.cfg = cfg
        self.fetcher = fetcher
        self.cfg.image_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, MediaResult] = {}
        if cfg.image_mode == "upload":
            self._wp = httpx.Client(
                base_url=f"{cfg.wp_base_url}/wp-json/wp/v2",
                auth=(cfg.wp_user, cfg.wp_app_password),
                timeout=cfg.request_timeout,
            )
        else:
            self._wp = None

    def _download(self, url: str) -> tuple[Path, str]:
        content, ctype = self.fetcher.get_bytes(url)
        fname = _filename_for(url, ctype)
        path = self.cfg.image_dir / fname
        # Avoid clobbering distinct assets that share a basename.
        if path.exists() and path.read_bytes() != content:
            stem, suffix = path.stem, path.suffix
            i = 1
            while path.exists() and path.read_bytes() != content:
                path = self.cfg.image_dir / f"{stem}-{i}{suffix}"
                i += 1
        path.write_bytes(content)
        return path, (ctype or mimetypes.guess_type(str(path))[0] or "image/jpeg")

    def _upload(self, path: Path, ctype: str, alt: str) -> MediaResult:
        with open(path, "rb") as fh:
            resp = self._wp.post(
                "/media",
                content=fh.read(),
                headers={
                    "Content-Type": ctype,
                    "Content-Disposition": f'attachment; filename="{path.name}"',
                },
            )
        resp.raise_for_status()
        data = resp.json()
        media_id = data["id"]
        source_url = data["source_url"]
        if alt:
            # Best-effort alt text; ignore failures.
            try:
                self._wp.post(f"/media/{media_id}", json={"alt_text": alt})
            except httpx.HTTPError:
                pass
        return MediaResult(url=source_url, media_id=media_id, alt=alt)

    def process(self, images: list[ImageRef]) -> dict[int, MediaResult]:
        out: dict[int, MediaResult] = {}
        for ref in images:
            if ref.src in self._cache:
                cached = self._cache[ref.src]
                out[ref.index] = MediaResult(
                    url=cached.url, media_id=cached.media_id, alt=ref.alt
                )
                continue
            try:
                if self.cfg.image_mode == "remote":
                    result = MediaResult(url=ref.src, alt=ref.alt)
                else:
                    path, ctype = self._download(ref.src)
                    if self.cfg.image_mode == "upload":
                        result = self._upload(path, ctype, ref.alt)
                    else:  # bundle
                        result = MediaResult(url=path.name, alt=ref.alt)
            except Exception as exc:  # keep the page; skip the broken image
                print(f"    ! image failed ({ref.src}): {exc}")
                result = MediaResult(url=ref.src, alt=ref.alt)
            self._cache[ref.src] = result
            out[ref.index] = result
        return out

    def close(self) -> None:
        if self._wp is not None:
            self._wp.close()
