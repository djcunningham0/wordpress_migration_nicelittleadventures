import pytest

from src.parsing.youtube import extract_youtube_id


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.youtube.com/watch?v=9uBATQJIArE", "9uBATQJIArE"),
        ("https://youtu.be/PoIngwoBW-Q", "PoIngwoBW-Q"),
        (
            "https://www.youtube.com/watch?v=pzSHqwNdVqE&amp;ab_channel=MostlySimpsons",
            "pzSHqwNdVqE",
        ),
        ("https://www.youtube.com/v/123", "123"),
        ("https://www.youtube.com/embed/123", "123"),
    ],
)
def test_extract_youtube_id(url, expected):
    assert extract_youtube_id(url) == expected
