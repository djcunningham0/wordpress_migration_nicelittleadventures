import html
import json
import logging
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import mdformat
from bs4 import NavigableString, Tag
from lxml import etree
from markdownify import MarkdownConverter
from slugify import slugify

from src.config import AUTHOR_OVERRIDES
from src.parsing.excerpts import parse_custom_excerpt
from src.parsing.images import strip_wp_size_suffix
from src.parsing.youtube import create_youtube_shortcode


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

USED_SLUGS: set[str] = set()


@dataclass
class Post:
    post_type: Literal["post", "page"]
    status: Literal["publish", "draft", "pending", "trash"]
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
            return create_youtube_shortcode(inner)
        return f"<figure>\n{inner}\n</figure>\n"

    def convert_iframe(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"{el}\n"


def _get_converter() -> WPMarkdownConverter:
    return WPMarkdownConverter(**MARKDOWNIFY_ARGS)


def parse_wordpress_xml(xml_path: Path, skip_ids: list[str | int] = None) -> list[Post]:
    skip_ids = skip_ids or []
    skip_ids = [str(x) for x in skip_ids]
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
    if not slug:
        slug = title  # example: draft posts don't have slugs
    if not slug:
        warnings.warn(
            f"Found empty slug for post {id_}. Generating a new slug with root 'empty-slug"
        )
        slug = "empty-slug"

    slug = create_unique_slug(slug, used_slugs=USED_SLUGS)

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


def create_unique_slug(slug: str, used_slugs: set[str]):
    """Force slugs to a common format (lowercase, hyphenated), and make sure they are
    unique among previously seen slugs. Add an incrementing number if the slug has
    previously been seen."""
    slug = slugify(slug)
    if slug not in used_slugs:
        used_slugs.add(slug)
        return slug

    n = 2
    while f"{slug}-{n}" in used_slugs:
        n += 1

    out = f"{slug}-{n}"
    used_slugs.add(out)
    return out


def _parse_authors(item: etree._Element, nsmap: dict[str, str]) -> str | list[str]:
    """Parse the author(s) from a WordPress XML item."""
    overrides = AUTHOR_OVERRIDES
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
