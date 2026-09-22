from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from lxml import etree

from src.parsing.excerpts import parse_custom_excerpt
from src.parsing.markdown import content_to_markdown
from src.parsing.settings import ParseSettings
from src.parsing.slugs import create_unique_slug

logger = logging.getLogger(__name__)

USED_SLUGS: set[str] = set()


@dataclass
class Post:
    post_type: Literal["post", "page"]
    status: Literal["publish", "draft", "pending", "trash"]
    title: str
    id_: str
    author: str | list[str]
    date: str
    slug: str
    raw_content: str
    categories: list[str]
    tags: list[str]
    _raw_excerpt: str
    footnotes_json: list[dict[str, str]]

    def __post_init__(self):
        self.is_draft: bool = self.status in ["draft", "pending"]
        self.subtitle, self.excerpt = parse_custom_excerpt(self._raw_excerpt)

    def generate_markdown(
        self,
        post_id_to_slug: dict[str, str],
        media_by_id: dict[str, MediaObject],
        parse_settings: ParseSettings | None = None,
    ):
        result = content_to_markdown(
            html_content=self.raw_content,
            footnotes_json=self.footnotes_json,
            post_id_to_slug=post_id_to_slug,
            media_by_id=media_by_id,
            parse_settings=parse_settings,
        )
        self.markdown: str = result.markdown
        self.images: set[str] = result.images
        self.videos: set[str] = result.videos

    def __repr__(self):
        return f"Post(title={self.title}, id_={self.id_}, type={self.post_type}, author={self.author}, date={self.date})"


@dataclass
class MediaObject:
    """Images and videos.

    Parameters
    ----------
    id_
        Wordpress ID of the image
    url
        Full URL of the uploaded image (https://{HOSTNAME}.com/wp-content/uploads/path/to/image.jpg)
    file_path
        Relative file path of the uploaded image (path/to/image.jpg)
    file_name
        (calculated from `file_path`) Image file name (image.jpg)
    """

    id_: str
    url: str
    file_path: str

    def __post_init__(self):
        self.file_name: str = self.file_path.strip("/").split("/")[-1]


@dataclass
class SiteContents:
    posts: list[Post]
    media: list[MediaObject]
    parse_settings: ParseSettings | None = None

    def __post_init__(self):
        self._validate()
        self.process_posts()

    def _validate(self):
        post_ids = {x.id_ for x in self.posts}
        post_slugs = {x.slug for x in self.posts}
        media_ids = {x.id_ for x in self.media}
        if len(post_ids) != len(self.posts):
            raise ValueError("Found duplicate post IDs")
        if len(post_slugs) != len(self.posts):
            raise ValueError("Found duplicate post slugs")
        if len(media_ids) != len(self.media):
            raise ValueError("Found duplicate media IDs")
        if len(post_ids.union(media_ids)) != len(self.posts) + len(self.media):
            raise ValueError("Found duplicate IDs across posts and media")

    @property
    def posts_by_id(self) -> dict[str, Post]:
        return {x.id_: x for x in self.posts}

    @property
    def media_by_id(self) -> dict[str, MediaObject]:
        return {x.id_: x for x in self.media}

    @property
    def post_id_to_slug(self) -> dict[str, str]:
        return {x.id_: x.slug for x in self.posts}

    def process_posts(self):
        for post in self.posts:
            post.generate_markdown(
                post_id_to_slug=self.post_id_to_slug,
                media_by_id=self.media_by_id,
                parse_settings=self.parse_settings,
            )


def parse_wordpress_xml(
    xml_path: Path,
    parse_settings: ParseSettings | None = None,
) -> SiteContents:
    parse_settings = parse_settings or ParseSettings()

    skip_ids = parse_settings.skip_ids
    skip_ids = {str(x) for x in skip_ids}
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    nsmap = {k: v for k, v in root.nsmap.items() if k is not None}
    logger.debug(f"Namespace map: {nsmap}")

    posts = []
    media = []
    for item in root.findall(".//channel/item"):
        if (id_ := item.findtext("wp:post_id", namespaces=nsmap)) in skip_ids:
            logger.debug(f"Skipping post with ID {id_}")
            continue

        post_type = item.findtext("wp:post_type", namespaces=nsmap)
        if post_type in ("post", "page"):
            p = parse_post(
                item,
                nsmap,
                author_overrides=parse_settings.author_overrides,
            )
            posts.append(p)
        elif post_type == "attachment":
            media.append(parse_media_object(item, nsmap))

    logger.info(f"parsed {len(posts):,} posts/pages and {len(media):,} media files")
    return SiteContents(posts=posts, media=media, parse_settings=parse_settings)


def parse_post(
    item: etree._Element,
    nsmap: dict[str, str],
    author_overrides: dict[str, str] | None = None,
) -> Post:
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

    author = _parse_authors(item, nsmap, overrides=author_overrides)
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
        raw_content=content,
        date=date,
        categories=categories,
        tags=tags,
        _raw_excerpt=excerpt,
        footnotes_json=footnotes_json,
    )


def parse_media_object(item: etree._Element, nsmap: dict[str, str]) -> MediaObject:
    id_ = item.findtext("wp:post_id", namespaces=nsmap)
    url = item.findtext("wp:attachment_url", namespaces=nsmap)
    file_path = item.findtext(
        "wp:postmeta[wp:meta_key='_wp_attached_file']/wp:meta_value",
        namespaces=nsmap,
    )
    return MediaObject(id_=id_, url=url, file_path=file_path)


def _parse_authors(
    item: etree._Element, nsmap: dict[str, str], overrides: dict[str, str] | None = None
) -> str | list[str]:
    """Parse the author(s) from a WordPress XML item."""
    overrides = overrides or {}
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
