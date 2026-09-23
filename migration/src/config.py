import os
import warnings

from dotenv import load_dotenv

load_dotenv()


# -------------------------------
# Local filesystem paths
# -------------------------------

# Sources (Wordpress export)
XML_PATH = os.getenv("XML_PATH")  # XML export location in local filesystem
MEDIA_DIR = "./wp_migration_files/uploads"  # media export directory in local filesystem

if XML_PATH is None:
    warnings.warn("XML_PATH is not set in `.env`")

# Targets (static site configuration)
HUGO_TARGET_DIR = ".."
HUGO_POSTS_SUBDIR = "posts"  # relative to `content/`
HUGO_PAGES_SUBDIR = ""  # relative to `content/`

# -------------------------------
# Migration settings
# -------------------------------

SKIP_IDS = {
    "2",  # Posts
    "7",  # Contact
    "3958",  # "do not delete" page
    "1104",  # MailPoet subscription
    "1693",  # MailPoet confirmation
    "2286",  # Home
}

# keep these classes in tags and optionally rename them (and prevent the tag from being
# stripped by the markdown conversion if it normally would be)
KEEP_HTML_CLASSES = {
    # tag: {source_class: renamed_class}
    "div": {
        "author-danny": "author-danny",
        "author-siyang": "author-siyang",
        "author-sean": "author-sean",
        "alignwide": "alignwide",
        "wp-block-columns": "img-row",
    },
    "figure": {
        "alignwide": "alignwide",
    },
}

AUTHOR_OVERRIDES = {"siyangsun": "Siyang"}
