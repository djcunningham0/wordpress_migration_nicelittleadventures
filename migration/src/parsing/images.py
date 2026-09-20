import re


def strip_wp_size_suffix(url: str) -> str:
    """Remove a trailing WordPress resize suffix like '-1024x768' before the
    extension.

    Example:
    >>> url = "https://example.com/wp-content/uploads/image-1024x768.jpg"
    >>> strip_wp_size_suffix(url)
    'https://example.com/wp-content/uploads/image.jpg'
    """
    return re.sub(r"-\d+x\d+(?=\.\w+(?:\?.*)?$)", "", url)
