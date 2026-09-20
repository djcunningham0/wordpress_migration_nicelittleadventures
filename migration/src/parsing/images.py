import re


def strip_wp_size_suffix(url: str) -> str:
    """Remove a trailing WordPress resize suffix of the following formats before the
    file extension:
    - "-{width}x{height}" (e.g., "1024x768")
    - "-scaled"

    Example:
    >>> url = "https://example.com/wp-content/uploads/image-1024x768.jpg"
    >>> strip_wp_size_suffix(url)
    'https://example.com/wp-content/uploads/image.jpg'

    >>> url = "https://example.com/image-scaled.png"
    >>> strip_wp_size_suffix(url)
    'https://example.com/image.jpg'
    """
    return re.sub(r"-(?:\d+x\d+|scaled)(?=\.\w+(?:\?.*)?$)", "", url)
