# migration

[nicelittleadventures.com](https://nicelittleadventures.com) was originally a WordPress site, and I switched it to a static site (built with [Hugo](https://gohugo.io)).
I used the code in this repo to do the bulk of the migration.
It extracts the content and metadata from each post and page on the WordPress site (from an XML export), converts it to markdown, and then places that markdown file into the correct subdirectory for the static site.
It also places copies of the image files for each post alongside the markdown (`index.md`) files.

**Note:** this is _**not**_ just a trivial HTML-to-markdown converter.
The output markdown files are a mix of markdown syntax, raw HTML, and Hugo shortcodes.
I made some decisions based on the conventions used on my specific WordPress site, and my preferred way of maintaining my static site.
Some examples:
- My post excerpts on WordPress use a hacky workaround to encode a subtitle and excerpt. `excerpts.py` includes logic for extracting those pieces.
- For images, I prefer to use raw HTML (`<figure><img href="image.png"></figure>`) rather than markdown syntax (`![](image.png)`) because it allows for more flexible formatting later on (adding captions, etc.)
- ...

## basic usage

_Note: I recommend using uv, but it's not strictly necessary._

```bash
uv run python -m src.migrate
```

## pre-requisites

The following must exist in the `wp_migration/` directory:
- The WordPress site XML export (e.g., mysite.WordPress.2026-09-23.xml`)
- A directory with the contents of `public_html/wp-content/uploads/` on the WordPress site (i.e., all of the media files)

Those files are excluded from git, but see `wp_migration/README.md` for details on creating them.

## contents

Important files are noted in **bold.**
- `src/`
  - `parsing/`
    - **`markdown.py`:** Convert HTML posts/pages to markdown. Key functions/classes: `content_to_markdown`, `WPMarkdownConverter` 
    - **`wordpress_parser.py`:** Parse the WordPress XML export and extract key elements. Key functions/classes: `parse_wordpress_xml`, `Post`
    - `excerpts.py`: extracting my custom (hacky) post excerpts into `(subtitle, excerpt)`
    - `images.py`: utilities related to images
    - `settings.py`: helper class to hold settings that are shared across modules
    - `slugs.py`: utilities related to post slugs
    - `youtube.py`: utilities related to embedded YouTube videos
  - `config.py`: configuration settings, such as source and target directories, posts to skip, HTML classes to keep, etc.
  - **`migrate.py`: Entry point.** Parse all posts and pages, then write markdown files and copy all media files to the appropriate location.
- `tests/`: unit tests, mirroring the structure of `src/`
- `wp_migration_files/`: See "pre-requisites" section above
