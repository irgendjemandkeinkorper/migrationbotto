<!--
  CLAUDE.md — L0 baseline (the MAP + the RULES). Always loaded and prompt-cached.
  Keep it SMALL, STABLE (edit between tasks, never mid-task), DURABLE
  (lasting facts only; session notes go in the vault).
-->

# wp-migrator

Python tool that scrapes arbitrary websites and packages them as a WordPress
Gutenberg **WXR** import file. Deterministic mechanics (fetch, extract, images,
blocks, WXR); an LLM (Claude) handles only the fuzzy cleanup step.

## Architecture map
<!-- Read THIS instead of grepping to "discover" structure. Load-bearing paths only. -->

- **Entry points:**
  - `wpmigrate/__main__.py` — CLI (`python -m wpmigrate --urls … --out … [--config …] [--images …] [--render]`)
  - `webapp/__main__.py` → `webapp/server.py` — FastAPI local web UI (`python -m webapp`, serves 127.0.0.1:8000)
- **Core package `wpmigrate/`:**
  - `pipeline.py` — orchestration; `run(cfg, progress)` is the spine, emits progress dicts
  - `config.py` — `Config` dataclass, `load_config`, `validate`; secrets from env only
  - `fetch.py` — polite HTTP (rate limit, retries); `render.py` — Playwright headless fetcher (`--render`)
  - `extract.py` — main-content extraction (trafilatura / per-domain CSS selector) + image tokenization (⟦IMG_n⟧)
  - `images.py` — `ImagePipeline`: download + upload/sideload/bundle images
  - `clean_llm.py` — Claude cleanup: messy HTML → constrained whitelist HTML, tokens preserved
  - `blocks.py` — whitelist HTML → Gutenberg block markup (tokens → `wp:image`)
  - `wxr.py` — WXR document builder (`Page`, `build_wxr`); `sitemap.py` — sitemap URL discovery (web UI)
- **Data flow:** urls → fetch → extract (+tokenize images) → images.process → clean_llm → blocks → wxr → `export.wxr`
- **Web UI:** `webapp/server.py` runs the same `pipeline.run` in a background thread; `webapp/static/index.html` is the single-page frontend.
- **Where NOT to look (DATA, never bulk-read):** `*-export.wxr` files (WordPress export dumps), `images_cache/` (downloaded images), `.venv/`.

## Deeper context lives in the vault

Curated, durable knowledge is in the Obsidian vault under `vault/`:

- Architecture deep-dives → `vault/10-Architecture/`
- Per-module notes       → `vault/20-Modules/`
- Decisions (ADRs)       → `vault/30-Decisions/`
- Known gotchas/footguns → `vault/40-Gotchas/`

When a task touches an area, open the matching note **before** reading source.

## Conventions

- **Secrets from env only** — `ANTHROPIC_API_KEY` (required), `WP_APP_PASSWORD` (upload mode). Never in `config.toml`, CLI, or code.
- **Default model is `claude-opus-4-8`** (`DEFAULT_MODEL` in `config.py`). Downgrade only via explicit `WPMIGRATE_MODEL` — never auto-downgrade for cost.
- Image modes: `upload` (REST, needs WP creds) / `sideload` (WXR attachment items) / `bundle` (local) / `remote` (source URLs inline).
- Extraction problems are fixed **first** with a per-domain `[selectors]` CSS override in `config.toml`, only then `--render`.

## Bash commands

Prefer these over defaults when available; fall back silently if missing.

- **Search content:** `rg` over `grep`   • **Find files:** `fd` over `find`
- **TOML/YAML:** `yq`   • **JSON:** `jq`   • **GitHub:** `gh`

### Python
- **Lint + format:** `ruff check` / `ruff format`
- **Typecheck:** `pyright` (or `mypy` if standardized)
- **Test:** `pytest -q`   • **Dead code:** `vulture`
- **Run tools without polluting the env:** `uvx <tool>` / `uv run <tool>`
- **Run CLI:** `python -m wpmigrate --urls urls.txt --out export.wxr --config config.toml`
- **Run web UI:** `python -m webapp` (env: `WPMIGRATE_HOST` / `WPMIGRATE_PORT`)
- **Deps:** `requirements.txt` (core) + `requirements-web.txt` (FastAPI/uvicorn) + `requirements-render.txt` (Playwright)

## Working agreement (token discipline)

- **Use the map above and the vault before searching.** Grep/open files only when the map doesn't answer.
- **When I name a file or symbol, that's your pivot** — start there; don't re-scan the tree to "confirm."
- **Prefer signatures over bodies.** Read a full body only for the file you're editing.
- **Explore in a subagent** so this conversation's context stays lean.
- **End-of-task ritual:** if you learned something durable, propose a short vault note (or a CLAUDE.md edit if a structural fact changed).

## Do NOT
- Don't edit this file mid-task (breaks the prompt cache).
- Don't reformat/mass-rename outside the task's scope.
- **Don't bulk-read** `*-export.wxr`, `images_cache/`, or `.venv/` — big data, not code.
- Don't put secrets in `config.toml` or code; they belong in env vars.
