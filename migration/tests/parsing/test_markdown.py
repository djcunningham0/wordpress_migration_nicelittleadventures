import pytest
from bs4 import BeautifulSoup

from src.parsing.markdown import (
    MarkdownOutput,
    content_to_markdown,
    prettify_markdown,
    replace_footnote_markers_with_placeholders,
    resolve_footnotes,
)
from src.parsing.settings import ParseSettings
from src.parsing.wordpress_parser import MediaObject


def get_empty_settings() -> ParseSettings:
    return ParseSettings(
        skip_ids=set(),
        author_overrides={},
        keep_class_map={},
        posts_subdir="",
        pages_subdir="",
    )


def convert(
    html: str,
    parse_settings: ParseSettings | None = None,
    **kwargs,
) -> MarkdownOutput:
    parse_settings = parse_settings or get_empty_settings()
    return content_to_markdown(
        html_content=html,
        footnotes_json=kwargs.get("footnotes_json", []),
        post_id_to_slug=kwargs.get("post_id_to_slug", {}),
        media_by_id=kwargs.get("media_by_id", {}),
        parse_settings=parse_settings,
    )


# --------------------------------------------------------------------------
# basics
# --------------------------------------------------------------------------


class TestBasics:
    @pytest.mark.parametrize(
        "html,expected",
        [
            ("<p>Hello world.</p>", "Hello world."),
            ("<h2>A heading</h2>", "## A heading"),
            ("<p>Some <strong>bold</strong> text.</p>", "Some **bold** text."),
            ("<p>Some <em>italic</em> text.</p>", "Some *italic* text."),
            ("<ul><li>One</li><li>Two</li></ul>", "- One\n- Two"),
            (
                '<p><a href="https://example.com">a link</a></p>',
                "[a link](https://example.com)",
            ),
            ("<p><s>Strikethrough</s></p>", "~~Strikethrough~~"),
            ("<blockquote><p>A quote.</p></blockquote>", "> A quote."),
            ("<code>Inline code</code>", "`Inline code`"),
            ("<pre><code>Code block</code></pre>", "```\nCode block\n```"),
            ("<hr>", "---"),
        ],
    )
    def test_basic_blocks(self, html, expected):
        result = convert(html)
        assert expected in result.markdown

    def test_gutenberg_comments_are_stripped(self):
        html = "<!-- wp:paragraph -->\n<p>Body text.</p>\n<!-- /wp:paragraph -->"
        result = convert(html)
        assert "wp:paragraph" not in result.markdown
        assert "Body text." in result.markdown

    def test_heading_style_is_atx(self):
        result = convert("<h1>Title</h1>")
        assert result.markdown.startswith("# Title")
        assert "===" not in result.markdown


# --------------------------------------------------------------------------
# links
# --------------------------------------------------------------------------


class TestLinks:
    def test_external_links_get_markdown_link(self):
        html = '<a href="https://example.org">a link</a>'
        assert convert(html).markdown == "[a link](https://example.org)"

    def test_internal_links_get_ref_links(self):
        post_id_to_slug = {"123": "actual-slug"}
        html = '<a href="https://mysite.com/some-slug" data-type="post" data-id="123">a link</a>'
        expected = '[a link]({{< ref "actual-slug" >}})'
        out = convert(html, post_id_to_slug=post_id_to_slug)
        out = out.markdown
        assert out == expected

    def test_internal_links_falls_back_to_original_slug(self):
        post_id_to_slug = {}  # "123" is not listed
        html = '<a href="https://mysite.com/some-slug" data-type="post" data-id="123">a link</a>'
        expected = '[a link]({{< ref "some-slug" >}})'
        out = convert(html, post_id_to_slug=post_id_to_slug)
        out = out.markdown
        assert out == expected

    def test_internal_links_respects_posts_subdir(self):
        settings = get_empty_settings()
        settings.posts_subdir = "posts"
        post_id_to_slug = {"123": "actual-slug"}
        html = '<a href="https://mysite.com/some-slug" data-type="post" data-id="123">a link</a>'
        expected = '[a link]({{< ref "posts/actual-slug" >}})'
        out = convert(html, parse_settings=settings, post_id_to_slug=post_id_to_slug)
        out = out.markdown
        assert out == expected

    def test_internal_links_respects_pages_subdir(self):
        settings = get_empty_settings()
        settings.pages_subdir = "pages"
        post_id_to_slug = {"5": "some-page"}
        html = '<a href="https://mysite.com/some-slug" data-type="page" data-id="5">a link</a>'
        expected = '[a link]({{< ref "pages/some-page" >}})'
        out = convert(html, parse_settings=settings, post_id_to_slug=post_id_to_slug)
        out = out.markdown
        assert out == expected

    def test_external_link_keeps_fragment(self):
        html = '<a href="https://example.org/page#fragment">a link</a>'
        assert convert(html).markdown == "[a link](https://example.org/page#fragment)"

    def test_internal_link_keeps_fragment(self):
        post_id_to_slug = {"123": "actual-slug"}
        html = '<a href="https://mysite.com/some-slug#fragment" data-type="post" data-id="123">a link</a>'
        expected = '[a link]({{< ref "actual-slug#fragment" >}})'
        out = convert(html, post_id_to_slug=post_id_to_slug)
        out = out.markdown
        assert out == expected


