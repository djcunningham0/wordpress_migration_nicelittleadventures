from pathlib import Path

import pytest
from lxml import etree

from src.parsing.settings import ParseSettings
from src.parsing.wordpress_parser import Post, SiteContents, parse_wordpress_xml

DATA_DIR = Path(__file__).parent / "sample_data"
SAMPLE_XML = DATA_DIR / "sample_wxr_export.xml"

TEST_PARSE_SETTINGS = ParseSettings(
    skip_ids=set(),
    author_overrides={},
    keep_class_map={
        "div": {
            "fixture-author-1": "fixture-author-1",
            "fixture-author-2": "fixture-author-2",
            "wp-block-columns": "img-row",
        },
    },
    posts_subdir="posts",
    pages_subdir="",
)


@pytest.fixture(scope="session")
def xml_path() -> Path:
    return SAMPLE_XML


@pytest.fixture(scope="session")
def tree() -> etree._ElementTree:
    return etree.parse(str(SAMPLE_XML))


@pytest.fixture(scope="session")
def nsmap(tree) -> dict[str, str]:
    return {k: v for k, v in tree.getroot().nsmap.items() if k is not None}


@pytest.fixture(scope="session")
def items(tree) -> dict[str, etree._Element]:
    ns = {k: v for k, v in tree.getroot().nsmap.items() if k is not None}
    return {
        item.findtext("wp:post_id", namespaces=ns): item
        for item in tree.getroot().findall(".//channel/item")
    }


@pytest.fixture(scope="session")
def site_contents(xml_path) -> SiteContents:
    return parse_wordpress_xml(xml_path, parse_settings=TEST_PARSE_SETTINGS)


@pytest.fixture(scope="session")
def posts(site_contents) -> list[Post]:
    return site_contents.posts


@pytest.fixture(scope="session")
def posts_by_id(posts) -> dict[str, Post]:
    return {p.id_: p for p in posts}
