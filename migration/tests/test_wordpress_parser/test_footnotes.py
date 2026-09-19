"""Footnote marker replacement, numbering and definition rendering."""

import pytest

from wordpress_parser import (
    content_to_markdown,
    replace_footnote_markers_with_placeholders,
    resolve_footnotes,
)


def sup(fn_id: str, n: int = 1) -> str:
    """A footnote marker in the shape WordPress actually emits."""
    return (
        f'<sup data-fn="{fn_id}" class="fn">'
        f'<a href="#{fn_id}" id="{fn_id}-link">{n}</a></sup>'
    )


# --------------------------------------------------------------------------
# marker -> placeholder
# --------------------------------------------------------------------------


def test_marker_becomes_placeholder():
    html = f"<p>Text.{sup('a1b2c3d4')}</p>"
    assert (
        replace_footnote_markers_with_placeholders(html)
        == "<p>Text.@@FOOTNOTE:a1b2c3d4@@</p>"
    )


def test_multiple_markers_all_replaced():
    html = f"<p>A{sup('aaaa1111')} and B{sup('bbbb2222', 2)}.</p>"
    out = replace_footnote_markers_with_placeholders(html)
    assert "@@FOOTNOTE:aaaa1111@@" in out
    assert "@@FOOTNOTE:bbbb2222@@" in out
    assert "<sup" not in out


def test_marker_spanning_newlines_is_replaced():
    """The regex is DOTALL; make sure that stays true."""
    html = '<p>Text.<sup data-fn="a1b2c3d4" class="fn">\n<a href="#x">1</a>\n</sup></p>'
    assert "@@FOOTNOTE:a1b2c3d4@@" in replace_footnote_markers_with_placeholders(html)


def test_sup_without_data_fn_is_left_alone():
    """Ordinary superscripts (e.g. 10<sup>3</sup>) must not be eaten."""
    html = "<p>10<sup>3</sup> feet</p>"
    assert replace_footnote_markers_with_placeholders(html) == html


# --------------------------------------------------------------------------
# numbering
# --------------------------------------------------------------------------


def test_numbering_follows_appearance_order_not_json_order():
    markdown = "First@@FOOTNOTE:bbbb2222@@ then second@@FOOTNOTE:aaaa1111@@."
    footnotes = [
        {"id": "aaaa1111", "content": "Listed first in JSON."},
        {"id": "bbbb2222", "content": "Listed second in JSON."},
    ]
    out = resolve_footnotes(markdown, footnotes)
    assert "First[^1] then second[^2]." in out
    assert "[^1]: Listed second in JSON." in out
    assert "[^2]: Listed first in JSON." in out


def test_repeated_id_reuses_the_same_number():
    markdown = "A@@FOOTNOTE:aaaa1111@@ B@@FOOTNOTE:bbbb2222@@ C@@FOOTNOTE:aaaa1111@@"
    footnotes = [
        {"id": "aaaa1111", "content": "One."},
        {"id": "bbbb2222", "content": "Two."},
    ]
    out = resolve_footnotes(markdown, footnotes)
    assert "A[^1] B[^2] C[^1]" in out
    assert out.count("[^1]: One.") == 1


def test_unreferenced_footnote_is_not_emitted():
    """A definition with no marker in the body should be dropped, not orphaned."""
    markdown = "Only one marker@@FOOTNOTE:aaaa1111@@."
    footnotes = [
        {"id": "aaaa1111", "content": "Referenced."},
        {"id": "bbbb2222", "content": "Never referenced."},
    ]
    out = resolve_footnotes(markdown, footnotes)
    assert "Never referenced." not in out


def test_no_footnotes_leaves_markdown_untouched():
    markdown = "Just some text."
    assert resolve_footnotes(markdown, []) == markdown


def test_markers_with_empty_footnote_list_still_numbered():
    """Markers present but JSON empty: body is renumbered, definitions are blank."""
    out = resolve_footnotes("Text@@FOOTNOTE:aaaa1111@@", [])
    assert "Text[^1]" in out


# --------------------------------------------------------------------------
# definition rendering
# --------------------------------------------------------------------------


def test_footnote_content_html_is_converted_to_markdown():
    markdown = "Text@@FOOTNOTE:aaaa1111@@"
    footnotes = [
        {
            "id": "aaaa1111",
            "content": 'Roughly <em>76 miles</em>, see <a href="https://example.com/x">here</a>.',
        }
    ]
    out = resolve_footnotes(markdown, footnotes)
    assert "[^1]: Roughly *76 miles*, see [here](https://example.com/x)." in out


# --------------------------------------------------------------------------
# end to end
# --------------------------------------------------------------------------


def test_end_to_end_footnote_conversion():
    html = f"<p>The high route begins above treeline.{sup('a1b2c3d4')}</p>"
    footnotes = [{"id": "a1b2c3d4", "content": "Unmaintained above 9,000 ft."}]
    out = content_to_markdown(html, footnotes).markdown
    assert "The high route begins above treeline.[^1]" in out
    assert "[^1]: Unmaintained above 9,000 ft." in out


def test_end_to_end_from_fixture(posts_by_id):
    post = posts_by_id["105"]
    assert "Continental Divide through the Front Range.[^1]" in post.markdown
    assert "whole game.[^2]" in post.markdown
    assert (
        "[^1]: Footnote one. With [a link](https://example.com/history)."
        in post.markdown
    )
