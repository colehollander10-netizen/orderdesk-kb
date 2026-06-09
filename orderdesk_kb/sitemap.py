"""Read the Order Desk help sitemap to discover pages and their lastmod dates.

The KB is WordPress + Yoast, which publishes a sitemap index pointing at
per-type sitemaps (posts, pages). Each <url> carries a <lastmod>, which is what
makes incremental sync possible: we skip any URL whose lastmod matches what we
already indexed.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass

SITEMAP_INDEX = "https://help.orderdesk.com/sitemap_index.xml"
USER_AGENT = "orderdesk-kb/0.1 (+internal KB indexer; public docs only)"
FETCH_TIMEOUT_SECONDS = 30

_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.S)
_URL_BLOCK_RE = re.compile(r"<url>(.*?)</url>", re.S)
_LASTMOD_RE = re.compile(r"<lastmod>\s*(.*?)\s*</lastmod>", re.S)


@dataclass(frozen=True)
class SitemapEntry:
    url: str
    lastmod: str


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _child_sitemaps(index_xml: str) -> list[str]:
    return _LOC_RE.findall(index_xml)


def _entries_from_sitemap(xml: str) -> list[SitemapEntry]:
    entries: list[SitemapEntry] = []
    for block in _URL_BLOCK_RE.findall(xml):
        loc_match = _LOC_RE.search(block)
        if not loc_match:
            continue
        lastmod_match = _LASTMOD_RE.search(block)
        entries.append(
            SitemapEntry(
                url=loc_match.group(1),
                lastmod=lastmod_match.group(1) if lastmod_match else "",
            )
        )
    return entries


def fetch_all_entries(index_url: str = SITEMAP_INDEX) -> list[SitemapEntry]:
    """Return every article/page URL with its lastmod, de-duplicated by URL."""
    index_xml = _fetch(index_url)
    seen: dict[str, SitemapEntry] = {}
    for child in _child_sitemaps(index_xml):
        for entry in _entries_from_sitemap(_fetch(child)):
            seen[entry.url] = entry
    return list(seen.values())
