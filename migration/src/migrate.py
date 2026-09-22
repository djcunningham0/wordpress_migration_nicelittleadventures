"""
From the `migration/` directory:

    uv run python -m src.migrate [--arg1 val --arg2 val]
"""

import argparse
import logging
import os
import shutil
from pathlib import Path

from lxml import etree

from src import config
from src.parsing.settings import ParseSettings
from src.parsing.wordpress_parser import Post, parse_wordpress_xml

logger = logging.getLogger(__name__)


def migrate(
    xml_name: str | None = None,
    target_dir_name: str | None = None,
    overwrite_individual: bool = True,
    full_rebuild: bool = False,
):
    xml_path, target_dir = parse_paths(xml_name, target_dir_name)
    settings = ParseSettings()
    site_contents = parse_wordpress_xml(xml_path, parse_settings=settings)
    posts = site_contents.posts
    logger.info(f"Parsed {len(posts):,} posts from {xml_path}")

    content_path = target_dir / "content"
    logger.info(f"Writing posts to {content_path}")
    if full_rebuild and content_path.exists():
        logger.info(
            f"Full rebuild requested; deleting existing content directory {content_path}"
        )
        shutil.rmtree(content_path)

    for post in posts:
        if post.post_type == "post":
            post_dir = content_path / "posts" / post.slug
        elif post.post_type == "page":
            post_dir = content_path / post.slug
        else:
            raise ValueError(f"Unknown post type: {post.post_type}")

        os.makedirs(post_dir, exist_ok=True)
        post_file_path = post_dir / "index.md"
        if post_file_path.exists() and not overwrite_individual:
            logger.info(f"Skipping existing file: {post_file_path}")
            continue

        with open(post_file_path, "w", encoding="utf-8") as f:
            f.write(post.markdown)
        logger.info(f"Wrote {post_file_path}")

        copy_images_for_post(post, post_dir)


def copy_images_for_post(post: Post, post_dir: Path):
    images_and_videos = post.images.union(post.videos)

    for file in images_and_videos:
        local_path = Path(file.replace(config.WP_MEDIA_DIR, config.MEDIA_DIR))
        if not local_path.exists():
            logger.warning(f"missing media file: {file}; post: {post.title}")
            continue

        shutil.copy(local_path, post_dir)


def parse_paths(
    xml_name: str | None = None,
    target_dir_name: str | None = None,
) -> tuple[Path, Path]:
    if xml_name is None:
        xml_name = config.XML_PATH
    if target_dir_name is None:
        target_dir_name = config.HUGO_TARGET_DIR

    if not xml_name or not target_dir_name:
        raise ValueError(
            f"`xml_name` and `target_dir_name` must be provided or set in `.env`. "
            f"Found {xml_name=} and {target_dir_name=}"
        )

    xml_path = Path(xml_name)
    target_dir = Path(target_dir_name)

    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found at {xml_path}")
    if not target_dir.exists():
        raise FileNotFoundError(f"Target directory not found at {target_dir}")

    return xml_path, target_dir


def parse_xml_file(xml_path: Path) -> etree._ElementTree:
    try:
        tree = etree.parse(str(xml_path))
        return tree
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Failed to parse XML file at {xml_path}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate WordPress XML to static site")
    parser.add_argument("--xml", help="Path to WordPress XML file")
    parser.add_argument("--target", help="Target directory for migrated content")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=True,
        help="Overwrite existing files",
    )
    parser.add_argument(
        "--full-rebuild",
        action="store_true",
        default=False,
        help="Perform full rebuild",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=log_level)

    migrate(
        xml_name=args.xml,
        target_dir_name=args.target,
        overwrite_individual=args.overwrite,
        full_rebuild=args.full_rebuild,
    )
