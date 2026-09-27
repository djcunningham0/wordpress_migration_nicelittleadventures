import re


def get_wp_image_id(classes: list[str]) -> str | None:
    """Get the ID from a class name like "wp-image-####". Returns the "####" ID of the
    first match in the list. If no match, returns None.
    """
    pattern = re.compile(r"wp-image-(\d+)")
    for item in classes:
        match = pattern.search(item)
        if match:
            return match.group(1)
