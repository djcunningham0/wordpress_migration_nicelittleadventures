from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import mdformat
from bs4 import NavigableString, Tag
from markdownify import MarkdownConverter

from src.parsing.images import get_wp_image_id
from src.parsing.settings import ParseSettings
from src.parsing.youtube import create_youtube_shortcode

if TYPE_CHECKING:
    from src.parsing.wordpress_parser import MediaObject


logger = logging.getLogger(__name__)

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
    media_paths: set[str] = field(default_factory=set)


class WPMarkdownConverter(MarkdownConverter):
    """Converts WordPress block HTML to Markdown, keeping images, videos, and embeds as
    raw HTML for flexibility in Hugo."""

    def __init__(
        self,
        *args,
        post_id_to_slug: dict[str, str],
        media_by_id: dict[str, MediaObject],
        parse_settings: ParseSettings | None = None,
        **kwargs,
    ):
        kwargs = {**MARKDOWNIFY_ARGS, **kwargs}  # use kwargs, fall back to default
        super().__init__(*args, **kwargs)

        self.post_id_to_slug = post_id_to_slug
        self.media_by_id = media_by_id
        self.parse_settings = parse_settings or ParseSettings()

        # uploaded images and videos to place alongside markdown files
        # (collected as a side effect of conversion)
        self.media_paths: set[str] = set()

    def convert_img(self, el: Tag, text: str, parent_tags: set) -> str:
        """Return <img> HTML tags rather than Markdown-style images for greater
        formatting flexibility. Keep alt text and remove other attributes.

        For uploaded images (which should be most or all of them), point to the file
        name and store the relative file path so we can copy the image to the right
        location later.

        For images at other URLs, use the src URL.
        """
        # uploaded image have class "wp-image-####"
        classes = el.get("class", [])
        image_id = get_wp_image_id(classes)

        src = None
        if image_id is not None:
            try:
                image = self.media_by_id[image_id]
                self.media_paths.add(image.file_path)  # path/to/img_123.jpg
                src = image.file_name  # img_123.jpg
            except KeyError:
                logger.info(
                    "could not find image with ID %s; from link %s", image_id, str(el)
                )

        # otherwise use the src from the image
        if src is None:
            src = str(el.get("src", ""))

        attrs = f'src="{html.escape(src)}"'
        alt = str(el.get("alt", ""))
        if alt:
            attrs += f' alt="{html.escape(alt)}"'
        return f"<img {attrs}>\n"

    def convert_video(self, el: Tag, text: str, parent_tags: set) -> str:
        """Similar handling to images: point to the file name for uploaded videos, and
        point to the src URL for other videos.

        But there's no class in the <video> tag identifying the source ID like there is
        for <img> tags, so we look it up by URL instead of ID
        """
        src: str = str(el.get("src", "")).strip()

        d = self.media_by_id
        video = next((d[x] for x in d if d[x].url.strip() == src), None)

        if video is not None:
            self.media_paths.add(video.file_path)  # path/to/vid_123.mp4
            src = video.file_name  # vid_123.mp4

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
        # Self-linking image: <a href="..."><img/></a> with nothing else inside. We
        # don't want to keep these links.
        children = [
            c
            for c in el.children
            if not (isinstance(c, NavigableString) and not c.strip())
        ]
        if len(children) == 1 and getattr(children[0], "name", None) == "img":
            return text + "\n"

        # relative links (identified via `data-type="post"` or `"page"`):
        # get the relative path and render as Hugo `ref` shortcode
        data_type = el.get("data-type")
        if data_type in ["post", "page"]:
            data_id: str = el.get("data-id", "")
            href = str(el.get("href", ""))
            parts = urlsplit(href)
            try:
                # if post ID has a known slug, use it
                slug = self.post_id_to_slug[data_id.strip()]
            except KeyError:
                # fall back to the path in the href
                slug = parts.path.lstrip("/")

            if parts.fragment:
                slug += f"#{parts.fragment}"

            if data_type == "post":
                prefix = self.parse_settings.posts_subdir
            else:
                prefix = self.parse_settings.pages_subdir

            ref_path = str(Path(prefix) / Path(slug))
            shortcode = f'{{{{< ref "{ref_path}" >}}}}'
            el["href"] = shortcode

        return super().convert_a(el, text, parent_tags)

    def convert_figure(self, el: Tag, text: str, parent_tags: set) -> str:
        """Keep `<figure>` tags if there are any images, videos, or figcaptions in them.
        Otherwise fall back to default behavior (strip `<figure>` tags.)

        Note: include double new lines so Hugo interprets the inner part as markdown,
        not HTML.
        """
        child_types = {x.name for x in el.find_all()}
        if any(x in child_types for x in ["img", "video", "figcaption"]):
            return f"<figure>\n\n{text.strip()}\n\n</figure>\n"
        return text + "\n"

    def convert_iframe(self, el: Tag, text: str, parent_tags: set) -> str:
        return f"{el}\n"

    def convert_div(self, el: Tag, text: str, parent_tags: set) -> str:
        """In general, strip `<div>` tags. But apply special processing to the following
        cases:

        ### custom div classes ###
        If a `<div>` has a class listed in `self.parse_settingskeep_div_classes`, keep
        it. These custom div classes are used for formatting.

        ### embeds ###
        If the `<div>` has a "wp-block-embed__wrapper" class, it is an embedded URL. If
        it is a YouTube URL, convert to a Hugo shortcode. Otherwise convert to a
        hyperlink. (Note: generally, putting the exact URL in an <iframe> will not work;
        that's why we're leaving it as a hyperlink.)

        ### other known edge cases ###
        - Strava embeds
        """
        classes = set(el.get("class", []))

        ### custom div classes
        matched_classes = classes.intersection(self.parse_settings.keep_div_classes)
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

        if "strava-embed-placeholder" in classes:
            return f"{el}\n"

        return super().convert_div(el, text, parent_tags)

    def convert_table(self, el: Tag, text: str, parent_tags: set) -> str:
        """Align pipes in markdown tables using `mdformat-gfm`. Only run on tables
        rather than the whole markdown file to prevent other unwanted changes.
        """
        out = super().convert_table(el, text, parent_tags)
        return mdformat.text(out, extensions=["gfm"])

    def convert_script(self, el: Tag, text: str, parent_tags: set) -> str:
        """Only keep known edge cases."""
        # Strava embeds
        if el.get("src") == "https://strava-embeds.com/embed.js":
            return f"{el}\n"

        return super().convert_script(el, text, parent_tags)


