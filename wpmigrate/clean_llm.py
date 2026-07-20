"""LLM cleanup step (required — arbitrary sites are never deterministically clean).

The model's ONLY job is to turn messy extracted HTML into a small, constrained
whitelist of tags, dropping leftover boilerplate (share bars, related-posts,
newsletter CTAs, cookie notices) that content-extraction missed. It must NOT:
  - emit Gutenberg block markup (that's the deterministic step's job),
  - touch, reorder, or invent ⟦IMG_n⟧ tokens (image placement stays exact).

Keeping the model on judgment (what is content) and off mechanics (block wrapping,
image URLs) is what keeps hundreds of pages consistent.
"""
from __future__ import annotations

import re

import anthropic

WHITELIST = "h2, h3, h4, p, ul, ol, li, blockquote, pre, code, table, thead, "\
    "tbody, tr, th, td, strong, em, a, br, hr, sup, sub"

SYSTEM_PROMPT = f"""\
You clean up article HTML extracted from arbitrary websites so it can be \
converted into WordPress content. You output HTML only.

Rules:
1. Output ONLY these tags: {WHITELIST}. Convert any h1 to h2. Drop every other \
tag (div, span, section, figure, figcaption, iframe, script, style, nav, \
button, form, img) but KEEP their meaningful text content by unwrapping.
2. On <a> keep only the href attribute. Strip all other attributes from all tags.
3. Remove boilerplate that is not part of the article body: navigation, share/\
social buttons, "related posts", author bios, newsletter or subscribe prompts, \
cookie/consent notices, comment sections, ad labels, breadcrumb trails.
4. Image placeholder tokens look like ⟦IMG_0⟧, ⟦IMG_1⟧, etc. Preserve every \
token EXACTLY as written, each alone in its own <p>, in its original order. \
Never add, remove, renumber, or reword a token.
5. Do not add commentary, titles, or a wrapping document element. Do not wrap \
the output in Markdown code fences. Return the cleaned HTML fragment only.
6. Preserve the reading order and all substantive text. Do not summarize or \
rewrite prose — only restructure and strip.
"""

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n|\n```$")


def clean(client: anthropic.Anthropic, cfg, title: str, content_html: str) -> str:
    """Return constrained whitelist HTML. `cfg` is a config.Config."""
    user = (
        f"Article title (for context; do NOT include it in the body): {title}\n\n"
        f"Extracted HTML to clean:\n\n{content_html}"
    )
    # Stream + get_final_message: content can be long, which risks HTTP timeouts
    # on a plain non-streaming call.
    with client.messages.stream(
        model=cfg.model,
        max_tokens=cfg.llm_max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": cfg.effort},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RuntimeError("LLM refused to clean this page (safety stop).")

    text = "".join(b.text for b in message.content if b.type == "text").strip()
    # Defensive: strip a stray Markdown fence if the model added one anyway.
    text = _FENCE_RE.sub("", text).strip()
    return text
