from pathlib import Path

import pytest
from lxml import etree

import src.parsing.wordpress_parser as wp

DATA_DIR = Path(__file__).parent / "sample_data"
SAMPLE_XML = DATA_DIR / "sample_wxr_export.xml"


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
    """Every <item> in the channel, keyed by wp:post_id (attachments included)."""
    ns = {k: v for k, v in tree.getroot().nsmap.items() if k is not None}
    return {
        item.findtext("wp:post_id", namespaces=ns): item
        for item in tree.getroot().findall(".//channel/item")
    }


@pytest.fixture(scope="session")
def posts(xml_path) -> list[wp.Post]:
    return wp.parse_wordpress_xml(xml_path)


@pytest.fixture(scope="session")
def posts_by_id(posts) -> dict[str, wp.Post]:
    return {p.id_: p for p in posts}


@pytest.fixture
def no_author_overrides(monkeypatch):
    """Disable author overrides for tests; otherwise we may get unexpected failures if
    overrides happen to appear in test data.
    """
    monkeypatch.setattr("src.config.XML_PATH", {})
