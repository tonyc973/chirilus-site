#!/usr/bin/env python3
"""
Static site generator for chirilus.dev.

Reads Markdown posts from posts/, renders them into HTML using the templates
in templates/, and writes the finished site to dist/. Also generates an
RSS feed at dist/feed.xml.

Posting a new entry is just:
    1. Create posts/YYYY-MM-DD-slug.md with frontmatter (title, date, tag, summary).
    2. Run `python build.py`.
    3. Commit and push.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import frontmatter
import markdown
from pygments.formatters import HtmlFormatter

# ─────────────────────────────  CONFIG  ─────────────────────────────

ROOT = Path(__file__).parent
TEMPLATES = ROOT / "templates"
POSTS = ROOT / "posts"
STATIC = ROOT / "static"
DIST = ROOT / "dist"

# Site root path (URL prefix). For GitHub Pages project sites, set this to
# "/<repo-name>/" via the SITE_ROOT env var. Defaults to "/" for custom
# domains and local dev.
SITE_ROOT = os.environ.get("SITE_ROOT", "/")
if not SITE_ROOT.endswith("/"):
    SITE_ROOT += "/"

SITE_URL = os.environ.get("SITE_URL", "https://chirilus.dev").rstrip("/")
SITE_TITLE = "Antonie Chirilus — Reliable LLM systems"
SITE_DESCRIPTION = (
    "Antonie Chirilus, R&D Engineer at Keysight Technologies. "
    "Building deterministic LLM systems: guided generation, validators, agents."
)
AUTHOR = "Antonie Chirilus"

VERSION = datetime.now().strftime("%Y.%m")
YEAR = datetime.now().year

# Markdown extensions: fenced code, tables, footnotes, abbreviations,
# syntax highlighting via Pygments.
MD_EXTENSIONS = [
    "fenced_code",
    "tables",
    "footnotes",
    "abbr",
    "codehilite",
    "smarty",
    "sane_lists",
    "toc",
]
MD_EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False, "css_class": "highlight"},
    "toc": {"permalink": False},
}


# ─────────────────────────────  HELPERS  ─────────────────────────────


@dataclass
class Post:
    slug: str
    title: str
    date: datetime
    tag: str
    summary: str
    body_html: str
    reading_time: int

    @property
    def url_path(self) -> str:
        return f"{SITE_ROOT}posts/{self.slug}/"

    @property
    def date_iso(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    @property
    def date_human(self) -> str:
        # e.g. "May · 17"
        return self.date.strftime("%b · %d")

    @property
    def date_list(self) -> str:
        # e.g. "May · 17" — same as date_human for the list view
        return self.date.strftime("%b · %d")


def render_template(template: str, context: dict[str, str]) -> str:
    """Substitute {{KEY}} placeholders in `template`. Unknown keys are left intact."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return context.get(key, m.group(0))
    return re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", repl, template)


def estimate_reading_time(text: str) -> int:
    words = len(re.findall(r"\b\w+\b", text))
    return max(1, round(words / 225))


def parse_post(path: Path) -> Post:
    post = frontmatter.load(path)
    meta = post.metadata

    # Derive slug from frontmatter or filename (strip leading YYYY-MM-DD-).
    slug = meta.get("slug")
    if not slug:
        stem = path.stem
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)

    title = meta.get("title")
    if not title:
        raise ValueError(f"Post {path.name} is missing required 'title' frontmatter")

    raw_date = meta.get("date")
    if isinstance(raw_date, datetime):
        date = raw_date
    elif isinstance(raw_date, str):
        date = datetime.fromisoformat(raw_date)
    else:
        # python-frontmatter parses bare dates as datetime.date
        from datetime import date as _date
        if isinstance(raw_date, _date):
            date = datetime(raw_date.year, raw_date.month, raw_date.day)
        else:
            raise ValueError(f"Post {path.name} has missing/invalid 'date' frontmatter")

    tag = meta.get("tag", "Notes")
    summary = meta.get("summary", "")

    md = markdown.Markdown(
        extensions=MD_EXTENSIONS,
        extension_configs=MD_EXTENSION_CONFIGS,
        output_format="html5",
    )
    body_html = md.convert(post.content)

    return Post(
        slug=slug,
        title=title,
        date=date,
        tag=tag,
        summary=summary,
        body_html=body_html,
        reading_time=estimate_reading_time(post.content),
    )


def pygments_css() -> str:
    """Generate Pygments CSS scoped to .highlight, tuned for the site's dark theme."""
    formatter = HtmlFormatter(style="monokai", cssclass="highlight")
    base = formatter.get_style_defs(".highlight")
    # Override background to match site surface colour, remove default padding.
    overrides = (
        ".highlight { background: transparent !important; }\n"
        ".prose .highlight { background: transparent; }\n"
    )
    return overrides + base


