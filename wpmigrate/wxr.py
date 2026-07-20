"""Build a WordPress eXtended RSS (WXR) document from converted pages.

Import via WP admin: Tools -> Import -> WordPress. Each page becomes one <item>
with the Gutenberg block markup in <content:encoded> (CDATA).

Image handling in the export:
  - Normal modes reference image URLs inline in the block markup.
  - "Sideload" mode (emit_attachments=True) additionally emits one attachment
    <item> per image, carrying <wp:attachment_url> = the source URL and
    parented to its page. With "Download and import file attachments" checked,
    the WordPress importer fetches each one server-side into the media library
    and remaps the inline <img> URLs to the new local copies. This is the way
    to get images into a managed target that blocks the REST API.
"""
from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import unquote, urlparse

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class Page:
    title: str
    link: str
    content_blocks: str
    # (source_url, alt) per image; only used when emit_attachments is True.
    images: list[tuple[str, str]] = field(default_factory=list)


def slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug or "page"


def _cdata(text: str) -> str:
    # CDATA cannot contain the literal "]]>"; split it if present.
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _img_title(src: str) -> str:
    name = os.path.basename(urlparse(src).path)
    name = unquote(os.path.splitext(name)[0]).replace("_", " ").replace("-", " ")
    return name.strip() or "image"


def _content_item(page: Page, post_id: int, author: str, post_type: str,
                  status: str, pub: str, date_gmt: str) -> str:
    slug = slugify(page.title)
    return f"""\
    <item>
        <title>{html.escape(page.title)}</title>
        <link>{html.escape(page.link)}</link>
        <pubDate>{pub}</pubDate>
        <dc:creator>{_cdata(author)}</dc:creator>
        <guid isPermaLink="false">{html.escape(page.link)}</guid>
        <description></description>
        <content:encoded>{_cdata(page.content_blocks)}</content:encoded>
        <excerpt:encoded>{_cdata("")}</excerpt:encoded>
        <wp:post_id>{post_id}</wp:post_id>
        <wp:post_date>{date_gmt}</wp:post_date>
        <wp:post_date_gmt>{date_gmt}</wp:post_date_gmt>
        <wp:comment_status>closed</wp:comment_status>
        <wp:ping_status>closed</wp:ping_status>
        <wp:post_name>{_cdata(slug)}</wp:post_name>
        <wp:status>{status}</wp:status>
        <wp:post_parent>0</wp:post_parent>
        <wp:menu_order>0</wp:menu_order>
        <wp:post_type>{post_type}</wp:post_type>
        <wp:post_password></wp:post_password>
        <wp:is_sticky>0</wp:is_sticky>
    </item>"""


def _attachment_item(src: str, alt: str, post_id: int, parent_id: int,
                     author: str, pub: str, date_gmt: str) -> str:
    title = alt.strip() or _img_title(src)
    return f"""\
    <item>
        <title>{html.escape(title)}</title>
        <link>{html.escape(src)}</link>
        <pubDate>{pub}</pubDate>
        <dc:creator>{_cdata(author)}</dc:creator>
        <guid isPermaLink="false">{html.escape(src)}</guid>
        <description></description>
        <content:encoded>{_cdata("")}</content:encoded>
        <excerpt:encoded>{_cdata("")}</excerpt:encoded>
        <wp:post_id>{post_id}</wp:post_id>
        <wp:post_date>{date_gmt}</wp:post_date>
        <wp:post_date_gmt>{date_gmt}</wp:post_date_gmt>
        <wp:comment_status>closed</wp:comment_status>
        <wp:ping_status>closed</wp:ping_status>
        <wp:post_name>{_cdata(slugify(title))}</wp:post_name>
        <wp:status>inherit</wp:status>
        <wp:post_parent>{parent_id}</wp:post_parent>
        <wp:menu_order>0</wp:menu_order>
        <wp:post_type>attachment</wp:post_type>
        <wp:post_password></wp:post_password>
        <wp:is_sticky>0</wp:is_sticky>
        <wp:attachment_url>{html.escape(src)}</wp:attachment_url>
        <wp:postmeta>
            <wp:meta_key>_wp_attachment_image_alt</wp:meta_key>
            <wp:meta_value>{_cdata(alt)}</wp:meta_value>
        </wp:postmeta>
    </item>"""


def build_wxr(pages: list[Page], *, author: str, post_type: str,
              status: str, site_title: str = "Imported Content",
              emit_attachments: bool = False) -> str:
    now = datetime.now(timezone.utc)
    pub = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    date_gmt = now.strftime("%Y-%m-%d %H:%M:%S")

    items: list[str] = []
    next_id = 1
    for page in pages:
        page_id = next_id
        next_id += 1
        items.append(_content_item(page, page_id, author, post_type, status,
                                   pub, date_gmt))
        if emit_attachments:
            for src, alt in page.images:
                att_id = next_id
                next_id += 1
                items.append(_attachment_item(src, alt, att_id, page_id,
                                              author, pub, date_gmt))

    body = "\n".join(items)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
    xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.2/">
<channel>
    <title>{html.escape(site_title)}</title>
    <link>https://example.com</link>
    <description>Migrated content</description>
    <pubDate>{pub}</pubDate>
    <language>en-US</language>
    <wp:wxr_version>1.2</wp:wxr_version>
    <wp:author>
        <wp:author_login>{_cdata(author)}</wp:author_login>
        <wp:author_display_name>{_cdata(author)}</wp:author_display_name>
    </wp:author>
{body}
</channel>
</rss>
"""
