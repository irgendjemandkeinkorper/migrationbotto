# Build instructions: "HTML → Gutenberg" web app (Google AI Studio → GitHub Pages)

Spec for a client-side web app that converts non-WordPress website content into
Gutenberg block markup. It ports wp-migrator's proven pipeline design
(extract → tokenize images → LLM whitelist-cleanup → deterministic block
serialization) into a static browser app.

**Workflow:** paste the "Build prompt" section below into Google AI Studio's
Build mode to generate the app → export the generated code to a GitHub repo →
enable GitHub Pages. The app is a pure static SPA; both hosts run it unchanged.

---

## Design invariants (do not let the generator "improve" these away)

These are the load-bearing decisions carried over from wp-migrator:

1. **The LLM never emits Gutenberg block markup.** It only normalizes messy
   HTML into a small whitelist-HTML intermediate. Block syntax is produced by
   deterministic code, so page 400 is structurally identical to page 1.
2. **The LLM never sees or invents image URLs.** Images are replaced by
   `⟦IMG_n⟧` tokens *before* the LLM step; real URLs are joined back in
   deterministically afterward. The model literally cannot hallucinate an image.
3. **Validate the LLM's output in code** (wp-migrator's known gap — the Python
   version trusts the prompt; this app must not). Parse the returned fragment,
   enforce the whitelist, assert token preservation, retry on violation.
4. **Keys stay client-side and user-owned.** The user's Gemini API key lives in
   `localStorage`, is sent only to `generativelanguage.googleapis.com`, and is
   never proxied through any server.

---

## Build prompt (paste everything below this line into AI Studio Build)

Build a single-page React + TypeScript app called **"Blockify — HTML to
Gutenberg"**. It converts content from any non-WordPress web page into
WordPress Gutenberg block markup, ready either to paste into the block editor
or to download as a WXR import file (one or many pages per bundle). All
processing is client-side; the only network calls are the optional page fetch
and the Gemini API.

### UI

Single screen, three panels top to bottom:

1. **Input panel**
   - Tab A "Paste HTML" (default): a large textarea. Instruction text: "In your
     browser, open the page, right-click → View Page Source (or use DevTools →
     copy outerHTML for JS-rendered pages), paste here." A second small input
     for the page URL (optional, used only to resolve relative image links).
   - Tab B "Fetch URL": a URL field. Fetch through a public CORS proxy
     (try `https://api.allorigins.win/raw?url=` then
     `https://corsproxy.io/?url=`). On failure show a friendly message telling
     the user to fall back to Paste HTML — do not retry-loop.
   - Optional "Content CSS selector" text input (advanced, collapsed by
     default): when set, extraction uses this selector's inner HTML instead of
     Readability.
   - Settings (gear icon): Gemini API key (password field, persisted to
     `localStorage`; when running inside AI Studio, use the injected
     `process.env.API_KEY` and hide the field), model picker with
     `gemini-2.5-pro` as default and `gemini-2.5-flash` as the fast option.
   - "Convert" button.
