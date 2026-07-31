# Trafilatura duplicates body on block-theme markup

**Seen:** 2026-07-29, crawling wptest.neintruths.com (WordPress Twenty Twenty-Five).

**Symptom:** `extract()` returns the whole page body twice — the second copy
slightly different (e.g. a captioned image dropped). Downstream this doubles
paragraphs, image tokens, and WXR attachment items.

**Cause:** trafilatura itself (verified with a direct `trafilatura.extract`
call on the raw HTML; page contains the content exactly once). Happens with
Twenty Twenty-Five's block-theme markup regardless of `favor_recall`.

**Fix (per project convention):** per-domain `[selectors]` override in
config.toml, scoping extraction to the content container:

```toml
[selectors]
"example.com" = ".entry-content"
```

`.entry-content` is the standard class on WP block themes'
`wp-block-post-content` container — likely the right override for *any*
WordPress source site showing duplicated output.

## Related case: flaor.com (2026-07-29)

Duplicated text + wrong images had *different* causes on the same symptom:
- The theme stuffs the **entire page text into `<meta name="description">`**;
  trafilatura merges that into the output → every name appeared twice.
- `favor_recall=True` also swept up **boilerplate images** (site logo,
  credit-card icons) → 10 image tokens for a 5-photo page, and the LLM
  paired the extra tokens with the duplicated text.

Same fix: `"flaor.com" = ".post_content"` (Thesis theme container). Diagnostic
that found it: walk ancestors of a known content string and pick the smallest
container whose `<img>` count matches the real content images.

Note: `extract()` falls back to trafilatura **silently** when a selector
doesn't match — a wrong selector looks identical to no selector.
