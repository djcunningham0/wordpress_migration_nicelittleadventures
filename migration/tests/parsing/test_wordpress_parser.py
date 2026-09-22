"""Structural tests: what comes out of the XML, not how HTML becomes markdown.

These run against the whole fixture document, because namespace resolution,
post_type filtering and postmeta lookups only mean anything in context.
"""

import pytest

from src.parsing.settings import ParseSettings
from src.parsing.wordpress_parser import parse_wordpress_xml

# --------------------------------------------------------------------------
# document-level
# --------------------------------------------------------------------------


class TestDocumentLevel:
    def test_parses_only_posts_and_pages(self, posts):
        """Attachments must not become Posts."""
        expected = {"101", "102", "103", "104", "105", "106", "5", "999"}
        assert {p.id_ for p in posts} == expected

    def test_post_types(self, posts_by_id):
        assert posts_by_id["101"].post_type == "post"
        assert posts_by_id["5"].post_type == "page"

    def test_skip_ids_excludes_posts(self, xml_path):
        settings = ParseSettings(skip_ids={"101", "5"})
        posts = parse_wordpress_xml(xml_path, parse_settings=settings).posts
        assert {p.id_ for p in posts} == {"102", "103", "104", "105", "106", "999"}

    def test_skip_ids_default_is_not_shared_between_calls(self, xml_path):
        """Guards against a mutable-default regression if `skip_ids=[]` ever creeps in."""
        first = parse_wordpress_xml(xml_path).posts
        second = parse_wordpress_xml(xml_path).posts
        assert {p.id_ for p in first} == {p.id_ for p in second}

    def test_draft_post_gets_slug_from_title(self, posts_by_id):
        """Draft posts don't have real slugs on Wordpress (empty `wp:post_name`), so we
        have to use the post title to generate a slug. This test makes sure we are doing
        that and not leaving the slug blank.
        """
        assert posts_by_id["103"].slug == "untitled-draft"

    def test_duplicate_slugs_are_made_unique(self, posts_by_id):
        # these two draft posts have the same title
        assert posts_by_id["103"].slug == "untitled-draft"
        assert posts_by_id["999"].slug == "untitled-draft-2"


# --------------------------------------------------------------------------
# scalar fields
# --------------------------------------------------------------------------


class TestBasicFields:
    def test_basic_fields(self, posts_by_id):
        post = posts_by_id["101"]
        assert post.title == "Sawtooth Traverse Part 1: Hiking the Sawtooth High Route"
        assert post.slug == "sawtooth-traverse-part-1"
        assert post.date == "2023-08-14 15:30:00"
        assert post.status == "publish"

    @pytest.mark.parametrize(
        "post_id,expected",
        [("101", False), ("102", False), ("103", True), ("104", True), ("5", False)],
    )
    def test_is_draft(self, posts_by_id, post_id, expected):
        assert posts_by_id[post_id].is_draft is expected


# --------------------------------------------------------------------------
# taxonomies
# --------------------------------------------------------------------------


class TestTaxonomies:
    def test_categories_and_tags_are_separated(self, posts_by_id):
        post = posts_by_id["101"]
        assert post.categories == ["Hiking", "Trip Reports"]
        assert post.tags == ["Idaho", "Sawtooths"]

    def test_author_categories_do_not_leak_into_categories(self, posts_by_id):
        """`category[@domain='author']` must not be picked up by the category selector."""
        post = posts_by_id["101"]
        assert "Danny" not in post.categories
        assert "Siyang" not in post.categories

    def test_missing_taxonomies_yield_empty_lists(self, posts_by_id):
        post = posts_by_id["103"]
        assert post.categories == []
        assert post.tags == []


# --------------------------------------------------------------------------
# authors
# --------------------------------------------------------------------------


class TestAuthors:
    def test_single_author_returns_string(self, posts_by_id):
        assert posts_by_id["102"].author == "Danny"

    def test_multiple_authors_returns_list_in_document_order(self, posts_by_id):
        assert posts_by_id["101"].author == ["Danny", "Siyang"]

    def test_author_falls_back_to_dc_creator(self, posts_by_id):
        """103 has no author category, so we fall back — and get the *login*, lowercase."""
        assert posts_by_id["103"].author == "danny"

    def test_author_overrides_applied(self, xml_path):
        overrides = {"Danny": "Danny C", "danny": "Danny C"}
        settings = ParseSettings(author_overrides=overrides)
        posts = parse_wordpress_xml(xml_path, parse_settings=settings).posts_by_id
        assert posts["102"].author == "Danny C"
        assert posts["101"].author == ["Danny C", "Siyang"]
        assert posts["103"].author == "Danny C"  # override also normalizes the fallback

    def test_author_override_of_unknown_name_is_noop(self, xml_path):
        settings = ParseSettings(author_overrides={"Nobody": "Someone"})
        posts = parse_wordpress_xml(xml_path, parse_settings=settings).posts_by_id
        assert posts["102"].author == "Danny"


