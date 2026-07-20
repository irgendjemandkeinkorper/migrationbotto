"""Build a WordPress eXtended RSS (WXR) document from converted pages.

Import via WP admin: Tools -> Import -> WordPress. Each page becomes one <item>
with the Gutenberg block markup in <content:encoded> (CDATA).
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone

_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class Page:
    title: str
    link: str
    content_blocks: str


def slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug or "page"


def _cdata(text: str) -> str:
    # CDATA cannot contain the literal "]]>"; split it if present.
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_wxr(pages: list[Page], *, author: str, post_type: str,
              status: str, site_title: str = "Imported Content") -> str:
    now = datetime.now(timezone.utc)
    pub = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    items: list[str] = []
    for i, page in enumerate(pages, start=1):
        slug = slugify(page.title)
        date_gmt = now.strftime("%Y-%m-%d %H:%M:%S")
        items.append(f"""\
    <item>
        <title>{html.escape(page.title)}</title>
        <link>{html.escape(page.link)}</link>
        <pubDate>{pub}</pubDate>
        <dc:creator>{_cdata(author)}</dc:creator>
        <guid isPermaLink="false">{html.escape(page.link)}</guid>
        <description></description>
        <content:encoded>{_cdata(page.content_blocks)}</content:encoded>
        <excerpt:encoded>{_cdata("")}</excerpt:encoded>
        <wp:post_id>{i}</wp:post_id>
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
    </item>""")

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
