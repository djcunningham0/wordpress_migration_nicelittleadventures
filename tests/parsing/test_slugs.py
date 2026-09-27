import pytest

from src.parsing.slugs import create_unique_slug


class TestSlugs:
    @pytest.mark.parametrize(
        "input_slug, expected",
        [
            ("a-slug", "a-slug"),
            ("A-slug", "a-slug"),
            ("A-SLUG", "a-slug"),
            ("a slug", "a-slug"),
            ("ANOTHER slug", "another-slug"),
            ("ANOTHER SLUG", "another-slug"),
            ("Another Slug", "another-slug"),
            ("Another sluG", "another-slug"),
        ],
    )
    def test_slug_is_lowercase(self, input_slug, expected):
        assert create_unique_slug(input_slug, used_slugs=set()) == expected

    def test_duplicate_slugs_are_incremented(self):
        used_slugs = {"a-post", "another-post", "another-post-2"}
        assert create_unique_slug("a-post", used_slugs) == "a-post-2"
        assert create_unique_slug("a-post", used_slugs) == "a-post-3"
        assert create_unique_slug("another-post-2", used_slugs) == "another-post-2-2"
