import json
import logging
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lxml import etree

from src.config import AUTHOR_OVERRIDES
from src.parsing.excerpts import parse_custom_excerpt
from src.parsing.markdown import content_to_markdown
from src.parsing.slugs import create_unique_slug


logger = logging.getLogger(__name__)

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
