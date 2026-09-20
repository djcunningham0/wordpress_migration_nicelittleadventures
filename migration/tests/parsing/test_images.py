import pytest

from src.parsing.images import strip_wp_size_suffix


@pytest.mark.parametrize(
    "file_name, expected",
    [
        (
            "https://example.com/wp-content/uploads/image-1024x768.jpg",
            "https://example.com/wp-content/uploads/image.jpg",
        ),
        (
            "example.com/wp-content/uploads/image-1024x768.jpg",
            "example.com/wp-content/uploads/image.jpg",
        ),
        ("image-1024x768.jpg", "image.jpg"),
        ("image-1024x1024.jpg", "image.jpg"),
        ("image-123x456.jpg", "image.jpg"),
        ("image-123x4567.jpg", "image.jpg"),
        ("image-1x2.jpg", "image.jpg"),
        ("image-1x2.jpeg", "image.jpeg"),
        ("image-1x2.png", "image.png"),
        ("image-1x2.PNG", "image.PNG"),
    ],
)
def test_strip_wp_size_suffix(file_name, expected):
    assert strip_wp_size_suffix(file_name) == expected


@pytest.mark.parametrize(
    "file_name, expected",
    [
        (
            "https://example.com/wp-content/uploads/image-scaled.jpg",
            "https://example.com/wp-content/uploads/image.jpg",
        ),
        ("https://example.com/image-scaled.jpg", "https://example.com/image.jpg"),
        ("image-scaled.jpg", "image.jpg"),
    ],
)
def test_strip_wp_size_suffix_scaled(file_name, expected):
    assert strip_wp_size_suffix(file_name) == expected


@pytest.mark.parametrize(
    "file_name",
    [
        "https://example.com/wp-content/uploads/image.jpg",
        "example.com/wp-content/uploads/image.jpg",
        "image.jpg",
    ],
)
def test_strip_wp_size_suffix_with_no_suffix(file_name):
    assert strip_wp_size_suffix(file_name) == file_name