# --------------------------------------------------------------------------
# figures
# --------------------------------------------------------------------------


class TestFigures:
    def test_keep_figure_with_two_newlines_around_img(self):
        html = '<figure><img src="https://example.com/a.jpg"></figure>'
        out = convert(html).markdown
        expected = '<figure>\n\n<img src="https://example.com/a.jpg">\n\n</figure>'
        assert out == expected

    def test_keep_figure_with_two_newlines_around_video(self):
        html = (
            '<figure><video controls src="https://example.com/a.mov"></video></figure>'
        )
        out = convert(html).markdown
        expected = '<figure>\n\n<video controls src="https://example.com/a.mov"></video>\n\n</figure>'
        assert out == expected

    def test_strip_figure_with_no_relevant_tags(self):
        html = "<figure><p>just some text</p></figure>"
        assert convert(html).markdown == "just some text"

    def test_keep_figure_with_figcaption(self):
        html = "<figure><p>some text</p><figcaption>and a caption</figcaption></figure>"
        out = convert(html).markdown
        expected = (
            "<figure>\n\n"
            "some text\n\n"
            "<figcaption>\n\nand a caption\n\n</figcaption>\n\n"
            "</figure>"
        )
        assert out == expected

    def test_keep_figure_with_specified_class(self):
        class_map = {"figure": {"some-class": "renamed-class"}}
        settings = get_empty_settings()
        settings.keep_class_map = class_map
        html = '<figure class="some-class"><img src="image.jpg"></figure>'
        out = convert(html, parse_settings=settings).markdown
        expected = (
            '<figure class="renamed-class">\n\n<img src="image.jpg">\n\n</figure>'
        )
        assert out == expected

    def test_keep_figure_with_specified_class_without_image(self):
        class_map = {"figure": {"some-class": "renamed-class"}}
        settings = get_empty_settings()
        settings.keep_class_map = class_map
        html = '<figure class="some-class"><p>some text</p></figure>'
        out = convert(html, parse_settings=settings).markdown
        expected = '<figure class="renamed-class">\n\nsome text\n\n</figure>'
        assert out == expected


class TestFigcaption:
    def test_two_newlines_around_figcaption(self):
        html = "<figcaption>some text</figcaption>"
        assert convert(html).markdown == "<figcaption>\n\nsome text\n\n</figcaption>"

    def test_figcaption_text_is_converted_to_markdown(self):
        html = (
            "<figcaption>"
            'some <strong>bold</strong> and <em>italic</em> text with a <a href="https://example.com">link</a>'
            "</figcaption>"
        )
        out = convert(html).markdown
        expected = (
            "<figcaption>\n\n"
            "some **bold** and *italic* text with a [link](https://example.com)\n\n"
            "</figcaption>"
        )
        assert out == expected


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------


