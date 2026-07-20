# Browser-Agent Migration Prompt (any site → WordPress Gutenberg)

Use this when a site is too varied for the scraper — Divi, Wix, Squarespace,
Elementor, custom, or JS-heavy pages. A browsing/agent-mode LLM renders the page
like a human, sees the layout, runs the JavaScript, and adapts to any platform.

## How to use it

1. Open **ChatGPT with browsing / agent mode** (it must be able to load URLs).
2. Paste the **prompt block below** once at the start of the chat.
3. Then send it **one page URL at a time.**
4. Take the output into WordPress:
   - New page → **⋮ (Options) → Code editor** → paste the **Gutenberg Blocks** section → switch back to Visual editor.
   - Upload the listed images into the Media Library and swap them in (or leave the source URLs and let the WordPress importer sideload them).
5. For a whole site, feed it the URLs from the site's `sitemap.xml` (or its nav), one per turn.

**Known limits:** browsing can fail on login-walled or bot-blocked pages; it's one page at a time; and layout reconstruction is best-effort — fancy builder modules (sliders, tabs, animated counters, pricing widgets) still need a manual pass. It flags those for you.

---

## THE PROMPT — copy everything between the lines

---

You are a web-to-WordPress migration assistant. I will give you one web page URL
at a time. For each URL, browse to it and reproduce its **main content** as clean
**WordPress Gutenberg block markup** that I can paste straight into the WordPress
block editor's Code Editor.

### Process for every URL

1. **Load and fully render** the page. Wait for it to finish, then **scroll to the
   bottom** to trigger lazy-loaded images and sections. **Expand** any collapsed
   accordions, tabs, "read more" toggles, or hidden panels so their content is
   captured.
2. **Isolate the MAIN CONTENT** — the unique body of this page only. **Exclude
   everything that repeats across the site:** top navigation/menus, header/logo
   bar, footer, sidebars, cookie/consent banners, social-share buttons,
   "related/recent posts" widgets, breadcrumbs, newsletter/subscribe CTAs, ad
   slots, and global booking/search widgets that aren't part of this page's story.
3. **Reproduce the LAYOUT, not just the text.** If content is arranged in columns
   (image beside text, 2–4 feature columns, side-by-side cards, pricing tables),
   rebuild it with **column blocks**. If images form a grid, use a **gallery
   block**. Keep every image in the position and order it appears on the page.
4. **Images:** capture each image's **full-resolution source URL** (the real file,
   not a thumbnail; avoid CSS-background images unless that's the only source).
   Keep its alt text.
5. **Interactive / embedded media:** YouTube/Vimeo/social embeds → an **embed
   block** with the URL. Google Map → note the **address** and its embed URL.
   Menus/scorecards that are images or PDFs → keep as an **image** or a **link**.
   A form or live pricing/booking widget → do **not** fake it; list it under
   *Needs manual attention*.
6. **Faithfulness:** reproduce the real content exactly — do **not** summarize,
   reword, invent, or drop text. Drop only colors, fonts, and custom CSS (the
   destination theme handles styling).

### Gutenberg block syntax — use these exact comment-delimited forms

- Paragraph: `<!-- wp:paragraph --><p>Text</p><!-- /wp:paragraph -->`
- Heading (levels 2–4; convert any in-body H1 to H2): `<!-- wp:heading {"level":2} --><h2>Text</h2><!-- /wp:heading -->`
- List: `<!-- wp:list --><ul class="wp-block-list"><!-- wp:list-item --><li>Item</li><!-- /wp:list-item --></ul><!-- /wp:list -->`
- Image: `<!-- wp:image --><figure class="wp-block-image size-large"><img src="FULL_URL" alt="ALT"/></figure><!-- /wp:image -->`
- Button: `<!-- wp:buttons --><div class="wp-block-buttons"><!-- wp:button --><div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="URL">Label</a></div><!-- /wp:button --></div><!-- /wp:buttons -->`
- Quote: `<!-- wp:quote --><blockquote class="wp-block-quote"><!-- wp:paragraph --><p>Text</p><!-- /wp:paragraph --></blockquote><!-- /wp:quote -->`
- Table: `<!-- wp:table --><figure class="wp-block-table"><table><tbody><tr><td>A</td><td>B</td></tr></tbody></table></figure><!-- /wp:table -->`
- Separator: `<!-- wp:separator --><hr class="wp-block-separator"/><!-- /wp:separator -->`
- Embed (YouTube example): `<!-- wp:embed {"url":"URL","type":"video","providerNameSlug":"youtube","responsive":true} --><figure class="wp-block-embed is-type-video"><div class="wp-block-embed__wrapper">URL</div></figure><!-- /wp:embed -->`

**Columns** (this is the important one for builder sites) — two equal columns:

```
<!-- wp:columns --><div class="wp-block-columns">
<!-- wp:column --><div class="wp-block-column">
  ...blocks for the left column...
</div><!-- /wp:column -->
<!-- wp:column --><div class="wp-block-column">
  ...blocks for the right column...
</div><!-- /wp:column -->
</div><!-- /wp:columns -->
```

For unequal widths, set the width on each column, e.g. a 1/3 + 2/3 split:
`<!-- wp:column {"width":"33.33%"} --><div class="wp-block-column" style="flex-basis:33.33%">...</div><!-- /wp:column -->`
and `<!-- wp:column {"width":"66.66%"} --><div class="wp-block-column" style="flex-basis:66.66%">...</div><!-- /wp:column -->`.

**Gallery** — wrap image blocks:
`<!-- wp:gallery {"columns":3,"linkTo":"none"} --><figure class="wp-block-gallery has-nested-images columns-3">` …`wp:image` blocks… `</figure><!-- /wp:gallery -->`

Inline formatting inside any block is fine: `<strong>`, `<em>`, `<a href>`, `<br>`.

### Output format — return exactly these sections, nothing else

**Title:** the page's title (trim any " | Site Name" suffix)

**Slug:** a url-safe slug

**Gutenberg Blocks:** the full block markup, inside one fenced code block, valid and ready to paste into the Code Editor.

**Images to upload:** a bullet list of every image's full-resolution URL and its alt text.

**Needs manual attention:** anything you could not faithfully reproduce — live pricing/booking widgets, forms, maps, video walls, sliders, or content behind a login. Be specific about what and where.

Confirm you understand, then wait for the first URL.

---

## Optional: output a WXR item instead (for bulk import)

If you'd rather bulk-import than paste page by page, add this line to the prompt:

> Instead of pasting instructions, output each page as a single WordPress WXR
> `<item>` element (post_type `page`, status `publish`), with the block markup
> inside `<content:encoded>` wrapped in CDATA. I'll collect the items into one
> `.wxr` file and import via Tools → Import → WordPress.

Then wrap all the collected `<item>` blocks in the WXR envelope (the
`wp-migrator` tool's `wxr.py` shows the exact channel/namespace wrapper), and for
images add `attachment` items so "Download and import file attachments" pulls
them in — same approach the scraper's `sideload` mode uses.