def render_writing_list(posts: list[Post]) -> str:
    rows = []
    for p in posts:
        rows.append(
            f'      <li class="border-b border-border">\n'
            f'        <a href="{p.url_path}" class="row grid grid-cols-[64px_1fr_auto] '
            f'md:grid-cols-[88px_1fr_120px_auto] items-baseline gap-x-5 px-3 -mx-3 py-5">\n'
            f'          <span class="font-mono text-[0.74rem] text-muted-2 tabnum">{p.date_list}</span>\n'
            f'          <span class="row-title text-[1rem] md:text-[1.05rem] text-text '
            f'font-medium tracking-tight">{p.title}</span>\n'
            f'          <span class="hidden md:block font-mono text-[0.72rem] text-muted-2">{p.tag}</span>\n'
            f'          <span class="row-arrow font-mono text-[0.85rem] text-muted">→</span>\n'
            f'        </a>\n'
            f'      </li>'
        )
    return "\n".join(rows) if rows else (
        '      <li class="py-5 font-mono text-[0.85rem] text-muted-2">No posts yet.</li>'
    )


def render_feed(posts: list[Post]) -> str:
    """Generate RSS 2.0 feed."""
    now = datetime.now(timezone.utc)
    items = []
    for p in posts[:20]:
        pub_date = format_datetime(p.date.replace(tzinfo=timezone.utc))
        link = f"{SITE_URL}{p.url_path}"
        items.append(
            f"  <item>\n"
            f"    <title>{xml_escape(p.title)}</title>\n"
            f"    <link>{link}</link>\n"
            f"    <guid isPermaLink=\"true\">{link}</guid>\n"
            f"    <pubDate>{pub_date}</pubDate>\n"
            f"    <description>{xml_escape(p.summary)}</description>\n"
            f"    <content:encoded><![CDATA[{p.body_html}]]></content:encoded>\n"
            f"  </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" '
        'xmlns:atom="http://www.w3.org/2005/Atom">\n'
        '<channel>\n'
        f'  <title>{xml_escape(SITE_TITLE)}</title>\n'
        f'  <link>{SITE_URL}{SITE_ROOT}</link>\n'
        f'  <description>{xml_escape(SITE_DESCRIPTION)}</description>\n'
        f'  <language>en</language>\n'
        f'  <lastBuildDate>{format_datetime(now)}</lastBuildDate>\n'
        f'  <atom:link href="{SITE_URL}{SITE_ROOT}feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items)
        + "\n</channel>\n</rss>\n"
    )


# ─────────────────────────────  BUILD  ─────────────────────────────


def build() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    base_tpl = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    index_tpl = (TEMPLATES / "index.html").read_text(encoding="utf-8")
    post_tpl = (TEMPLATES / "post.html").read_text(encoding="utf-8")

    syntax_css = pygments_css()
    base_ctx_common = {
        "ROOT": SITE_ROOT,
        "YEAR": str(YEAR),
        "VERSION": VERSION,
        "SYNTAX_CSS": syntax_css,
    }

    # 1. Load posts
    post_files = sorted(POSTS.glob("*.md"))
    posts = [parse_post(p) for p in post_files]
    posts.sort(key=lambda p: p.date, reverse=True)
    print(f"  • Loaded {len(posts)} post(s)")

    # 2. Render each post page
    for p in posts:
        body = render_template(post_tpl, {
            "ROOT": SITE_ROOT,
            "POST_TITLE": p.title,
            "DATE_ISO": p.date_iso,
            "DATE_HUMAN": p.date_human,
            "TAG": p.tag,
            "SUMMARY": p.summary,
            "READING_TIME": str(p.reading_time),
            "POST_CONTENT": p.body_html,
        })
        html = render_template(base_tpl, {
            **base_ctx_common,
            "TITLE": f"{p.title} — {AUTHOR}",
            "DESCRIPTION": p.summary or SITE_DESCRIPTION,
            "CANONICAL": f"{SITE_URL}{p.url_path}",
            "OG_TYPE": "article",
            "CONTENT": body,
        })
        out_dir = DIST / "posts" / p.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"  • {p.slug}  →  posts/{p.slug}/")

    # 3. Render homepage
    index_body = render_template(index_tpl, {
        "ROOT": SITE_ROOT,
        "WRITING_LIST": render_writing_list(posts),
    })
    html = render_template(base_tpl, {
        **base_ctx_common,
        "TITLE": SITE_TITLE,
        "DESCRIPTION": SITE_DESCRIPTION,
        "CANONICAL": f"{SITE_URL}{SITE_ROOT}",
        "OG_TYPE": "website",
        "CONTENT": index_body,
    })
    (DIST / "index.html").write_text(html, encoding="utf-8")
    print("  • index.html")

    # 4. RSS feed
    (DIST / "feed.xml").write_text(render_feed(posts), encoding="utf-8")
    print("  • feed.xml")

    # 5. Copy static/ if present
    if STATIC.exists():
        for src in STATIC.rglob("*"):
            if src.is_file():
                dst = DIST / src.relative_to(STATIC)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        print(f"  • static/ → dist/")

    # 6. .nojekyll so GitHub Pages doesn't try to process the output
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"\nBuilt site → {DIST}")
    print(f"Site root: {SITE_ROOT}")


if __name__ == "__main__":
    print("Building site...")
    try:
        build()
    except Exception as e:
        print(f"\nBuild failed: {e}", file=sys.stderr)
        sys.exit(1)
