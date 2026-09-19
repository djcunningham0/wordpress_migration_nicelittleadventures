import html
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse, parse_qs

import mdformat
from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree
from markdownify import MarkdownConverter


logger = logging.getLogger(__name__)

MARKDOWNIFY_ARGS = {
    "heading_style": "ATX",
    "bullets": "-",
    "strong_em_symbol": "*",
    "escape_asterisks": True,
    "escape_underscores": True,
    "wrap": False,
    "autolinks": False,
}

# footnote pattern in the HTML content, e.g. <sup data-fn="uuid">1</sup>
FOOTNOTE_PLACEHOLDER_RE = re.compile(
    r'<sup[^>]*data-fn="([0-9a-f-]+)"[^>]*>.*?</sup>',
    re.DOTALL,
)


@dataclass
class Post:
    post_type: Literal["post", "page"]
    status: Literal["publish", "draft", "pending"]
    title: str
    id_: str
    slug: str
    author: str | list[str]
    _content: str
    date: str
    categories: list[str]
    tags: list[str]
    _excerpt: str
    _footnotes_json: list[dict[str, str]]

    def __post_init__(self):
        self.is_draft: bool = self.status in ["draft", "pending"]
        self.subtitle, self.excerpt = parse_custom_excerpt(self._excerpt)
        result = content_to_markdown(
            html_content=self._content, footnotes_json=self._footnotes_json
        )
        self.markdown: str = result.markdown
        self.images: set[str] = result.images
        self.videos: set[str] = result.videos

    def __repr__(self):
        return f"Post(title={self.title}, id_={self.id_}, type={self.post_type}, author={self.author}, date={self.date})"


@dataclass
class MarkdownOutput:
    markdown: str
    images: set[str] = field(default_factory=set)
    videos: set[str] = field(default_factory=set)


