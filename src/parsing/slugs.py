from slugify import slugify


def create_unique_slug(slug: str, used_slugs: set[str]):
    """Force slugs to a common format (lowercase, hyphenated), and make sure they are
    unique among previously seen slugs. Add an incrementing number if the slug has
    previously been seen."""
    slug = slugify(slug)
    if slug not in used_slugs:
        used_slugs.add(slug)
        return slug

    n = 2
    while f"{slug}-{n}" in used_slugs:
        n += 1

    out = f"{slug}-{n}"
    used_slugs.add(out)
    return out
