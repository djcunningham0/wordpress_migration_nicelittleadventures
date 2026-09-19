import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

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
        self.is_draft = self.status in ["draft", "pending"]
        self.markdown = content_to_markdown(self._content, self._footnotes_json)
        self.subtitle, self.excerpt = parse_custom_excerpt(self._excerpt)

    def __repr__(self):
        return f"Post(title={self.title}, id_={self.id_}, type={self.post_type}, author={self.author}, date={self.date})"


class WPMarkdownConverter(MarkdownConverter):
    """Converts WordPress block HTML to Markdown, keeping images/video as
    raw HTML for figure/caption/column flexibility in Hugo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images: list[str] = []  # collected as a side effect of conversion
        self.videos: list[str] = []

    def convert_img(
        self,
        el: Tag,
        text: str,
        parent_tags: set,
        override_src: str | None = None,
    ) -> str:
        src = override_src or el.get("src", "")
        alt = el.get("alt", "")
        if src:
            self.images.append(src)
        attrs = f'src="{src}"'
        if alt:
            attrs += f' alt="{alt}"'
        return f"<img {attrs}/>\n"

    def convert_video(self, el: Tag, text: str, parent_tags: set) -> str:
        src = el.get("src", "")
        if src:
            self.videos.append(src)
        attrs = f'src="{src}"'
        if el.get("controls") is not None:
            attrs = f"controls {attrs}"
        if el.get("playsinline") is not None:
            attrs += " playsinline"
        return f"<video {attrs}></video>\n"

    def convert_figcaption(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"<figcaption>{text.strip()}</figcaption>\n"

    def convert_a(self, el: Tag, text: str, parent_tags: set) -> str:
        children = [
            c
            for c in el.children
            if not (isinstance(c, NavigableString) and not c.strip())
        ]

        # Self-linking image: <a href="..."><img/></a> with nothing else inside.
        # Use the href image rather than the src value from the <img> tag. (Convention:
        # the images on my Wordpress site link to full-res versions of themselves.))
        if len(children) == 1 and children[0].name == "img":
            return self.convert_img(
                children[0], "", parent_tags, override_src=el.get("href")
            )
        return super().convert_a(el, text, parent_tags)

    def convert_figure(self, el: Tag, text: str, parent_tags: set) -> str:
        print(f"{el=}")
        inner = text.strip("\n")
        print(f"{el.get("class")=}")
        if "is-provider-youtube" in el.get("class", []):
            return self._convert_youtube_embed(inner)
        return f"<figure>\n{inner}\n</figure>\n"

    def _convert_youtube_embed(self, text: str):
        print("here")
        url = text.split("v=")[1].split("&")[0]
        return f"{{{{< youtube {url} >}}}}"


def convert(html: str) -> str:
    return WPMarkdownConverter(**MARKDOWNIFY_ARGS).convert(html).strip()


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
        content_md = convert(content_html)
        definitions.append(f"[^{n}]: {content_md}")

    return body + "\n\n" + "\n".join(definitions)


def content_to_markdown(html_content: str, footnotes_json: list[dict[str, str]]) -> str:
    """Convert HTML content to Markdown."""

    if not html_content:
        return ""

    html_content = replace_footnote_markers_with_placeholders(html_content)
    markdown = convert(html_content)
    markdown = resolve_footnotes(markdown, footnotes_json)

    # prettify markdown
    markdown = mdformat.text(
        markdown,
        options={"wrap": "keep", "number": True},
        extensions=["footnote", "simple_breaks", "frontmatter", "gfm"],
    )

    return markdown


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
