"""Fetch an Order Desk help page and split it into searchable sections.

The highest-leverage part of the whole CLI. WordPress pages are wrapped in nav,
sidebar, footer, and "related articles" chrome, so we extract the main content
first with the `defuddle` CLI (clean markdown, no page chrome) and then chunk
it for the index.

Chunking is HYBRID, because the real corpus is mixed (verified against live
pages, June 2026):

  * Integration guides and most how-to articles carry markdown headings
    (## .. ####). There we split on heading boundaries and keep each section's
    heading path + anchor URL so results deep-link to the right section.
  * Short "101" explainer articles have NO headings at all — just paragraphs.
    There we pack consecutive paragraphs into coherent ~target-size passages
    rather than emitting one giant page-sized chunk.
  * Category/landing pages have empty content (wordCount 0); the caller skips
    those — they are navigation, not articles.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, asdict
from typing import Iterator

USER_AGENT = (
    "orderdesk-kb/0.1 (+internal KB indexer; public docs only)"
)
FETCH_TIMEOUT_SECONDS = 45
# Target characters per paragraph-packed chunk for heading-less pages. Big
# enough to be a coherent passage, small enough that search lands precisely.
TARGET_CHUNK_CHARS = 800
# Drop trailing scraps shorter than this when they stand alone.
MIN_CHUNK_CHARS = 60
# A section must carry at least this much body to be worth indexing. Below it,
# the "section" is really a bare heading whose content (image, embed, empty
# list) was stripped — it matches on heading words but answers nothing.
MIN_BODY_CHARS = 15

_HEADING_RE = re.compile(r"^(#{2,4})\s+(.*\S)\s*$")
# Standalone image markdown carries no searchable text — drop it so chunks
# aren't dominated by screenshot links (verified on integration-guide pages).
_IMAGE_LINE_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")


# defuddle leaves some raw HTML in its markdown (video embeds, the odd script).
# Remove these block elements tag-AND-contents so a section that is "just an
# iframe" collapses to empty and drops out of the index instead of ranking.
_HTML_BLOCK_RE = re.compile(
    r"<(iframe|script|style|noscript)\b[^>]*>.*?</\1>", re.I | re.S
)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_images(text: str) -> str:
    # Drop video/script/style blocks entirely (tag + contents).
    text = _HTML_BLOCK_RE.sub("", text)
    # Drop any remaining stray HTML tags but keep their inner text.
    text = _HTML_TAG_RE.sub("", text)
    lines = [ln for ln in text.splitlines() if not _IMAGE_LINE_RE.match(ln)]
    # Also strip inline image markdown embedded mid-paragraph.
    cleaned = "\n".join(lines)
    cleaned = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", cleaned)
    return cleaned.strip()


@dataclass(frozen=True)
class Section:
    """One indexable chunk: a passage plus where it came from."""

    url: str           # canonical page URL
    anchor_url: str    # url + #slug so results deep-link to the section
    title: str         # page title (h1)
    heading: str       # this section's heading, or "" for heading-less prose
    heading_path: str  # "Page Title > Parent > Heading"
    text: str          # the passage body, plain text


@dataclass(frozen=True)
class Page:
    """Extracted page metadata plus its sections."""

    url: str
    title: str
    published: str     # first ISO timestamp defuddle reports, or ""
    word_count: int
    sections: list[Section]


def extract_page(url: str) -> Page:
    """Run defuddle on a URL and return cleaned metadata + chunked sections.

    defuddle fetches the URL itself, strips chrome, and emits JSON with the
    main content as markdown. Returns a Page with empty sections when the page
    has no real content (category/landing pages) so the caller can skip it.
    """
    result = subprocess.run(
        ["defuddle", "parse", url, "--md", "--json"],
        capture_output=True,
        text=True,
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"defuddle failed for {url}: {result.stderr.strip()}")

    payload = json.loads(result.stdout)
    title = (payload.get("title") or _title_from_url(url)).strip()
    content = _strip_images((payload.get("content") or "").strip())
    word_count = int(payload.get("wordCount") or 0)
    published = _first_timestamp(payload.get("published"))

    sections = [
        s
        for s in _chunk(content, url, title)
        if not _is_video_stub(s) and len(s.text.strip()) >= MIN_BODY_CHARS
    ] if content else []
    return Page(
        url=url,
        title=title,
        published=published,
        word_count=word_count,
        sections=sections,
    )


# A "Watch and Learn" section whose embedded video has been stripped is just a
# content-free pointer ("Are you a visual learner? Watch below."). These ranked
# too high (BM25 over-rewards short sections) and answer nothing, so drop them.
# Deliberately content-specific, NOT length-based: many genuinely useful
# sections are short (e.g. "Click Remove Access to remove a user").
_VIDEO_HEADING_RE = re.compile(r"\b(watch|video)\b", re.I)
_VIDEO_STUB_MAX_CHARS = 160


def _is_video_stub(section: "Section") -> bool:
    if not section.heading or not _VIDEO_HEADING_RE.search(section.heading):
        return False
    return len(section.text) <= _VIDEO_STUB_MAX_CHARS


def _first_timestamp(value: object) -> str:
    """defuddle sometimes reports 'ts,ts' (duplicated); keep the first."""
    if not value:
        return ""
    return str(value).split(",")[0].strip()


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return slug.replace("-", " ").title()


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _chunk(content: str, url: str, title: str) -> Iterator[Section]:
    """Dispatch to heading-based or paragraph-based chunking."""
    has_headings = any(_HEADING_RE.match(line) for line in content.splitlines())
    if has_headings:
        yield from _chunk_by_heading(content, url, title)
    else:
        yield from _chunk_by_paragraph(content, url, title)


def _chunk_by_heading(content: str, url: str, title: str) -> Iterator[Section]:
    """Split on ## .. #### boundaries, carrying the nearest H2 as parent."""
    heading = ""
    parent = ""
    buffer: list[str] = []

    def emit() -> Iterator[Section]:
        body = "\n".join(buffer).strip()
        buffer.clear()
        if len(body) < MIN_CHUNK_CHARS and not heading:
            return
        if not body and not heading:
            return
        parts = [title]
        if parent and parent != heading:
            parts.append(parent)
        if heading:
            parts.append(heading)
        anchor = f"{url}#{_slugify(heading)}" if heading else url
        yield Section(
            url=url,
            anchor_url=anchor,
            title=title,
            heading=heading,
            heading_path=" > ".join(parts),
            text=body,
        )

    for line in content.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            yield from emit()
            level = len(match.group(1))
            text = match.group(2).strip()
            if level == 2:
                parent = text
            heading = text
        else:
            buffer.append(line)
    yield from emit()


def _chunk_by_paragraph(content: str, url: str, title: str) -> Iterator[Section]:
    """Pack blank-line-separated paragraphs into ~TARGET_CHUNK_CHARS passages."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    buffer: list[str] = []
    size = 0
    index = 0

    def emit() -> Iterator[Section]:
        nonlocal index
        body = "\n\n".join(buffer).strip()
        buffer.clear()
        if len(body) < MIN_CHUNK_CHARS:
            return
        anchor = url if index == 0 else f"{url}#section-{index}"
        index += 1
        yield Section(
            url=url,
            anchor_url=anchor,
            title=title,
            heading="",
            heading_path=title,
            text=body,
        )

    for paragraph in paragraphs:
        buffer.append(paragraph)
        size += len(paragraph)
        if size >= TARGET_CHUNK_CHARS:
            yield from emit()
            size = 0
    yield from emit()


def section_to_dict(section: Section) -> dict:
    return asdict(section)
