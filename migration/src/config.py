import os
import warnings

from dotenv import load_dotenv

load_dotenv()

XML_PATH = os.getenv("XML_PATH")
HUGO_TARGET_DIR = ".."

if XML_PATH is None:
    warnings.warn("XML_PATH is not set in `.env`")

SITE_URL = "https://nicelittleadventures.com"

AUTHOR_OVERRIDES = {"siyangsun": "Siyang"}
SKIP_IDS = [
    2,  # Posts
    7,  # Contact
    3958,  # "do not delete" page
    1104,  # MailPoet subscription
    1693,  # MailPoet confirmation
    2286,  # Home
]

# keep `<div>` tags with these classes when converting HTML to markdown (normally,
# `<div>` tags are stripped out)
KEEP_CUSTOM_DIV_CLASSES = [
    "author-danny",
    "author-siyang",
    "author-sean",
]
