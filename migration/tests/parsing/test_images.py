import pytest

from src.parsing.images import get_wp_image_id


@pytest.mark.parametrize(
    "classes, expected",
    [
        (["wp-image-1"], "1"),
        (["wp-image-123"], "123"),
        (["wp-image-1234"], "1234"),
        (["wp-image-12345"], "12345"),
        (["some-class"], None),
        ([""], None),
        ([], None),
        (["some-class", "wp-image-123"], "123"),
        (["wp-image-123", "some-class"], "123"),
        (["wp-image-123", "wp-image-456"], "123"),
        (["wp-image-456", "wp-image-123"], "456"),
    ],
)
def test_get_wp_image_id(classes, expected):
    assert get_wp_image_id(classes) == expected
