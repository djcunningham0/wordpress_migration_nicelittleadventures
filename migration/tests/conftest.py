from pathlib import Path

import pytest
from _pytest.monkeypatch import MonkeyPatch
from lxml import etree

from src.parsing.wordpress_parser import Post, SiteContents, parse_wordpress_xml

DATA_DIR = Path(__file__).parent / "sample_data"
SAMPLE_XML = DATA_DIR / "sample_wxr_export.xml"


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped equivalent of `monkeypatch`, since the built-in
    fixture is function-scoped only."""
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(scope="session", autouse=True)
def no_author_overrides(monkeypatch_session):
    monkeypatch_session.setattr("src.config.AUTHOR_OVERRIDES", {})
    monkeypatch_session.setattr("src.parsing.wordpress_parser.AUTHOR_OVERRIDES", {})


@pytest.fixture(scope="session", autouse=True)
def custom_div_classes(monkeypatch_session):
    classes = [
        "fixture-author-1",
        "fixture-author-2",
    ]
    monkeypatch_session.setattr("src.config.KEEP_CUSTOM_DIV_CLASSES", classes)
    monkeypatch_session.setattr("src.parsing.markdown.KEEP_CUSTOM_DIV_CLASSES", classes)


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
    return parse_wordpress_xml(xml_path)


@pytest.fixture(scope="session")
def posts(site_contents) -> list[Post]:
    return site_contents.posts


@pytest.fixture(scope="session")
def posts_by_id(posts) -> dict[str, Post]:
    return {p.id_: p for p in posts}