2. **Progress panel**: step list with live status — Extract → Images → Clean
   (LLM) → Validate → Blocks. Show a short note per step (e.g. "14 images
   tokenized"). Show validation retries explicitly ("model broke the contract,
   retrying 1/2").
3. **Output panel**
   - Read-only code view of the final Gutenberg block markup, with a
     **Copy to clipboard** button and a "How to paste into WordPress" hint
     (block editor → three-dot menu → Code editor → paste).
   - A collapsible "Images" table: token index, source URL, alt text, and a
     warning badge for any image that ended up unresolved.
   - A collapsible "Intermediate HTML" view (the post-LLM whitelist HTML), for
     debugging.
   - An editable **Title** field (pre-filled from extraction) and an
     **"Add page to WXR bundle"** button.
4. **Bundle panel** (below output, visible once it has pages): the list of
   pages added so far (title, image count, remove button), settings for the
   export — author login (default `admin`), post type (`page`/`post`, default
   `page`), post status (`draft`/`publish`, default `draft`), and a checkbox
   **"Sideload images"** (default on) — and a **"Download WXR"** button that
   serializes the bundle to `export.wxr`. Persist the bundle to `localStorage`
   so converted pages survive a reload.

### Pipeline (implement exactly this order)

**Step 1 — Extract.** Parse the input HTML with `DOMParser`. If a content CSS
selector is provided and matches, use that element's inner HTML. Otherwise run
**Mozilla Readability** (`@mozilla/readability`) on the document and use its
`content` HTML. If Readability returns nothing, fall back to `<body>` inner
HTML. Derive a page title: first content heading, else `<title>` split on
`/\s+[|–—-]\s+/` taking the first part, else `og:title`, else "Untitled".

**Step 2 — Tokenize images.** Walk the extracted fragment. For every `<img>`:

- Resolve `src` in this order: `src`, `data-src`, `data-lazy-src`, first URL in
  `srcset`. If none, remove the element and issue **no** token (indices stay
  gapless).
- Absolutize against the page URL if one was given.
- Alt text: `alt` attribute, else `title`, else `""`. If the image sits inside
  a `<figure>` with a `<figcaption>`, capture the figcaption text as `caption`.
- Replace the `<img>` (or its whole `<figure>` if it has one) with a new
  paragraph element whose entire text content is the token `⟦IMG_n⟧`
  (n = 0-based counter). The delimiters are U+27E6 and U+27E7 — use those exact
  codepoints; the matching regex everywhere is `/⟦IMG_(\d+)⟧/g`.
- Record `{ index, src, alt, caption }` in an image map.

Tokens must be block-level (their own paragraph) so they survive the LLM step
as standalone elements.

**Step 3 — LLM cleanup (Gemini).** Call the Gemini API (`@google/genai`) with
this system instruction (verbatim; `{WHITELIST}` interpolated):

> You are an HTML normalizer. You receive messy extracted article HTML and
> return a clean HTML fragment.
> Rules:
> 1. Output ONLY these tags: h2, h3, h4, p, ul, ol, li, blockquote, pre, code,
>    table, thead, tbody, tr, th, td, strong, em, a, br, hr, sup, sub. Convert
>    any h1 to h2. Drop every other tag (div, span, section, figure,
>    figcaption, iframe, script, style, nav, button, form, img) but KEEP their
>    meaningful text content by unwrapping.
> 2. On `<a>` keep only the href attribute. Strip all other attributes from all
>    tags.
> 3. Remove boilerplate: navigation, share/social buttons, "related posts",
>    author bios, newsletter or subscribe prompts, cookie/consent notices,
>    comment sections, ad labels, breadcrumb trails.
> 4. Image placeholder tokens look like ⟦IMG_0⟧, ⟦IMG_1⟧, etc. Preserve every
>    token EXACTLY as written, each alone in its own `<p>`, in its original
>    order. Never add, remove, renumber, or reword a token.
> 5. Do not add commentary, titles, or a wrapping document element. Do not wrap
>    the output in Markdown code fences. Return the cleaned HTML fragment only.
> 6. Preserve the reading order and all substantive text. Do not summarize or
>    rewrite prose — only restructure and strip.

User message:

```
Article title (for context; do NOT include it in the body): {title}

Extracted HTML to clean:

{tokenizedHtml}
```

Strip a leading/trailing markdown code fence from the response if present.

**Step 4 — Validate (this step is mandatory, never skip it).** Parse the LLM
response with `DOMParser` and check:

- a. **Wrapper unwrap:** if the fragment's body has a single element child that
  is `div`, `article`, `section`, `main`, or `body`, unwrap it (repeat until
  stable). Do this silently — it is a known model failure mode.
- b. **Whitelist:** every element must be in the whitelist above plus the
  tolerated inline set `b`, `i`, `u` (normalize `b`→`strong`, `i`→`em`, unwrap
  `u`). Unwrap any other element in place (keep its children). Strip all
  attributes except `href` on `<a>`.
- c. **Token integrity:** the multiset of token indices in the output must
  equal the input's. If tokens are missing, duplicated, or renumbered → retry
  the LLM call (max 2 retries), appending to the user message: "Your previous
  attempt violated rule 4. These tokens were {missing/duplicated}: {list}.
  Return the corrected full fragment." After final failure, re-insert missing
  tokens as trailing paragraphs and mark those images "position lost" in the
  Images table.
- d. Each token must be alone in its own `<p>`; if one is embedded in a text
  run, split it out into its own paragraph in code (do not retry for this).

**Step 5 — Serialize to blocks (pure deterministic code, no LLM).** Walk the
validated fragment's direct children and emit blocks joined by `"\n\n"`:

| Element | Block emitted |
|---|---|
| `<p>` (no token) | `<!-- wp:paragraph -->\n<p>{inner}</p>\n<!-- /wp:paragraph -->` |
| `<p>` containing exactly `⟦IMG_n⟧` | image block, see below |
| `<h2>`–`<h4>` | `<!-- wp:heading {"level":N} -->\n<hN class="wp-block-heading">…</hN>\n<!-- /wp:heading -->` (clamp level to 2–4) |
| `<ul>` | `<!-- wp:list -->\n<ul class="wp-block-list">{items}</ul>\n<!-- /wp:list -->` |
| `<ol>` | `<!-- wp:list {"ordered":true} -->\n<ol class="wp-block-list">{items}</ol>\n<!-- /wp:list -->` |
| each `<li>` | `<!-- wp:list-item -->\n<li>…</li>\n<!-- /wp:list-item -->`; a nested `<ul>`/`<ol>` inside an `<li>` becomes a nested `wp:list` block inside that `wp:list-item` (support one level of nesting minimum) |
| `<blockquote>` | `<!-- wp:quote -->\n<blockquote class="wp-block-quote">{nested wp:paragraph blocks}</blockquote>\n<!-- /wp:quote -->` |
| `<pre>` | `<!-- wp:code -->\n<pre class="wp-block-code"><code>{escaped text}</code></pre>\n<!-- /wp:code -->` |
| `<table>` | `<!-- wp:table -->\n<figure class="wp-block-table"><table>…</table></figure>\n<!-- /wp:table -->` — bare `<table>` tag, no extra class (core rejects nonstandard classes) |
| `<hr>` | `<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->` |
| anything else | treat as paragraph after inline sanitation |

Image block (token `⟦IMG_n⟧` looked up in the image map; URLs point at the
source site — "remote" mode):

```
<!-- wp:image {"sizeSlug":"large"} -->
<figure class="wp-block-image size-large"><img src="{src}" alt="{escapedAlt}"/>{caption}</figure>
<!-- /wp:image -->
```

where `{caption}` is `<figcaption class="wp-element-caption">{text}</figcaption>`
when a caption was captured, else empty.

Inline sanitation inside every block: allowed inline tags are `a`, `strong`,
`em`, `code`, `br`, `sup`, `sub`; unwrap everything else; `<a>` keeps only
`href`. HTML-escape all text nodes.

**Step 6 — Final gate.** If the string `⟦IMG_` appears anywhere in the final
block markup, something upstream failed: show an error banner naming the
affected tokens instead of silently shipping broken output. Also fail if the
output is empty.

**Step 7 — WXR bundle export (pure deterministic code).** "Download WXR"
serializes every page in the bundle into one WordPress eXtended RSS 1.2
document that Tools → Import → WordPress accepts. Structure it exactly like
this:

- Envelope:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.2/">
<channel>
    <title>{escaped site title, default "Imported Content"}</title>
    <link>https://example.com</link>
    <description>Migrated content</description>
    <pubDate>{now as RFC-1123, e.g. Tue, 28 Jul 2026 12:00:00 +0000}</pubDate>
    <language>en-US</language>
    <wp:wxr_version>1.2</wp:wxr_version>
    <wp:author>
        <wp:author_login><![CDATA[{author}]]></wp:author_login>
        <wp:author_display_name><![CDATA[{author}]]></wp:author_display_name>
    </wp:author>
    {items…}
</channel>
</rss>
```

- One content `<item>` per page, with sequential integer `wp:post_id` starting
  at 1 and the block markup CDATA-wrapped in `content:encoded`:

```xml
<item>
    <title>{escaped title}</title>
    <link>{escaped source URL}</link>
    <pubDate>{pub}</pubDate>
    <dc:creator><![CDATA[{author}]]></dc:creator>
    <guid isPermaLink="false">{escaped source URL}</guid>
    <description></description>
    <content:encoded><![CDATA[{block markup}]]></content:encoded>
    <excerpt:encoded><![CDATA[]]></excerpt:encoded>
    <wp:post_id>{id}</wp:post_id>
    <wp:post_date>{now as "YYYY-MM-DD HH:MM:SS" UTC}</wp:post_date>
    <wp:post_date_gmt>{same}</wp:post_date_gmt>
    <wp:comment_status>closed</wp:comment_status>
    <wp:ping_status>closed</wp:ping_status>
    <wp:post_name><![CDATA[{slug}]]></wp:post_name>
    <wp:status>{status}</wp:status>
    <wp:post_parent>0</wp:post_parent>
    <wp:menu_order>0</wp:menu_order>
    <wp:post_type>{post type}</wp:post_type>
    <wp:post_password></wp:post_password>
    <wp:is_sticky>0</wp:is_sticky>
</item>
```

- When **Sideload images** is checked, additionally emit one attachment
  `<item>` per image of that page (continuing the same post-id sequence),
  parented to the page. This makes the WordPress importer — with "Download and
  import file attachments" checked — fetch each image server-side into the
  media library and remap the inline `<img>` URLs to local copies:

```xml
<item>
    <title>{escaped: alt text, else filename-derived title}</title>
    <link>{escaped image src}</link>
    <pubDate>{pub}</pubDate>
    <dc:creator><![CDATA[{author}]]></dc:creator>
    <guid isPermaLink="false">{escaped image src}</guid>
    <description></description>
    <content:encoded><![CDATA[]]></content:encoded>
    <excerpt:encoded><![CDATA[]]></excerpt:encoded>
    <wp:post_id>{id}</wp:post_id>
    <wp:post_date>{date}</wp:post_date>
    <wp:post_date_gmt>{date}</wp:post_date_gmt>
    <wp:comment_status>closed</wp:comment_status>
    <wp:ping_status>closed</wp:ping_status>
    <wp:post_name><![CDATA[{slug of title}]]></wp:post_name>
    <wp:status>inherit</wp:status>
    <wp:post_parent>{parent page id}</wp:post_parent>
    <wp:menu_order>0</wp:menu_order>
    <wp:post_type>attachment</wp:post_type>
    <wp:post_password></wp:post_password>
    <wp:is_sticky>0</wp:is_sticky>
    <wp:attachment_url>{escaped image src}</wp:attachment_url>
    <wp:postmeta>
        <wp:meta_key>_wp_attachment_image_alt</wp:meta_key>
        <wp:meta_value><![CDATA[{alt}]]></wp:meta_value>
    </wp:postmeta>
</item>
```

- Helpers: `slugify(title)` = lowercase, replace runs of non-`[a-z0-9]` with
  `-`, trim `-`, fall back to `"page"`. CDATA content must have any literal
  `]]>` split as `]]]]><![CDATA[>`. XML-escape everything interpolated outside
  CDATA. Filename-derived image title = basename of the URL path, extension
  stripped, `_`/`-` → spaces, URL-decoded, fallback `"image"`.
- Download via a `Blob` + temporary anchor; filename `export.wxr`.
- The UI hint next to the button: "In WordPress: Tools → Import → WordPress,
  upload this file, assign an author, and check 'Download and import file
  attachments' so images are copied into your media library."

### Non-goals (v1)

No direct WordPress upload (no REST API calls, no WP credentials in the
browser — imports go through the WXR file), no embeds/columns/galleries
(iframes are intentionally stripped), no automated multi-URL crawling (pages
are converted one at a time and collected into the bundle), no server. Keep
the whole app dependency-light: React, `@mozilla/readability`, `@google/genai`
only.

---
*(end of AI Studio build prompt)*

---

## After generation: deploy to GitHub Pages

1. In AI Studio, export/download the generated app code and push it to a new
   GitHub repo.
2. Replace the AI Studio key injection with the settings-field key path (the
   spec already asks for both; verify the `localStorage` path works standalone).
3. Add a GitHub Actions workflow that builds the Vite app and publishes `dist/`
   to Pages (`actions/deploy-pages`). Set Vite `base` to the repo name.
4. Smoke-test: convert one plain article, one image-heavy page, one page with
   tables + nested lists; paste each result into a real Gutenberg code editor
   and confirm no "unexpected or invalid content" warnings. Then bundle all
   three, download the WXR, and import it on a scratch WordPress site with
   "Download and import file attachments" checked — confirm pages appear with
   images in the media library.

## Deltas from wp-migrator (deliberate, not drift)

- **Validator added** (step 4): the Python pipeline enforces the whitelist and
  token contract by prompt alone; drift is absorbed silently. Known silent
  failures fixed here: wrapper-`<div>` page collapse, dropped-token image loss,
  literal tokens leaking into output.
- **Readability replaces trafilatura** (no JS equivalent of trafilatura; no
  `<graphic>` elements to handle).
- **Captions are captured** (`figcaption` → `wp:image` caption); the Python
  pipeline drops them.
- **Nested lists supported**; Python flattens them.
- **Bare `<table>`** inside the figure; Python emits a nonstandard
  `wp-block-table__table` class that trips editor validation.
- **Gemini instead of Claude** — required by the AI Studio context; the prompt
  contract is unchanged.
- **WXR export is a straight port of `wpmigrate/wxr.py`** (envelope, item
  shapes, CDATA splitting, slugify, sequential ids) plus a bundle UI in front
  of it. Image handling maps to wp-migrator's "sideload" mode: block markup
  references source URLs inline, attachment items make the WP importer fetch
  them server-side. `upload` mode (REST) is deliberately not ported — it would
  put WP credentials in the browser.

## Possible v2

- Template-driven direct-to-blocks mode for builder pages (Divi/Wix/Elementor),
  per `prompts/browser-migration-prompt.md` — paste known-good block markup as
  a target vocabulary and let the model pattern-match into it.
- Multi-URL batch via the CORS-proxy fetcher with a per-page result list
  feeding the bundle automatically, plus sitemap discovery (port
  `wpmigrate/sitemap.py`).
