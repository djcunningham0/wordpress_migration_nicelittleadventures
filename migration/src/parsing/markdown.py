import html
import re
from dataclasses import dataclass, field

import mdformat
from bs4 import NavigableString, Tag
from markdownify import MarkdownConverter

from src.config import KEEP_CUSTOM_DIV_CLASSES
from src.parsing.images import strip_wp_size_suffix
from src.parsing.youtube import create_youtube_shortcode


MARKDOWNIFY_ARGS = {
    "heading_style": "ATX",
    "bullets": "-",
    "strong_em_symbol": "*",
    "escape_asterisks": True,
    "escape_underscores": True,
    "wrap": False,
    "autolinks": False,
}

# footnote pattern in the HTML content, e.g. <sup data-fn="uuid">1</sup>
FOOTNOTE_PLACEHOLDER_RE = re.compile(
    r'<sup[^>]*data-fn="([0-9a-f-]+)"[^>]*>.*?</sup>',
    re.DOTALL,
)


@dataclass
class MarkdownOutput:
    markdown: str
    images: set[str] = field(default_factory=set)
    videos: set[str] = field(default_factory=set)


class WPMarkdownConverter(MarkdownConverter):
    """Converts WordPress block HTML to Markdown, keeping images, videos, and embeds as
    raw HTML for flexibility in Hugo."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images: set[str] = set()  # collected as a side effect of conversion
        self.videos: set[str] = set()

    def convert_img(self, el: Tag, text: str, parent_tags: set) -> str:
        src = el.get("src", "")
        alt = el.get("alt", "")

        # self linking images will have an <a> parent tag linking to the full resolution image
        if el.parent is not None and el.parent.name == "a":
            href = el.parent.get("href", "")
            if strip_wp_size_suffix(href) == strip_wp_size_suffix(src):
                src = href

        if src:
            self.images.add(src)

        attrs = f'src="{html.escape(src)}"'
        if alt:
            attrs += f' alt="{html.escape(alt)}"'
        return f"<img {attrs}>\n"

    def convert_video(self, el: Tag, text: str, parent_tags: set) -> str:
        src = el.get("src", "")
        if src:
            self.videos.add(src)

        attrs = []
        if el.get("controls") is not None:
            attrs.append("controls")
        if el.get("playsinline") is not None:
            attrs.append("playsinline")

        attrs.append(f'src="{html.escape(src)}"')
        attrs = " ".join(attrs)
        return f"<video {attrs}></video>\n"

    def convert_figcaption(self, el: Tag, text: str, parent_tags: set) -> str:
        """Keep `<figcaption>` tags so they can be formatted with CSS.

        Note: include double new lines so Hugo interprets the inner part as markdown,
        not HTML.
        """
        return f"<figcaption>\n\n{text.strip()}\n\n</figcaption>\n"

    def convert_a(self, el: Tag, text: str, parent_tags: set) -> str:
        children = [
            c
            for c in el.children
            if not (isinstance(c, NavigableString) and not c.strip())
        ]

        # Self-linking image: <a href="..."><img/></a> with nothing else inside. These
        # are handled by `self.convert_img`, so no additional processing needed here.
        if len(children) == 1 and getattr(children[0], "name", None) == "img":
            return text + "\n"

        return super().convert_a(el, text, parent_tags)

    def convert_figure(self, el: Tag, text: str, parent_tags: set) -> str:
        """Keep `<figure>` tags if there are any images, videos, or figcaptions in them.
        Otherwise fall back to default behavior (strip `<figure>` tags.)

        Note: include double new lines so Hugo interprets the inner part as markdown,
        not HTML.
        """
        child_types = {x.name for x in el.find_all()}
        if any(x in child_types for x in ["img", "video", "figcaption"]):
            return f"<figure>\n\n{text.strip()}\n\n</figure>"
        return text + "\n"

    def convert_iframe(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"{el}\n"

    def convert_div(self, el: Tag, text: str, parent_tags: set) -> str:
        """In general, strip `<div>` tags. But apply special processing to the following
        cases:

        ### custom div classes ###
        If a `<div>` has a class listed in `config.KEEP_CUSTOM_DIV_CLASSES`, keep it.
        These custom div classes are used for formatting.

        ### embeds ###
        If the `<div>` has a "wp-block-embed__wrapper" class, it is an embedded URL. If
        it is a YouTube URL, convert to a Hugo shortcode. Otherwise convert to a
        hyperlink. (Note: generally, putting the exact URL in an <iframe> will not work;
        that's why we're leaving it as a hyperlink.)

        Keep `<div>` tags with the specified classes in `KEEP_CUSTOM_DIV_CLASSES`;
        otherwise strip them (normal `MarkdownConverter` behavior.)
        """
        classes = el.get("class", [])

        matched_classes = set(classes).intersection(set(KEEP_CUSTOM_DIV_CLASSES))
        if matched_classes:
            class_str = " ".join(matched_classes)
            return f'<div class="{class_str}">\n\n{text}\n</div>\n'

        if "wp-block-embed__wrapper" in classes:
            # youtube is straightforward to handle: rely on the Hugo shortcode
            if "is-provider-youtube" in el.parent.get("class", []):
                return create_youtube_shortcode(el.text) + "\n"

            # otherwise, return a hyperlink to the URL
            else:
                hyperlink = Tag(name="a", attrs={"href": el.text.strip()})
                hyperlink.string = el.text.strip()
                return super().convert_a(hyperlink, hyperlink.text, {})
                # return hyperlink in HTML format rather than markdown format because
                # these divs are usually (always?) nested inside `<figure>` tags
                return str(hyperlink)

        return super().convert_div(el, text, parent_tags)


def get_default_markdown_converter() -> WPMarkdownConverter:
    return WPMarkdownConverter(**MARKDOWNIFY_ARGS)


def content_to_markdown(
    html_content: str,
    footnotes_json: list[dict[str, str]],
) -> MarkdownOutput:
    """Convert HTML content to Markdown."""

    if not html_content:
        return MarkdownOutput(markdown="")

    html_content = replace_footnote_markers_with_placeholders(html_content)
    converter = get_default_markdown_converter()
    markdown = converter.convert(html_content).strip()
    markdown = resolve_footnotes(markdown, footnotes_json)

    # prettify markdown
    markdown = mdformat.text(
        markdown,
        options={"wrap": "keep", "number": True},
        extensions=["footnote", "simple_breaks", "frontmatter", "gfm"],
    )

    return MarkdownOutput(
        markdown=markdown, images=converter.images, videos=converter.videos
    )


def replace_footnote_markers_with_placeholders(html: str) -> str:
    """Replace footnote pattern in the HTML content with @@FOOTNOTE:uuid@@ placeholders
    for easy replacement later. This way we don't have to worry about how `markdownify`
    handles the <sup> tags."""
    return FOOTNOTE_PLACEHOLDER_RE.sub(r"@@FOOTNOTE:\1@@", html)


def resolve_footnotes(markdown: str, footnotes: list[dict]) -> str:
    """Resolve footnote placeholders in the markdown content with actual footnote
    definitions."""

    footnotes_by_id = {fn["id"]: fn["content"] for fn in footnotes}
    order: list[str] = []  # ids in order of first appearance

    def repl(match: re.Match) -> str:
        fn_id = match.group(1)
        if fn_id not in order:
            order.append(fn_id)
        n = order.index(fn_id) + 1
        return f"[^{n}]"

    placeholder_re = re.compile(r"@@FOOTNOTE:([0-9a-f-]+)@@")
    body = placeholder_re.sub(repl, markdown)

    if not order:
        return body

    definitions = []
    for n, fn_id in enumerate(order, start=1):
        content_html = footnotes_by_id.get(fn_id, "")
        converter = get_default_markdown_converter()
        content_md = converter.convert(content_html)
        definitions.append(f"[^{n}]: {content_md}")

    return body + "\n\n" + "\n".join(definitions)
