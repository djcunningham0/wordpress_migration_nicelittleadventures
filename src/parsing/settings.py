from dataclasses import dataclass, field

from src.config import (
    AUTHOR_OVERRIDES,
    HUGO_PAGES_SUBDIR,
    HUGO_POSTS_SUBDIR,
    KEEP_HTML_CLASSES,
    SKIP_IDS,
)


@dataclass
class ParseSettings:
    skip_ids: set[str] = field(default_factory=lambda: SKIP_IDS)
    author_overrides: dict[str, str] = field(default_factory=lambda: AUTHOR_OVERRIDES)
    keep_class_map: dict[str, dict[str, str]] = field(
        default_factory=lambda: KEEP_HTML_CLASSES
    )
    posts_subdir: str = HUGO_POSTS_SUBDIR
    pages_subdir: str = HUGO_PAGES_SUBDIR
