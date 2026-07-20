# wp-migrator

Scrape content from arbitrary websites (any host, any structure) and package it
as a **WordPress Gutenberg WXR import file** for bulk import.

It's a real pipeline, not a prompt: the mechanical parts (fetching, content
extraction, image handling, block markup, WXR) are deterministic; an LLM handles
only the fuzzy judgment (what's the real content vs. leftover nav/share/related
junk, and normalizing messy markup) — because arbitrary sites are never
deterministically clean.

## Pipeline

```
urls.txt
  → fetch (rate-limited, retried)
  → extract main content        trafilatura, or a per-domain CSS selector
                                (strips nav / header / footer / sidebars)
  → tokenize images to ⟦IMG_n⟧  so the LLM can't reorder or mangle them
  → images: download + upload   into the WP media library (REST) as real
                                attachments; positions kept from source order
  → LLM cleanup (Claude)        messy HTML → constrained whitelist HTML,
                                tokens preserved verbatim, boilerplate dropped
  → to Gutenberg blocks         deterministic; tokens → wp:image blocks
  → WXR                         one <item> per page, blocks in content:encoded
```

**Why images/interactive/CSS behave:** images stay inline where they appear in
the source DOM (never repositioned by guesswork); CSS/styling is intentionally
dropped (Gutenberg blocks carry their own theme styling — porting origin CSS is
what makes imports look broken); interactive embeds/iframes are stripped in the
whitelist step (extend `blocks.py` if you want to map known providers to
`wp:embed`).

## Install

```bash
cd wp-migrator
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

```bash
cp config.example.toml config.toml       # edit WP URL/user, image_mode, selectors
export ANTHROPIC_API_KEY=sk-ant-...       # required (LLM cleanup)
export WP_APP_PASSWORD='xxxx xxxx xxxx'   # only for image_mode = "upload"
```

A WordPress **application password** (Users → Profile → Application Passwords)
authenticates the media uploads over the REST API.

## Run

```bash
python -m wpmigrate --urls urls.txt --out export.wxr --config config.toml
```

Override image handling without editing the config:

```bash
python -m wpmigrate --urls urls.txt --images remote     # no WP creds needed
```

Then in WordPress: **Tools → Import → WordPress**, upload `export.wxr`.

## Web UI

A local browser interface over the same pipeline — paste URLs or discover them
from a sitemap, pick options, watch progress, and download the WXR.

```bash
pip install -r requirements.txt -r requirements-web.txt
export ANTHROPIC_API_KEY=sk-ant-...        # required
export WP_APP_PASSWORD='xxxx xxxx xxxx'    # only for the "upload" image mode
python -m webapp                            # serves http://127.0.0.1:8000
```

Open `http://127.0.0.1:8000`, then:

1. **Source** — paste URLs (one per line), or enter a `sitemap.xml` URL and
   click *Fetch URLs* to populate the list (sitemap-index files are expanded).
2. **Options** — image mode, post type/status, author, optional model. For
   *upload* mode, enter the WordPress URL + user (the app password stays in the
   server env).
3. **Start** — a background job runs the pipeline with a live progress log;
   when it finishes, download `export.wxr`.

It's a **single-user local tool**: secrets stay server-side in env vars, jobs
run in-memory. It is not hardened for public/multi-user hosting — don't expose
it to the internet as-is. Change host/port with `WPMIGRATE_HOST` /
`WPMIGRATE_PORT`.

Why a server (and not a static page): a browser can't fetch arbitrary
cross-origin sites, can't safely hold your API keys, and can't run the Python
extraction pipeline — so the work has to happen server-side.

## Image modes

| Mode       | What it does                                                              | Needs WP creds |
|------------|--------------------------------------------------------------------------|:--------------:|
| `sideload` | Emits WXR **attachment items**; on import (with "Download and import file attachments" checked) WordPress fetches each image server-side into the media library and remaps the `<img>` URLs | no |
| `upload`   | Download originals, POST into the media library via the REST API          | yes            |
| `bundle`   | Download into `images_cache/`, reference local filenames                  | no             |
| `remote`   | Leave source URLs inline; no attachment items (images not imported)       | no             |

**Which to pick:**

- `sideload` — best for **managed hosts** (e.g. platforms that block the REST
  API). The import runs server-side inside the target, so there's no external
  auth. Requirement: the target server must be able to reach the source image
  URLs during import.
- `upload` — best when you have working REST access to the target: pages
  reference real media-library attachments with attachment IDs. Fails if the
  host blocks authenticated REST writes.

## Tuning extraction

If a specific site's content area comes through wrong (too much or too little),
pin it with a CSS selector in `config.toml`:

```toml
[selectors]
"example.com" = "article.entry-content"
```

## Model

Defaults to `claude-opus-4-8`. Override for cost with `WPMIGRATE_MODEL`
(e.g. `claude-haiku-4-5` or `claude-sonnet-5`) — that's your call, not an
automatic downgrade.

## Layout

```
wpmigrate/
  config.py     load/validate config (secrets from env)
  fetch.py      polite HTTP (rate limit, retries)
  extract.py    main-content extraction + image tokenization
  clean_llm.py  Claude cleanup into a constrained HTML whitelist
  images.py     download + upload to WP media library
  blocks.py     whitelist HTML → Gutenberg block markup
  wxr.py        WXR document builder
  pipeline.py   orchestration
  __main__.py   CLI
```
