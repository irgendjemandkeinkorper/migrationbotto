"""Deterministic conversion: constrained whitelist HTML -> Gutenberg block markup.

Gutenberg blocks are ordinary HTML wrapped in special HTML comments, e.g.
    <!-- wp:paragraph --><p>Hi</p><!-- /wp:paragraph -->
Because the input is already a small, LLM-normalized whitelist, this mapping is
reliable. Image tokens (⟦IMG_n⟧) are expanded here using the media map built by
the image pipeline, so positions come from the source DOM, never guessed.
"""
from __future__ import annotations

import html as html_lib
import re

from bs4 import BeautifulSoup, NavigableString, Tag

from .extract import TOKEN_RE
from .images import MediaResult

# Inline tags allowed to remain inside block text content.
_INLINE_OK = {"a", "strong", "em", "b", "i", "code", "br", "sup", "sub", "u"}


def _sanitize_inline(node: Tag) -> None:
    """Unwrap disallowed inline tags and strip attributes (keep href on <a>)."""
    for tag in node.find_all(True):
        if tag.name not in _INLINE_OK:
            tag.unwrap()
            continue
        if tag.name == "a":
            href = tag.get("href")
            tag.attrs = {"href": href} if href else {}
        else:
            tag.attrs = {}


def _inner_html(node: Tag) -> str:
    _sanitize_inline(node)
    return node.decode_contents().strip()


def _image_block(media: MediaResult) -> str:
    alt = html_lib.escape(media.alt or "", quote=True)
    if media.media_id is not None:
        attrs = f'{{"id":{media.media_id},"sizeSlug":"large"}}'
        img = (
            f'<img src="{media.url}" alt="{alt}" '
            f'class="wp-image-{media.media_id}"/>'
        )
    else:
        attrs = "{}"
        img = f'<img src="{media.url}" alt="{alt}"/>'
    return (
        f"<!-- wp:image {attrs} -->\n"
        f'<figure class="wp-block-image size-large">{img}</figure>\n'
        f"<!-- /wp:image -->"
    )


def _paragraph_block(inner: str) -> str:
    if not inner.strip():
        return ""
    return f"<!-- wp:paragraph -->\n<p>{inner}</p>\n<!-- /wp:paragraph -->"


def _heading_block(level: int, inner: str) -> str:
    lvl = min(max(level, 2), 4)
    return (
        f'<!-- wp:heading {{"level":{lvl}}} -->\n'
        f"<h{lvl}>{inner}</h{lvl}>\n"
        f"<!-- /wp:heading -->"
    )


def _list_block(node: Tag) -> str:
    ordered = node.name == "ol"
    items = []
    for li in node.find_all("li", recursive=False):
        items.append(
            f"<!-- wp:list-item -->\n<li>{_inner_html(li)}</li>\n<!-- /wp:list-item -->"
        )
    tag = "ol" if ordered else "ul"
    attr = '{"ordered":true} ' if ordered else ""
    body = "\n".join(items)
    return (
        f"<!-- wp:list {attr}-->\n"
        f'<{tag} class="wp-block-list">\n{body}\n</{tag}>\n'
        f"<!-- /wp:list -->"
    )


def _quote_block(node: Tag) -> str:
    inner_paras = []
    for child in node.find_all("p", recursive=False):
        inner_paras.append(_paragraph_block(_inner_html(child)))
    if not inner_paras:  # bare text inside blockquote
        inner_paras.append(_paragraph_block(_inner_html(node)))
    body = "\n".join(p for p in inner_paras if p)
    return f"<!-- wp:quote -->\n<blockquote class=\"wp-block-quote\">\n{body}\n</blockquote>\n<!-- /wp:quote -->"


def _code_block(node: Tag) -> str:
    text = html_lib.escape(node.get_text())
    return f"<!-- wp:code -->\n<pre class=\"wp-block-code\"><code>{text}</code></pre>\n<!-- /wp:code -->"


def _table_block(node: Tag) -> str:
    for tag in node.find_all(True):
        if tag.name not in {"table", "thead", "tbody", "tr", "th", "td"}:
            tag.unwrap()
        else:
            tag.attrs = {}
    node.attrs = {}
    node["class"] = "wp-block-table__table"
    return (
        f'<!-- wp:table -->\n<figure class="wp-block-table">{str(node)}</figure>\n'
        f"<!-- /wp:table -->"
    )


def _expand_tokens_in_text(text: str, media_map: dict[int, MediaResult]) -> list[str]:
    """Split a text run on image tokens, yielding paragraph and image blocks."""
    out: list[str] = []
    pos = 0
    for m in TOKEN_RE.finditer(text):
        before = text[pos:m.start()].strip()
        if before:
            out.append(_paragraph_block(html_lib.escape(before)))
        idx = int(m.group(1))
        media = media_map.get(idx)
        if media is not None:
            out.append(_image_block(media))
        pos = m.end()
    tail = text[pos:].strip()
    if tail:
        out.append(_paragraph_block(html_lib.escape(tail)))
    return out


def to_blocks(clean_html: str, media_map: dict[int, MediaResult]) -> str:
    soup = BeautifulSoup(clean_html, "lxml")
    root = soup.find("body") or soup
    blocks: list[str] = []

    for child in root.children:
        if isinstance(child, NavigableString):
            text = str(child)
            if text.strip():
                blocks.extend(_expand_tokens_in_text(text, media_map))
            continue
        if not isinstance(child, Tag):
            continue

        name = child.name
        raw_text = child.get_text()

        # A block-level element that is (or contains) image tokens.
        if TOKEN_RE.search(raw_text) and name in {"p", "div", "figure"}:
            blocks.extend(_expand_tokens_in_text(raw_text, media_map))
            continue

        if name == "p":
            blocks.append(_paragraph_block(_inner_html(child)))
        elif name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            blocks.append(_heading_block(level, _inner_html(child)))
        elif name in {"ul", "ol"}:
            blocks.append(_list_block(child))
        elif name == "blockquote":
            blocks.append(_quote_block(child))
        elif name == "pre":
            blocks.append(_code_block(child))
        elif name == "table":
            blocks.append(_table_block(child))
        elif name == "hr":
            blocks.append("<!-- wp:separator -->\n<hr class=\"wp-block-separator\"/>\n<!-- /wp:separator -->")
        else:
            # Unknown wrapper: recurse into its meaningful children as paragraphs.
            inner = _inner_html(child)
            if inner:
                blocks.append(_paragraph_block(inner))

    return "\n\n".join(b for b in blocks if b.strip())