class TestImages:
    def test_image_converts_to_html_and_strips_class(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" class="wp-image-202"/>'
            "</figure>"
        )
        out = convert(html)
        expected = '<figure>\n\n<img src="https://example.com/a.jpg">\n\n</figure>'
        assert out.markdown == expected

    def test_alt_text_is_preserved(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" alt="Alt text" class="wp-image-202">'
            "</figure>"
        )
        out = convert(html)
        expected = '<figure>\n\n<img src="https://example.com/a.jpg" alt="Alt text">\n\n</figure>'
        assert out.markdown == expected

    def test_image_keeps_caption(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" class="wp-image-202">'
            '<figcaption class="wp-element-caption">A caption.</figcaption>'
            "</figure>\n"
        )
        out = convert(html)
        assert out.markdown == (
            "<figure>\n\n"
            '<img src="https://example.com/a.jpg">\n'
            "<figcaption>\n\nA caption.\n\n</figcaption>\n\n"
            "</figure>"
        )

    def test_self_linking_image_removes_link(self):
        """Pull the href image only."""
        self_linking_image = (
            '<figure class="wp-block-image size-large">'
            '<a href="https://example.com/wp-content/uploads/2023/08/ridge.jpg">'
            '<img src="https://example.com/wp-content/uploads/2023/08/ridge.jpg" '
            "</figure>"
        )
        out = convert(self_linking_image).markdown
        expected = (
            "<figure>\n\n"
            '<img src="https://example.com/wp-content/uploads/2023/08/ridge.jpg">\n\n'
            "</figure>"
        )
        assert out == expected

    def test_image_with_escaped_characters_in_alt_text(self):
        html = '<img src="https://example.com/a.jpg" alt="a quote &quot;Overlook&quot; and ampersand &amp;">'
        assert convert(html).markdown.strip() == html.strip()

    def test_uploaded_image_links_to_file_name(self):
        image = MediaObject(
            id_="123",
            url="https://example.com/wp-content/uploads/2023/08/ridge.jpg",
            file_path="2023/08/ridge.jpg",
        )
        media_by_id = {"123": image}
        html = '<img src="https://example.com/wp-content/uploads/2023/08/ridge.jpg" class="wp-image-123">'
        out = convert(html, media_by_id=media_by_id)
        expected = '<img src="ridge.jpg">'
        assert out.markdown == expected
        assert out.media_paths == {"2023/08/ridge.jpg"}


# --------------------------------------------------------------------------
# embeds: iframes and video
# --------------------------------------------------------------------------


class TestEmbeds:
    def test_iframe_survives_conversion(self):
        iframe_block = (
            '<iframe src="https://caltopo.com/m/ABC123" width="100%" height="500" '
            'frameborder="0" allowfullscreen></iframe>'
        )
        out = convert(iframe_block).markdown
        assert out.startswith("<iframe ")
        assert out.endswith("</iframe>")

        # `convert_iframe` won't preserve attribute order, so that each element is
        # preserved rather than checking an exact string
        soup = BeautifulSoup(out, "html.parser")
        out_iframe = soup.find("iframe")
        assert out_iframe is not None
        assert out_iframe.get("src") == "https://caltopo.com/m/ABC123"
        assert out_iframe.get("width") == "100%"
        assert out_iframe.get("height") == "500"
        assert out_iframe.get("frameborder") == "0"
        assert out_iframe.get("allowfullscreen") == ""

    def test_iframe_inside_figure_with_caption(self):
        html = (
            "<figure>\n"
            '<iframe src="https://caltopo.com/m/ABC123"></iframe>\n'
            "<figcaption>a caption</figcaption>\n"
            "</figure>"
        )
        out = convert(html).markdown
        expected = (
            "<figure>\n\n"
            '<iframe src="https://caltopo.com/m/ABC123"></iframe>\n'
            "<figcaption>\n\na caption\n\n</figcaption>\n\n"
            "</figure>"
        )
        assert out == expected

    def test_self_hosted_video_is_preserved(self):
        html = (
            '<figure class="wp-block-video">'
            '<video controls src="https://example.com/flyover.mp4"></video>'
            "</figure>"
        )
        out = convert(html)
        assert out.markdown == (
            "<figure>\n\n"
            '<video controls src="https://example.com/flyover.mp4"></video>\n\n'
            "</figure>"
        )

    def test_youtube_embed_is_converted_to_hugo_shortcode(self):
        html = (
            '<figure class="wp-block-embed is-provider-youtube">'
            '<div class="wp-block-embed__wrapper">\n'
            "https://www.youtube.com/watch?v=aqz-KE-bpKQ\n"
            "</div></figure>"
        )
        out = convert(html).markdown
        expected = "{{< youtube aqz-KE-bpKQ >}}"
        assert out == expected

    def test_youtube_embed_with_caption(self):
        html = (
            '<div class="wp-block-column" style="flex-basis:27.27%">'
            '<!-- wp:embed {"url":"https://youtu.be/PoIngwoBW-Q","type":"video","providerNameSlug":"youtube","responsive":true,"className":"wp-embed-aspect-4-3 wp-has-aspect-ratio"} -->'
            '<figure class="wp-block-embed is-type-video is-provider-youtube wp-block-embed-youtube wp-embed-aspect-4-3 wp-has-aspect-ratio">'
            '<div class="wp-block-embed__wrapper">'
            "https://youtu.be/PoIngwoBW-Q"
            "</div>"
            '<figcaption class="wp-element-caption">View from afar of their line... they got stuck a few times</figcaption>'
            "</figure>"
            "<!-- /wp:embed --></div>"
        )
        out = convert(html).markdown
        expected = (
            "<figure>\n\n"
            "{{< youtube PoIngwoBW-Q >}}\n"
            "<figcaption>\n\nView from afar of their line... they got stuck a few times\n\n</figcaption>\n\n"
            "</figure>"
        )
        assert out == expected

    def test_other_embeds_are_converted_to_hyperlinks(self):
        html = (
            '<figure class="wp-block-embed is-provider-unsupported-website">'
            '<div class="wp-block-embed__wrapper">\n'
            "https://unsupported_website.com\n"
            "</div></figure>"
        )
        out = convert(html).markdown
        expected = "[https://unsupported_website.com](https://unsupported_website.com)"
        assert out == expected


