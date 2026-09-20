from urllib.parse import urlparse, parse_qs


def create_youtube_shortcode(youtube_url: str):
    youtube_id = extract_youtube_id(youtube_url)
    return f"{{{{< youtube {youtube_id} >}}}}"


def extract_youtube_id(url: str) -> str | None:
    """Extract the YouTube video ID from a URL. Returns the video ID, or None if it
    can't be found.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname.lower() if parsed.hostname else ""

    # Strip leading "www." for easier matching
    if hostname.startswith("www."):
        hostname = hostname[4:]

    # youtu.be/VIDEO_ID
    if hostname == "youtu.be":
        video_id = parsed.path.lstrip("/")
        return video_id if video_id else None

    if hostname in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        # /watch?v=VIDEO_ID
        if parsed.path == "/watch":
            query = parse_qs(parsed.query)
            video_id = query.get("v")
            return video_id[0] if video_id else None

        # /embed/VIDEO_ID or /v/VIDEO_ID or /shorts/VIDEO_ID or /live/VIDEO_ID
        for prefix in ("/embed/", "/v/", "/shorts/", "/live/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix) :].split("/")[0]
                return video_id if video_id else None

    return None
