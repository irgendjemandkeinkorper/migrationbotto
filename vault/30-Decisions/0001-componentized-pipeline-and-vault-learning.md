---
type: decision
id: 0001
status: accepted
date: 2026-07-29
---

# ADR 0001: Componentize the pipeline; feed a vault-backed pattern/template library

> **TL;DR:** Split the linear pipeline into artifact-producing stages so raw
> content, analysis, and final export are independently inspectable; add a
> manual-attention report and a vault-backed pattern/template library that
> gets smarter across migrations, instead of re-deciding block mappings from
> scratch every run.

## Context

A ChatGPT-generated sibling tool (`sitemap-to-gutenberg-&-wxr-exporter`, see
[[40-Gotchas/README]] area for tool comparisons — full review kept in this
ADR since it's a one-time comparison, not a recurring gotcha) was reviewed for
ideas. It does several things well — SSRF-hardened fetching, a human
approval gate before export, per-page confidence scoring, a resumable
per-page job queue — but is materially weaker on content fidelity: no image
pipeline (remote URLs only, no WXR attachments), no LLM cleanup pass (pure
rule-based DOM→block mapping), no JS-render fallback, and no learning across
migrations (config is per-run only).

Separately, the user wants:
1. A pure raw-HTML backup, both as a standalone per-page archive and as a
   parallel "raw" WXR export, distinct from the block-ified WXR.
2. Very visible placeholders (not silent drops or guesses) for content the
   pipeline shouldn't try to migrate automatically.
3. An "analysis" pass that classifies which content structures are easy vs.
   hard to migrate, written to the vault so the classification improves
   across migrations instead of resetting every run.
4. A human-readable manual-attention report (txt/html, ideally also PDF)
   with concrete URLs and surrounding context — not a guessing game.
5. A target-template picker (dropdown) that biases — but does not hard-gate
   — extraction/cleanup/block-selection toward a specific client theme's
   preferred block patterns.

## Decision

Componentize `pipeline.run()` into stages that each persist an artifact to
disk before the next stage runs, so any stage is independently inspectable
and rerunnable:

`fetch → extract → analyze (new) → clean_llm → blocks → images → wxr (dual: raw + block-ified) → report (new) → vault sync (new)`

Concretely, phased:

- **Phase 1 (this pass):** raw HTML backup. Every fetched page's raw HTML is
  saved to `cfg.raw_html_dir` (one file per page); a parallel "raw" WXR
  (`<out_stem>-raw.wxr`) is built from the extracted+detokenized HTML
  (image tokens resolved back to real `<img>` tags), independent of whether
  downstream `clean_llm`/`blocks` succeeds for that page. This is pure
  plumbing — no new stage, no LLM involvement, low risk.
- **Phase 2:** a new `analyze` stage between `extract` and `clean_llm`.
  Classifies structural elements by a confidence heuristic, produces the
  manual-attention findings that both (a) drive visible placeholder
  insertion in `clean_llm` output for low-confidence elements and (b) feed
  the human-readable report (txt + self-contained HTML; PDF via Playwright
  print-to-pdf, already a dependency via `render.py`).
- **Phase 3:** vault-backed pattern library (`vault/60-Patterns/`) and
  per-client template profiles (`vault/70-Templates/`). Template profiles
  are Markdown docs (human-readable, hold the rationale) with the
  structured data the code reads in frontmatter or a fenced block —
  decided over the ChatGPT-tool's per-run-only config specifically so
  profiles persist and compose with the vault's existing pattern-learning
  loop. The dropdown in `webapp/static/index.html` lists profiles found
  under `vault/70-Templates/`. Template bias is soft: `clean_llm`/`blocks`
  prefer the named template's patterns but are not restricted to them.
  After each run, findings (especially human corrections of an
  auto-guessed mapping) are written back to `vault/60-Patterns/` so the
  next migration's `analyze` stage starts smarter.

Review UI (side-by-side raw/markup/preview + approve-before-export, the one
genuinely strong idea from the ChatGPT tool we're *not* adopting yet) is
deferred — report-only first, since it's a separate, larger `webapp` change.

## Alternatives considered

- **Adopt the ChatGPT tool's rule-based DOM→block converter wholesale** —
  rejected: no image pipeline, no LLM cleanup, cruder unknown-element
  handling (paragraph-ify with no flag). Our `clean_llm.py` + whitelist
  `blocks.py` combination produces better fidelity on varied/messy markup.
- **Structured TOML/JSON for template profiles instead of vault Markdown** —
  rejected: loses the narrative "why" and doesn't compose naturally with
  the pattern-learning vault sync (see phasing options originally posed to
  the user; vault Markdown was the explicit choice).
- **Build the live human-review gate now, alongside the report** — deferred:
  correct long-term (it's a genuinely better UX than a static report) but a
  bigger `webapp` surface change; sequencing it after the report keeps this
  pass scoped.

## Consequences

- Good: raw backups exist independent of pipeline success/failure downstream
  — a page that fails block conversion still has its content preserved.
  Analysis/report/vault-sync stages are additive; nothing in phase 1 changes
  existing `image_mode`/`clean_llm`/`blocks` behavior.
- Cost / trade-off: two WXR files per run instead of one; more disk usage
  (raw HTML per page) for large migrations. No toggle added yet to disable
  the raw backup — cheap enough that it wasn't worth the config surface for
  a first pass; revisit if migrations get large enough to matter.
- Now-forbidden: don't reintroduce per-run-only template config (defeats the
  point of the vault-backed learning loop) — new per-client settings belong
  in `vault/70-Templates/`, not a transient `config.toml` block.

## Supersedes / superseded by
- None yet.
