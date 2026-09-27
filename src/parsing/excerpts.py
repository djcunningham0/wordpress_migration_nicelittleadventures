from bs4 import BeautifulSoup


def parse_custom_excerpt(excerpt: str) -> tuple[str, str]:
    """Parse the custom excerpt HTML to extract the subtitle and excerpt. Convention:
    my wordpress posts put the subtitle in an `<h5 class="page-description">` tag and
    the excerpt in a `<p> tag below it.

    Example:
    <hr>
    <h5 class="page-description"><i>
    This is the subtitle
    </i></h5>
    <p>
    And this is the excerpt text.
    </p>
    """
    if excerpt is None:
        return "", ""

    soup = BeautifulSoup(excerpt, "html.parser")
    subtitle = soup.select_one("h5.page-description")
    paragraph = soup.find("p")
    return (
        normalize(subtitle) if subtitle else "",
        normalize(paragraph) if paragraph else "",
    )


def normalize(element) -> str:
    """Normalize the text content of an HTML element by stripping whitespace and joining
    lines."""
    return " ".join(element.get_text().split())
