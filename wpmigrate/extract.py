"""Main-content extraction and image tokenization.

Two ways to isolate the content area:
  1. A per-domain CSS selector override (config `selectors`) — take that node's
     inner HTML directly. Best for sites where you know the wrapper.
  2. trafilatura auto-extraction — strips nav/header/footer/sidebars/boilerplate
     across arbitrary hosts. The default.

Every <img> (and trafilatura's <graphic>) is then replaced in-place with a stable
text token like ⟦IMG_3⟧, so the downstream LLM cleanup can't reorder or mangle
images. The original absolute src/alt is recorded against each token index.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup

TOKEN_TEMPLATE = "⟦IMG_{n}⟧"          # ⟦IMG_n⟧
TOKEN_RE = re.compile(r"⟦IMG_(\d+)⟧")  # matches ⟦IMG_n⟧


@dataclass
class ImageRef:
    index: int
    src: str            # absolute URL
    alt: str = ""


@dataclass
class Extracted:
    title: str
    html: str                 # content HTML with image tokens in place
    images: list[ImageRef]    # ordered by token index


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


# Headings that live in every page's shared template, not its real content.
_BOILERPLATE_HEADINGS = {"join our email club today!", "news & events"}


def _extract_title(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    # Prefer the first real content heading, then <title>, then og:title.
    #
    # A page's own <h1>/<h2> is more distinctive than its <title>: many CMS
    # templates emit an identical, site-wide <title> (e.g. just the location or
    # brand) on every page, which would collide into duplicate post names. To
    # find the *content* heading we first drop the chrome (nav/header/footer/
    # aside/form) and known template CTAs, then take the first heading left.
    chrome = soup.find("body") or soup
    work = BeautifulSoup(str(chrome), "lxml")
    for junk in work.find_all(["nav", "header", "footer", "aside", "form"]):
        junk.decompose()
    cta = work.find(id="email-cta-heading")
    if cta:
        cta.decompose()
    for h in work.find_all(["h1", "h2", "h3"]):
        text = h.get_text(strip=True)
        if text and text.lower() not in _BOILERPLATE_HEADINGS:
            return text

    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        # Trim common " | Site Name" suffixes conservatively.
        return re.split(r"\s+[|–—-]\s+", title)[0].strip() or title
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content", "").strip():
        return og["content"].strip()
    return "Untitled"


def _content_html(raw_html: str, url: str, selector: str | None) -> str:
    if selector:
        soup = BeautifulSoup(raw_html, "lxml")
        node = soup.select_one(selector)
        if node is not None:
            return node.decode_contents()
        # Fall through to trafilatura if the override didn't match.
    extracted = trafilatura.extract(
        raw_html,
        output_format="html",
        include_images=True,
        include_links=True,
        include_formatting=True,
        include_tables=True,
        favor_recall=True,
        url=url,
    )
    return extracted or ""


def _tokenize_images(content_html: str, base_url: str) -> tuple[str, list[ImageRef]]:
    soup = BeautifulSoup(content_html, "lxml")
    images: list[ImageRef] = []
    n = 0
    for tag in soup.find_all(["img", "graphic"]):
        src = tag.get("src") or tag.get("data-src") or tag.get("url") or ""
        if not src:
            tag.decompose()
            continue
        abs_src = urljoin(base_url, src)
        alt = (tag.get("alt") or tag.get("title") or "").strip()
        images.append(ImageRef(index=n, src=abs_src, alt=alt))
        # Replace the tag with a standalone paragraph carrying just the token,
        # so it survives as a block-level element through LLM cleanup.
        token_p = soup.new_tag("p")
        token_p.string = TOKEN_TEMPLATE.format(n=n)
        tag.replace_with(token_p)
        n += 1
    # decode() on the soup's body if present, else the fragment as-is.
    body = soup.find("body")
    return (body.decode_contents() if body else str(soup)), images


def extract(raw_html: str, url: str, selectors: dict[str, str],
            title_override: str | None = None) -> Extracted:
    title = title_override or _extract_title(raw_html)
    selector = selectors.get(_host(url)) or selectors.get(urlparse(url).netloc)
    content_html = _content_html(raw_html, url, selector)
    if not content_html.strip():
        return Extracted(title=title, html="", images=[])
    tokenized, images = _tokenize_images(content_html, url)
    return Extracted(title=title, html=tokenized, images=images)