# --------------------------------------------------------------------------
# footnotes postmeta
# --------------------------------------------------------------------------


class TestFootnotes:
    def test_footnotes_postmeta_is_parsed_as_json(self, posts_by_id):
        footnotes = posts_by_id["105"].footnotes_json
        assert [fn["id"] for fn in footnotes] == ["deadbeef", "c0ffee01"]
        assert footnotes == [
            {"content": "Footnote two.", "id": "deadbeef"},
            {
                "content": 'Footnote one. With <a href="https://example.com/history">a link</a>.',
                "id": "c0ffee01",
            },
        ]

    def test_footnotes_absent_yields_empty_list(self, posts_by_id):
        assert posts_by_id["103"].footnotes_json == []

    def test_thumbnail_postmeta_does_not_confuse_footnote_lookup(self, posts_by_id):
        """104 has _thumbnail_id but no footnotes; the XPath must not match the wrong meta."""
        assert posts_by_id["104"].footnotes_json == []


# --------------------------------------------------------------------------
# Images and videos
# --------------------------------------------------------------------------


class TestImages:
    def test_parses_images_to_set(self, posts_by_id):
        p = posts_by_id["101"]
        images = p.images
        expected = {
            "2023/08/sawtooth-ridge.jpg",
            "2023/08/alpine-lake.jpg",
        }
        assert images == expected

    def test_images_linked_to_file(self, posts_by_id):
        p = posts_by_id["101"]
        markdown = p.markdown
        print(markdown)
        assert '<img src="sawtooth-ridge.jpg">' in markdown
        assert '<img src="sawtooth-ridge.jpg" alt="Ridgeline at dawn">' in markdown
        assert '<img src="alpine-lake.jpg" alt="Alpine lake">' in markdown

    def test_parses_videos_to_set(self, posts_by_id):
        videos = posts_by_id["102"].videos
        assert videos == {"2023/09/ridge-flyover.mp4"}

    def test_videos_linked_to_file(self, posts_by_id):
        markdown = posts_by_id["102"].markdown
        print(markdown)
        assert '<video controls src="ridge-flyover.mp4"></video>' in markdown

    def test_parses_images_and_videos(self, posts_by_id):
        out = posts_by_id["102"]
        assert out.images == {
            "2023/09/pack-layout.jpg",
            "2023/08/sawtooth-ridge.jpg",
            "2023/08/alpine-lake.jpg",
        }
        assert out.videos == {"2023/09/ridge-flyover.mp4"}


# --------------------------------------------------------------------------
# embeds
# --------------------------------------------------------------------------


class TestEmbeds:
    def test_iframe_persists(self, posts_by_id):
        markdown = posts_by_id["102"].markdown
        # conversion doesn't maintain exact order of attributes, so just going to do
        # some basic checks
        assert "<iframe " in markdown
        assert "</iframe>" in markdown
        assert 'src="https://caltopo.com/m/ABC123"' in markdown

    def test_youtube_embed_is_converted_to_shortcode(self, posts_by_id):
        markdown = posts_by_id["102"].markdown
        assert "{{< youtube aqz-KE-bpKQ >}}" in markdown


# --------------------------------------------------------------------------
# custom div classes
# --------------------------------------------------------------------------


class TestCustomDivs:
    def test_custom_divs_are_kept(self, posts_by_id):
        markdown = posts_by_id["101"].markdown
        assert '<div class="fixture-author-1"' in markdown
        assert '<div class="fixture-author-2"' in markdown


# --------------------------------------------------------------------------
# internal links
# --------------------------------------------------------------------------


class TestLinks:
    def test_post_to_post_internal_link(self, posts_by_id):
        markdown = posts_by_id["101"].markdown
        assert (
            'For gear details, see [our gear notes post]({{< ref "posts/gear-notes-route-flyover" >}}).'
            in markdown
        )

    def test_post_to_page_internal_link(self, posts_by_id):
        markdown = posts_by_id["106"].markdown
        print(markdown)
        assert (
            'behind this site, see [our About page]({{< ref "about" >}}).' in markdown
        )

    def test_missing_post_id_falls_back_to_source_slug(self, posts_by_id):
        markdown = posts_by_id["102"].markdown
        assert (
            'wrote up [an older gear post]({{< ref "posts/nonexistent-post" >}}) that'
            in markdown
        )