def content_to_markdown(
    html_content: str,
    footnotes_json: list[dict[str, str]],
    post_id_to_slug: dict[str, str],
    media_by_id: dict[str, MediaObject],
    parse_settings: ParseSettings | None = None,
) -> MarkdownOutput:
    """Convert HTML content to Markdown."""

    if not html_content:
        return MarkdownOutput(markdown="")

    html_content = replace_footnote_markers_with_placeholders(html_content)
    converter = WPMarkdownConverter(
        post_id_to_slug=post_id_to_slug,
        media_by_id=media_by_id,
        parse_settings=parse_settings,
    )
    markdown = converter.convert(html_content).strip()
    markdown = resolve_footnotes(
        markdown=markdown,
        footnotes=footnotes_json,
        post_id_to_slug=post_id_to_slug,
    )
    markdown = prettify_markdown(markdown)

    return MarkdownOutput(markdown=markdown, media_paths=converter.media_paths)


def replace_footnote_markers_with_placeholders(html: str) -> str:
    """Replace footnote pattern in the HTML content with @@FOOTNOTE:uuid@@ placeholders
    for easy replacement later. This way we don't have to worry about how `markdownify`
    handles the <sup> tags."""
    return FOOTNOTE_PLACEHOLDER_RE.sub(r"@@FOOTNOTE:\1@@", html)


def resolve_footnotes(
    markdown: str,
    footnotes: list[dict],
    post_id_to_slug: dict[str, str],
) -> str:
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
        converter = WPMarkdownConverter(
            post_id_to_slug=post_id_to_slug,
            media_by_id={},  # footnotes never contain images
        )
        content_md = converter.convert(content_html)
        definitions.append(f"[^{n}]: {content_md}")

    return body + "\n\n" + "\n".join(definitions)


def prettify_markdown(text: str) -> str:
    out = re.sub(r"\n{3,}", "\n\n", text)  # collapse 3+ newlines to 2
    return out
