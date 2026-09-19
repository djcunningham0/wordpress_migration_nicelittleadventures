"""HTML -> markdown conversion.

These use inline snippets rather than the XML fixture: the input sits next to
the assertion, which is what you want when you're adding a case every time you
discover a new block type in the real export.

Assertions are deliberately loose (substring / "is present") rather than exact
full-document equality. Exact-match tests on markdownify + mdformat output break
on every dependency bump for reasons that have nothing to do with your code.
Assert the thing you actually care about.
"""

import pytest

from wordpress_parser import content_to_markdown


def convert(html: str) -> str:
    return content_to_markdown(html, [])


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
        ],
    )
    def test_basic_blocks(self, html, expected):
        assert expected in convert(html)

    def test_gutenberg_comments_are_stripped(self):
        html = "<!-- wp:paragraph -->\n<p>Body text.</p>\n<!-- /wp:paragraph -->"
        out = convert(html)
        assert "wp:paragraph" not in out
        assert "Body text." in out

    def test_heading_style_is_atx(self):
        out = convert("<h1>Title</h1>")
        assert out.startswith("# Title")
        assert "===" not in out


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------


SELF_LINKING_IMAGE = (
    '<figure class="wp-block-image size-large">'
    '<a href="https://example.com/wp-content/uploads/2023/08/ridge.jpg">'
    '<img src="https://example.com/wp-content/uploads/2023/08/ridge-1024x768.jpg" '
    "</figure>"
)


class TestImages:
    @pytest.mark.xfail()
    def test_image_converts_to_html_and_strips_class(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" class="wp-image-202"/>'
            "</figure>"
        )
        out = convert(html).strip()
        assert out == ('<figure>\n<img src="https://example.com/a.jpg"/>\n</figure>')

    @pytest.mark.xfail()
    def test_alt_text_is_preserved(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" alt="Alt text" class="wp-image-202"/>'
            "</figure>"
        )
        out = convert(html).strip()
        assert out == (
            '<figure>\n<img src="https://example.com/a.jpg" alt="Alt text"/>\n</figure>'
        )

    @pytest.mark.xfail()
    def test_image_keeps_caption(self):
        html = (
            '<figure class="wp-block-image size-full">'
            '<img src="https://example.com/a.jpg" class="wp-image-202"/>'
            '<figcaption class="wp-element-caption">A caption.</figcaption>'
            "</figure>"
        )
        out = convert(html).strip()
        assert out == (
            "<figure>\n"
            '<img src="https://example.com/a.jpg"/>\n'
            "<figcaption>A caption.</figcaption>\n"
            "</figure>"
        )

    @pytest.mark.xfail()
    def test_self_linking_image_removes_link(self):
        """Pull the href image."""
        out = convert(SELF_LINKING_IMAGE)
        assert out == (
            "<figure>\n"
            '<img src="https://example.com/wp-content/uploads/2023/08/ridge-1024x768.jpg" '
            "</figure>"
        )


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------


def _columns(*column_inner: str, widths: list[str] | None = None) -> str:
    cols = []
    for i, inner in enumerate(column_inner):
        if widths:
            cols.append(
                f'<div class="wp-block-column" style="flex-basis:{widths[i]}">{inner}</div>'
            )
        else:
            cols.append(f'<div class="wp-block-column">{inner}</div>')
    return '<div class="wp-block-columns">' + "".join(cols) + "</div>"


IMG_A = '<figure class="wp-block-image"><img src="https://example.com/a.jpg" alt="A"/></figure>'
IMG_B = '<figure class="wp-block-image"><img src="https://example.com/b.jpg" alt="B"/></figure>'


class TestColumns:
    @pytest.mark.xfail()
    def test_columns_TODO(self):
        assert False


# --------------------------------------------------------------------------
# embeds: iframes and video
# --------------------------------------------------------------------------


class TestEmbeds:
    @pytest.mark.xfail(
        reason="markdownify drops <iframe> entirely — silent data loss on every map embed",
        strict=True,
    )
    def test_iframe_survives_conversion():
        iframe_block = (
            '<iframe src="https://caltopo.com/m/ABC123" width="100%" height="500" '
            'frameborder="0" allowfullscreen></iframe>'
        )
        out = convert(iframe_block)
        assert "caltopo.com/m/ABC123" in out

    @pytest.mark.xfail(
        reason="<video> becomes an empty link: [](url)",
        strict=True,
    )
    def test_self_hosted_video_is_preserved(self):
        html = (
            '<figure class="wp-block-video">'
            '<video controls src="https://example.com/flyover.mp4"></video>'
            "</figure>"
        )
        out = convert(html).strip()
        assert out == (
            "<figure>\n"
            '<video controls src="https://example.com/flyover.mp4"></video>\n'
            "</figure>"
        )

    @pytest.mark.xfail()
    def test_youtube_embed_is_converted_to_hugo_shortcode(self):
        """The oEmbed block is a bare URL in a wrapper div; at minimum the URL must remain."""
        html = (
            '<figure class="wp-block-embed is-provider-youtube">'
            '<div class="wp-block-embed__wrapper">\n'
            "https://www.youtube.com/watch?v=aqz-KE-bpKQ\n"
            "</div></figure>"
        )
        assert "{{< youtube aqz-KE-bpKQ >}}" in convert(html)


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
        out = convert(table_with_header)
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
        out = convert(html)
        assert "No header row" in out
        assert "on this one" in out
        assert "body cells" in out


# --------------------------------------------------------------------------
# quotes
# --------------------------------------------------------------------------


PULLQUOTE = (
    '<figure class="wp-block-pullquote"><blockquote>'
    "<p>The mountains are calling and I must go.</p>"
    "<cite>John Muir</cite></blockquote></figure>"
)

BLOCKQUOTE = (
    '<blockquote class="wp-block-quote"><p>A regular block quote.</p></blockquote>'
)


class TestQuotes:
    def test_blockquote(self):
        out = convert(BLOCKQUOTE)
        assert "> A regular block quote." in out

    def test_pullquote_becomes_blockquote(self):
        out = convert(PULLQUOTE)
        assert "> The mountains are calling and I must go." in out

    @pytest.mark.xfail(
        reason="<cite> is emitted as a plain quoted line, not visibly an attribution",
        strict=True,
    )
    def test_citation_is_marked_as_a_citation(self):
        out = convert(PULLQUOTE)
        assert "— John Muir" in out or "*John Muir*" in out


# --------------------------------------------------------------------------
# author divs (custom handling hook)
# --------------------------------------------------------------------------


class TestAuthorDivs:
    AUTHOR_DIVS = (
        '<div class="author-danny"><p>One of us says a thing.</p></div>'
        '<div class="author-sayang"><p>The other says another thing.</p></div>'
    )

    @pytest.mark.xfail()
    def test_author_divs_survive_conversion(self):
        out = convert(AUTHOR_DIVS)
        assert 'class="author-danny"' in out
        assert 'class="author-sayang"' in out

    @pytest.mark.xfail()
    def test_exact_author_div_output(self):
        out = convert(self.AUTHOR_DIVS)
        assert out == (
            '<div class="author-danny">\n<p>One of us says a thing.</p>\n</div>\n'
            '<div class="author-sayang">\n<p>The other says another thing.</p>\n</div>'
        )


# --------------------------------------------------------------------------
# degenerate input
# --------------------------------------------------------------------------


class TestDegenerateInput:
    def test_empty_content(self):
        assert convert("") == ""

    def test_whitespace_only_content(self):
        assert convert("\n\n   \n") == ""

    def test_none_content_does_not_crash(self):
        assert convert(None) == ""
