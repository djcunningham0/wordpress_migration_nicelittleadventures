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

# keep `<div>` tags with these classes when converting HTML to markdown (normally,
# `<div>` tags are stripped out)
KEEP_CUSTOM_DIV_CLASSES = {
    "author-danny",
    "author-siyang",
    "author-sean",
}

AUTHOR_OVERRIDES = {"siyangsun": "Siyang"}