class WPMarkdownConverter(MarkdownConverter):
    """Converts WordPress block HTML to Markdown, keeping images, videos, and embeds as
    raw HTML for flexibility in Hugo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images: set[str] = set()  # collected as a side effect of conversion
        self.videos: set[str] = set()

    def convert_img(self, el: Tag, text: str, parent_tags: set) -> str:
        src = el.get("src", "")
        alt = el.get("alt", "")

        # self linking images will have an <a> parent tag linking to the full resolution image
        if el.parent is not None and el.parent.name == "a":
            href = el.parent.get("href", "")
            if strip_wp_size_suffix(href) == strip_wp_size_suffix(src):
                src = href

        if src:
            self.images.add(src)

        attrs = f'src="{html.escape(src)}"'
        if alt:
            attrs += f' alt="{html.escape(alt)}"'
        return f"<img {attrs}/>\n"

    def convert_video(self, el: Tag, text: str, parent_tags: set) -> str:
        src = el.get("src", "")
        if src:
            self.videos.add(src)

        attrs = []
        if el.get("controls") is not None:
            attrs.append("controls")
        if el.get("playsinline") is not None:
            attrs.append("playsinline")

        attrs.append(f'src="{html.escape(src)}"')
        attrs = " ".join(attrs)
        return f"<video {attrs}></video>\n"

    def convert_figcaption(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"<figcaption>{text.strip()}</figcaption>\n"

    def convert_a(self, el: Tag, text: str, parent_tags: set) -> str:
        children = [
            c
            for c in el.children
            if not (isinstance(c, NavigableString) and not c.strip())
        ]

        # Self-linking image: <a href="..."><img/></a> with nothing else inside. These
        # are handled by `self.convert_img`, so no additional processing needed here.
        if len(children) == 1 and getattr(children[0], "name", None) == "img":
            return text

        return super().convert_a(el, text, parent_tags)

    def convert_figure(self, el: Tag, text: str, parent_tags: set) -> str:
        inner = text.strip("\n")
        if "is-provider-youtube" in el.get("class", []):
            return self._convert_youtube_embed(inner)
        return f"<figure>\n{inner}\n</figure>\n"

    def convert_iframe(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"{el}\n"

    @staticmethod
    def _convert_youtube_embed(text: str):
        youtube_id = extract_youtube_id(text)
        return f"{{{{< youtube {youtube_id} >}}}}"


def extract_youtube_id(url: str) -> str | None:
    """Extract the YouTube video ID from a URL. Returns the video ID, or None if it
    can't be found.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""

    # Strip leading "www." for easier matching
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # youtu.be/VIDEO_ID
    if hostname == "youtu.be":
        video_id = parsed.path.lstrip("/")
        return video_id if video_id else None

    if hostname in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        # /watch?v=VIDEO_ID
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            video_id = query.get("v")
            return video_id[0] if video_id else None

        # /embed/VIDEO_ID or /v/VIDEO_ID or /shorts/VIDEO_ID or /live/VIDEO_ID
        for prefix in ("/embed/", "/v/", "/shorts/", "/live/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix) :].split("/")[0]
                return video_id if video_id else None

    return None


def strip_wp_size_suffix(url: str) -> str:
    """Remove a trailing WordPress resize suffix like '-1024x768' before the
    extension.

    Example:
    >>> url = "https://example.com/wp-content/uploads/image-1024x768.jpg"
    >>> strip_wp_size_suffix(url)
    'https://example.com/wp-content/uploads/image.jpg'
    """
    return re.sub(r"-\d+x\d+(?=\.\w+(?:\?.*)?$)", "", url)


def _get_converter() -> WPMarkdownConverter:
    return WPMarkdownConverter(**MARKDOWNIFY_ARGS)


def parse_wordpress_xml(xml_path: Path, skip_ids: list[str] = None) -> list[Post]:
    skip_ids = skip_ids or []
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    nsmap = {k: v for k, v in root.nsmap.items() if k is not None}
    logger.debug(f"Namespace map: {nsmap}")

    posts = []
    for item in root.findall(".//channel/item"):
        if (id_ := item.findtext("wp:post_id", namespaces=nsmap)) in skip_ids:
            logger.debug(f"Skipping post with ID {id_}")
            continue
        post_type = item.findtext("wp:post_type", namespaces=nsmap)
        if post_type in ("post", "page"):
            posts.append(parse_post(item, nsmap))

    logger.info(f"parsed {len(posts):,} posts and pages from XML file {xml_path}")
    return posts


def parse_post(item: etree._Element, nsmap: dict[str, str]) -> Post:
    post_type = item.findtext("wp:post_type", namespaces=nsmap)
    status = item.findtext("wp:status", namespaces=nsmap)
    title = item.findtext("title")
    id_ = item.findtext("wp:post_id", namespaces=nsmap)
    slug = item.findtext("wp:post_name", namespaces=nsmap)
    author = _parse_authors(item, nsmap)
    content = item.findtext("content:encoded", namespaces=nsmap)
    date = item.findtext("wp:post_date", namespaces=nsmap)
    categories = [cat.text for cat in item.findall("category[@domain='category']")]
    tags = [tag.text for tag in item.findall("category[@domain='post_tag']")]
    excerpt = item.findtext("excerpt:encoded", namespaces=nsmap)

    footnotes_json = item.findtext(
        "wp:postmeta[wp:meta_key='footnotes']/wp:meta_value",
        namespaces=nsmap,
    )
    if footnotes_json:
        footnotes_json = json.loads(footnotes_json)
    else:
        footnotes_json = []

    return Post(
        post_type=post_type,
        status=status,
        title=title,
        id_=id_,
        slug=slug,
        author=author,
        _content=content,
        date=date,
        categories=categories,
        tags=tags,
        _excerpt=excerpt,
        _footnotes_json=footnotes_json,
    )


def _parse_authors(item: etree._Element, nsmap: dict[str, str]) -> str | list[str]:
    """Parse the author(s) from a WordPress XML item."""
    overrides = json.loads(os.environ.get("AUTHOR_OVERRIDES", "{}"))
    authors: list[str] = [x.text for x in item.findall("category[@domain='author']")]
    if not authors:
        # fallback to dc:creator
        creator: str = item.findtext("dc:creator", namespaces=nsmap)
        if creator:
            authors.append(creator)
    authors = [overrides.get(x, x) for x in authors]
    if len(authors) == 1:
        return authors[0]
    return authors


def replace_footnote_markers_with_placeholders(html: str) -> str:
    """Replace footnote pattern in the HTML content with @@FOOTNOTE:uuid@@ placeholders
    for easy replacement later. This way we don't have to worry about how `markdownify`
    handles the <sup> tags."""
    return FOOTNOTE_PLACEHOLDER_RE.sub(r"@@FOOTNOTE:\1@@", html)


def resolve_footnotes(markdown: str, footnotes: list[dict]) -> str:
    """Resolve footnote placeholders in the markdown content with actual footnote
    definitions."""

    footnotes_by_id = {fn["id"]: fn["content"] for fn in footnotes}
    order: list[str] = []  # ids in order of first appearance

    def repl(match: re.Match) -> str:
        fn_id = match.group(1)
        if fn_id not in order:
            order.append(fn_id)
        n = order.index(fn_id) + 1
        return f"[^{n}]"

    placeholder_re = re.compile(r"@@FOOTNOTE:([0-9a-f-]+)@@")
    body = placeholder_re.sub(repl, markdown)

    if not order:
        return body

    definitions = []
    for n, fn_id in enumerate(order, start=1):
        content_html = footnotes_by_id.get(fn_id, "")
        converter = _get_converter()
        content_md = converter.convert(content_html)
        definitions.append(f"[^{n}]: {content_md}")

    return body + "\n\n" + "\n".join(definitions)


def content_to_markdown(
    html_content: str,
    footnotes_json: list[dict[str, str]],
) -> MarkdownOutput:
    """Convert HTML content to Markdown."""

    if not html_content:
        return MarkdownOutput(markdown="")

    html_content = replace_footnote_markers_with_placeholders(html_content)
    converter = _get_converter()
    markdown = converter.convert(html_content).strip()
    markdown = resolve_footnotes(markdown, footnotes_json)

    # prettify markdown
    markdown = mdformat.text(
        markdown,
        options={"wrap": "keep", "number": True},
        extensions=["footnote", "simple_breaks", "frontmatter", "gfm"],
    )

    return MarkdownOutput(
        markdown=markdown, images=converter.images, videos=converter.videos
    )


def parse_custom_excerpt(excerpt: str) -> tuple[str, str]:
    """Parse the custom excerpt HTML to extract the subtitle and excerpt.

    Example:
    <hr>
    <h5 class="page-description"><i>
    This is the subtitle
    </i></h5>
    <p>
    And this is the excerpt text.
    </p>
    """
    if excerpt is None:
        return "", ""

    soup = BeautifulSoup(excerpt, "html.parser")
    subtitle = soup.select_one("h5.page-description")
    paragraph = soup.find("p")
    return (
        normalize(subtitle) if subtitle else "",
        normalize(paragraph) if paragraph else "",
    )


def normalize(element) -> str:
    """Normalize the text content of an HTML element by stripping whitespace and joining
    lines."""
    return " ".join(element.get_text().split())