# --------------------------------------------------------------------------
# tables
# --------------------------------------------------------------------------


class TestTables:
    def test_table_becomes_gfm_pipe_table(self):
        table_with_header = (
            '<figure class="wp-block-table"><table>'
            "<thead><tr><th>Ingredient</th><th>Amount</th></tr></thead>"
            "<tbody><tr><td>Table salt</td><td>1/4 tsp</td></tr>"
            "<tr><td>Sugar</td><td>2 tbsp</td></tr></tbody>"
            '</table><figcaption class="wp-element-caption">Per 1 liter of water.</figcaption></figure>'
        )
        out = convert(table_with_header).markdown
        assert "| Ingredient" in out
        assert "| Table salt" in out
        assert "1/4 tsp" in out
        # separator row
        assert any(set(line) <= set("| -") and "-" in line for line in out.splitlines())

    def test_table_without_thead_still_renders_all_cells(self):
        html = (
            '<figure class="wp-block-table"><table><tbody>'
            "<tr><td>No header row</td><td>on this one</td></tr>"
            "<tr><td>Just</td><td>body cells</td></tr>"
            "</tbody></table></figure>"
        )
        out = convert(html).markdown
        assert "No header row" in out
        assert "on this one" in out
        assert "body cells" in out

    def test_table_pipes_are_aligned(self):
        html = (
            "<figure>"
            "<table>"
            "<thead><tr><th>col 1</th><th>col 2</th></tr></thead>"
            "<tbody><tr><td>x</td><td>y</td></tr>"
            "<tr><td>z</td><td>longer value</td></tr></tbody>"
            "</table>"
            "</figure>"
        )
        expected = (
            "| col 1 | col 2        |\n"
            "| ----- | ------------ |\n"
            "| x     | y            |\n"
            "| z     | longer value |"
        )
        out = convert(html).markdown
        assert out == expected

    def test_table_pipes_are_aligned_and_keeps_caption(self):
        html = (
            "<figure>"
            "<table>"
            "<thead><tr><th>col 1</th><th>col 2</th></tr></thead>"
            "<tbody><tr><td>x</td><td>y</td></tr>"
            "<tr><td>z</td><td>longer value</td></tr></tbody>"
            "</table>"
            "<figcaption>a caption</figcaption>"
            "</figure>"
        )
        expected = (
            "<figure>\n\n"
            "| col 1 | col 2        |\n"
            "| ----- | ------------ |\n"
            "| x     | y            |\n"
            "| z     | longer value |\n"
            "<figcaption>\n\na caption\n\n</figcaption>\n\n"
            "</figure>"
        )
        out = convert(html).markdown
        assert out == expected


# --------------------------------------------------------------------------
# quotes
# --------------------------------------------------------------------------


class TestQuotes:
    PULLQUOTE = (
        '<figure class="wp-block-pullquote"><blockquote>'
        "<p>The mountains are calling and I must go.</p>"
        "<cite>John Muir</cite></blockquote></figure>"
    )

    BLOCKQUOTE = (
        '<blockquote class="wp-block-quote"><p>A regular block quote.</p></blockquote>'
    )

    def test_blockquote(self):
        out = convert(self.BLOCKQUOTE).markdown
        assert "> A regular block quote." in out

    def test_pullquote_becomes_blockquote(self):
        out = convert(self.PULLQUOTE).markdown
        assert "> The mountains are calling and I must go." in out


# --------------------------------------------------------------------------
# custom div handling
# --------------------------------------------------------------------------


