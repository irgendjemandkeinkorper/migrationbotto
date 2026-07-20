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

## Image modes

| Mode     | What it does                                                        | Needs WP creds |
|----------|--------------------------------------------------------------------|:--------------:|
| `upload` | Download originals, POST into the media library as real attachments | yes            |
| `bundle` | Download into `images_cache/`, reference local filenames            | no             |
| `remote` | Leave source URLs; WP importer sideloads on import                  | no             |

`upload` is the recommended path — pages reference real media-library
attachments and are fully decoupled from the source sites.

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
