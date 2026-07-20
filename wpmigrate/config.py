"""Runtime configuration, loaded from CLI args, env vars, and an optional TOML file.

Secrets (WordPress application password, Anthropic key) come from the environment
only — never from the config file or CLI, so they don't end up in shell history
or version control.
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# The claude-api skill's standing instruction is to default to Opus 4.8 and let
# the user opt into a cheaper model explicitly (WPMIGRATE_MODEL) rather than
# downgrading for cost automatically.
DEFAULT_MODEL = "claude-opus-4-8"


@dataclass
class Config:
    # --- source ---
    urls_file: Path
    # Per-domain CSS selector overrides for the main content area, e.g.
    # {"example.com": "article.post-body"}. When a page's host matches, we take
    # that node's inner HTML instead of trusting trafilatura's auto-extraction.
    selectors: dict[str, str] = field(default_factory=dict)

    # --- output ---
    out_file: Path = Path("export.wxr")
    image_dir: Path = Path("images_cache")
    post_type: str = "page"          # "page" or "post"
    post_status: str = "publish"     # "publish" | "draft" | "pending"
    author: str = "admin"            # dc:creator / wp:post_author login

    # --- images ---
    # "upload"   -> download then POST to the WP media library (needs WP creds)
    # "sideload" -> emit WXR attachment items; the WP importer fetches each
    #               image server-side on import (no REST needed — works against
    #               managed hosts that block the REST API)
    # "bundle"   -> download into image_dir, reference local files (no upload)
    # "remote"   -> leave source URLs inline; no attachment items
    image_mode: str = "upload"

    # --- WordPress REST (only needed for image_mode == "upload") ---
    wp_base_url: str = ""            # e.g. https://your-site.com
    wp_user: str = ""
    wp_app_password: str = ""        # from env WP_APP_PASSWORD

    # --- LLM ---
    model: str = DEFAULT_MODEL
    effort: str = "medium"           # low | medium | high | max
    llm_max_tokens: int = 32000

    # --- fetching ---
    request_timeout: float = 30.0
    rate_limit_seconds: float = 1.0  # min delay between requests to the same host
    user_agent: str = (
        "wp-migrator/0.1 (+content migration tool)"
    )

    @property
    def anthropic_key(self) -> str:
        # The SDK also resolves this itself; surfaced here only for a clear
        # up-front error message.
        return os.environ.get("ANTHROPIC_API_KEY", "")


def load_config(
    urls_file: str,
    out_file: str,
    config_path: str | None,
    image_mode: str | None,
) -> Config:
    data: dict = {}
    if config_path:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)

    cfg = Config(
        urls_file=Path(urls_file),
        out_file=Path(out_file),
        selectors=data.get("selectors", {}),
        image_dir=Path(data.get("image_dir", "images_cache")),
        post_type=data.get("post_type", "page"),
        post_status=data.get("post_status", "publish"),
        author=data.get("author", "admin"),
        image_mode=image_mode or data.get("image_mode", "upload"),
        wp_base_url=(data.get("wp_base_url", "")).rstrip("/"),
        wp_user=data.get("wp_user", ""),
        wp_app_password=os.environ.get("WP_APP_PASSWORD", ""),
        model=os.environ.get("WPMIGRATE_MODEL", data.get("model", DEFAULT_MODEL)),
        effort=data.get("effort", "medium"),
        llm_max_tokens=int(data.get("llm_max_tokens", 32000)),
        request_timeout=float(data.get("request_timeout", 30.0)),
        rate_limit_seconds=float(data.get("rate_limit_seconds", 1.0)),
    )
    return cfg


def validate(cfg: Config) -> list[str]:
    """Return a list of human-readable problems; empty means good to go."""
    problems: list[str] = []
    if not cfg.urls_file.exists():
        problems.append(f"URL list not found: {cfg.urls_file}")
    if not cfg.anthropic_key:
        problems.append(
            "ANTHROPIC_API_KEY is not set (the LLM cleanup step is required)."
        )
    if cfg.image_mode == "upload":
        if not cfg.wp_base_url:
            problems.append("image_mode=upload needs wp_base_url in the config file.")
        if not cfg.wp_user:
            problems.append("image_mode=upload needs wp_user in the config file.")
        if not cfg.wp_app_password:
            problems.append(
                "image_mode=upload needs WP_APP_PASSWORD in the environment "
                "(a WordPress application password)."
            )
    if cfg.image_mode not in ("upload", "sideload", "bundle", "remote"):
        problems.append(f"Unknown image_mode: {cfg.image_mode}")
    return problems