class TestDivs:
    @property
    def parse_settings(self):
        keep_class_map = {
            "div": {
                "fixture-author-1": "fixture-author-1",
                "fixture-author-2": "fixture-author-2",
                "wp-block-columns": "img-row",
            }
        }
        settings = get_empty_settings()
        settings.keep_class_map = keep_class_map
        return settings

    def test_exact_author_div_output(self):
        html = (
            '<div class="fixture-author-1"><p>One of us says a thing.</p></div>'
            '<div class="fixture-author-2"><p>The other says another thing.</p></div>'
        )
        out = convert(html, parse_settings=self.parse_settings).markdown
        expected = (
            '<div class="fixture-author-1">\n\n'
            "One of us says a thing.\n\n"
            "</div>\n"
            '<div class="fixture-author-2">\n\n'
            "The other says another thing.\n\n"
            "</div>"
        )
        assert out == expected

    def test_other_divs_are_skipped(self):
        html = (
            '<div class="fixture-author-8"><p>One of us says a thing.</p></div>'
            '<div class="fixture-author-9"><p>The other says another thing.</p></div>'
        )
        out = convert(html, parse_settings=self.parse_settings).markdown
        expected = "One of us says a thing.\n\nThe other says another thing."
        assert out == expected

    def test_only_keeps_specified_div(self):
        html = (
            '<div class="fixture-author-1"><p>One of us says a thing.</p></div>'
            '<div class="fixture-author-9"><p>Another sentence.</p></div>'
        )
        out = convert(html, parse_settings=self.parse_settings).markdown
        expected = (
            '<div class="fixture-author-1">\n\n'
            "One of us says a thing.\n\n"
            "</div>\n\n"
            "Another sentence."
        )
        assert out == expected

    def test_specified_divs_are_renamed(self):
        html = (
            '<div class="wp-block-columns">'
            '<div class="wp-block-column">'
            "<p>some text</p>"
            "</div>"
            "</div>"
        )
        out = convert(html, parse_settings=self.parse_settings).markdown
        expected = '<div class="img-row">\n\nsome text\n\n</div>'
        assert out == expected


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------


class TestColumns:
    def test_columns(self):
        keep_class_map = {"div": {"wp-block-columns": "img-row"}}
        settings = get_empty_settings()
        settings.keep_class_map = keep_class_map
        html = (
            '<div class="wp-block-columns">'
            '<div class="wp-block-column" style="flex-basis:66.67%">'
            '<figure class="wp-block-image">'
            '<img src="image.jpg">'
            "<figcaption>a caption</figcaption>"
            "</figure>"
            "</div>"
            '<div class="wp-block-column" style="flex-basis:33.33%">'
            '<figure class="wp-block-image">'
            '<img src="image2.jpg">'
            "</figure>"
            "</div>"
            "</div>"
        )
        out = convert(html, parse_settings=settings).markdown
        expected = (
            '<div class="img-row">\n\n'
            "<figure>\n\n"
            '<img src="image.jpg">\n'
            "<figcaption>\n\na caption\n\n</figcaption>\n\n"
            "</figure>\n\n"
            "<figure>\n\n"
            '<img src="image2.jpg">\n\n'
            "</figure>\n\n"
            "</div>"
        )
        assert out == expected


# --------------------------------------------------------------------------
# footnotes
# --------------------------------------------------------------------------


def sup(fn_id: str, n: int = 1) -> str:
    """A footnote marker in the shape WordPress actually emits."""
    return (
        f'<sup data-fn="{fn_id}" class="fn">'
        f'<a href="#{fn_id}" id="{fn_id}-link">{n}</a></sup>'
    )


