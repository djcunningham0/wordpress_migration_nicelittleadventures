from src.parsing.wordpress_parser import normalize, parse_custom_excerpt


class TestParseCustomExcerpt:
    def test_parse_custom_excerpt(self):
        excerpt_html = """
            <hr>
            <h5 class="page-description"><i>
            This is the subtitle
            </i></h5>
            <p>
            And this is the excerpt text.
            </p>
        """
        subtitle, excerpt = parse_custom_excerpt(excerpt_html)
        assert subtitle == "This is the subtitle"
        assert excerpt == "And this is the excerpt text."

    def test_parse_custom_excerpt_with_multiline_excerpt(self):
        excerpt_html = """
            <hr>
            <h5 class="page-description"><i>
            This is the subtitle
            </i></h5>
            <p>
            And this is the excerpt text.
            It has two lines.
            </p>
        """
        subtitle, excerpt = parse_custom_excerpt(excerpt_html)
        assert subtitle == "This is the subtitle"
        assert excerpt == "And this is the excerpt text. It has two lines."

    def test_paragraph_only_excerpt_has_empty_subtitle(self):
        subtitle, excerpt = parse_custom_excerpt("<p>\nJust a plain excerpt.\n</p>")
        assert subtitle == ""
        assert excerpt == "Just a plain excerpt."

    def test_subtitle_without_paragraph(self):
        subtitle, excerpt = parse_custom_excerpt(
            '<h5 class="page-description"><i>Only a subtitle</i></h5>'
        )
        assert subtitle == "Only a subtitle"
        assert excerpt == ""

    def test_empty_excerpt_returns_two_empty_strings(self):
        assert parse_custom_excerpt("") == ("", "")

    def test_none_excerpt_does_not_crash(self):
        assert parse_custom_excerpt(None) == ("", "")

    # --------------------------------------------------------------------------
    # from the fixture
    # --------------------------------------------------------------------------

    def test_fixture_excerpts(self, posts_by_id):
        post = posts_by_id["101"]
        assert post.subtitle == "Nine hours of talus, one very good alpine lake"
        assert post.excerpt.startswith("A three-day traverse")

    def test_fixture_excerpt_without_subtitle(self, posts_by_id):
        post = posts_by_id["106"]
        assert post.subtitle == ""
        assert post.excerpt == "Four ingredients, about eleven cents a liter."

    def test_fixture_empty_excerpt(self, posts_by_id):
        post = posts_by_id["103"]
        assert post.subtitle == ""
        assert post.excerpt == ""

    # --------------------------------------------------------------------------
    # normalize()
    # --------------------------------------------------------------------------

    def test_normalize_collapses_all_whitespace(self):
        from bs4 import BeautifulSoup

        el = BeautifulSoup("<p>  a\n\n  b\tc  </p>", "html.parser").find("p")
        assert normalize(el) == "a b c"