class TestFootnotes:
    ### marker -> placeholder

    def test_marker_becomes_placeholder(self):
        html = f"<p>Text.{sup('a1b2c3d4')}</p>"
        expected = "<p>Text.@@FOOTNOTE:a1b2c3d4@@</p>"
        assert replace_footnote_markers_with_placeholders(html) == expected

    def test_multiple_markers_all_replaced(self):
        html = f"<p>A{sup('aaaa1111')} and B{sup('bbbb2222', 2)}.</p>"
        out = replace_footnote_markers_with_placeholders(html)
        assert "@@FOOTNOTE:aaaa1111@@" in out
        assert "@@FOOTNOTE:bbbb2222@@" in out
        assert "<sup" not in out

    def test_marker_spanning_newlines_is_replaced(self):
        html = '<p>Text.<sup data-fn="a1b2c3d4" class="fn">\n<a href="#x">1</a>\n</sup></p>'
        out = replace_footnote_markers_with_placeholders(html)
        assert "@@FOOTNOTE:a1b2c3d4@@" in out

    def test_sup_without_data_fn_is_left_alone(self):
        html = "<p>10<sup>3</sup> feet</p>"
        assert replace_footnote_markers_with_placeholders(html) == html

    ### numbering

    def test_numbering_follows_appearance_order_not_json_order(self):
        markdown = "First@@FOOTNOTE:bbbb2222@@ then second@@FOOTNOTE:aaaa1111@@."
        footnotes = [
            {"id": "aaaa1111", "content": "Listed first in JSON."},
            {"id": "bbbb2222", "content": "Listed second in JSON."},
        ]
        out = resolve_footnotes(markdown, footnotes, {})
        assert "First[^1] then second[^2]." in out
        assert "[^1]: Listed second in JSON." in out
        assert "[^2]: Listed first in JSON." in out

    def test_repeated_id_reuses_the_same_number(self):
        markdown = (
            "A@@FOOTNOTE:aaaa1111@@ B@@FOOTNOTE:bbbb2222@@ C@@FOOTNOTE:aaaa1111@@"
        )
        footnotes = [
            {"id": "aaaa1111", "content": "One."},
            {"id": "bbbb2222", "content": "Two."},
        ]
        out = resolve_footnotes(markdown, footnotes, {})
        assert "A[^1] B[^2] C[^1]" in out
        assert out.count("[^1]: One.") == 1

    def test_unreferenced_footnote_is_not_emitted(self):
        """A definition with no marker in the body should be dropped, not orphaned."""
        markdown = "Only one marker@@FOOTNOTE:aaaa1111@@."
        footnotes = [
            {"id": "aaaa1111", "content": "Referenced."},
            {"id": "bbbb2222", "content": "Never referenced."},
        ]
        out = resolve_footnotes(markdown, footnotes, {})
        assert "Never referenced." not in out

    def test_no_footnotes_leaves_markdown_untouched(self):
        markdown = "Just some text."
        assert resolve_footnotes(markdown, [], {}) == markdown

    def test_markers_with_empty_footnote_list_still_numbered(self):
        """Markers present but JSON empty: body is renumbered, definitions are blank."""
        out = resolve_footnotes("Text@@FOOTNOTE:aaaa1111@@", [], {})
        assert "Text[^1]" in out

    ### rendering

    def test_footnote_content_html_is_converted_to_markdown(self):
        markdown = "Text@@FOOTNOTE:aaaa1111@@"
        footnotes = [
            {
                "id": "aaaa1111",
                "content": 'Roughly <em>76 miles</em>, see <a href="https://example.com/x">here</a>.',
            }
        ]
        out = resolve_footnotes(markdown, footnotes, {})
        assert "[^1]: Roughly *76 miles*, see [here](https://example.com/x)." in out

    ### end to end

    def test_end_to_end_footnote_conversion(self):
        html = f"<p>The high route begins above treeline.{sup('a1b2c3d4')}</p>"
        footnotes = [{"id": "a1b2c3d4", "content": "Unmaintained above 9,000 ft."}]
        out = content_to_markdown(html, footnotes, {}, {}).markdown
        assert "The high route begins above treeline.[^1]" in out
        assert "[^1]: Unmaintained above 9,000 ft." in out


# --------------------------------------------------------------------------
# degenerate input
# --------------------------------------------------------------------------


class TestDegenerateInput:
    def test_empty_content(self):
        out = convert("")
        assert out.markdown == ""
        assert out.media_paths == set()

    def test_whitespace_only_content(self):
        out = convert("\n\n   \n")
        assert out.markdown == ""
        assert out.media_paths == set()

    def test_none_content_does_not_crash(self):
        out = convert(None)
        assert out.markdown == ""
        assert out.media_paths == set()


# --------------------------------------------------------------------------
# prettify markdown
# --------------------------------------------------------------------------


class TestPrettifyMarkdown:
    def test_removes_excessive_newlines(self):
        markdown = (
            "Line 1."
            "\n\n\n"
            "Line 2. Two sentences."
            "\n\n"
            "Line 3."
            "\n"
            "Continuation of line 3"
            "\n\n\n\n\n\n\n\n\n"
            "Last line."
        )
        expected = (
            "Line 1."
            "\n\n"
            "Line 2. Two sentences."
            "\n\n"
            "Line 3."
            "\n"
            "Continuation of line 3"
            "\n\n"
            "Last line."
        )
        out = prettify_markdown(markdown)
        assert out == expected
