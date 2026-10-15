#!/usr/bin/env python3
"""
Static site generator for roglia.ro.

Reads Markdown posts from posts/ and projects from projects.yml, renders them
with the templates in templates/, and writes the finished site to dist/
(plus feed.xml, sitemap.xml, robots.txt and 404.html).

Day to day you don't run this directly — use blog.py (see README.md):
    python3 blog.py new "Title"  ·  python3 blog.py preview  ·  python3 blog.py publish
GitHub Actions runs `python build.py` on every push to main.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import frontmatter
import markdown
import yaml

# ─────────────────────────────  CONFIG  ─────────────────────────────

ROOT = Path(__file__).parent
TEMPLATES = ROOT / "templates"
POSTS = ROOT / "posts"
STATIC = ROOT / "static"
DIST = ROOT / "dist"
PROJECTS_FILE = ROOT / "projects.yml"

# URL prefix of the site. "/" for the custom domain and local preview; a
# GitHub Pages project site would need "/<repo-name>/" (set via SITE_ROOT).
SITE_ROOT = os.environ.get("SITE_ROOT", "/")
if not SITE_ROOT.endswith("/"):
    SITE_ROOT += "/"

SITE_URL = os.environ.get("SITE_URL", "https://roglia.ro").rstrip("/")
AUTHOR = "Antonie Chirilus"
ROLE = "AI Platform Engineer"
SITE_TITLE = f"{AUTHOR} — Reliable LLM systems"
SITE_DESCRIPTION = (f"{AUTHOR}, {ROLE}. Essays on running LLMs in production — "
                    "inference, agents, and the parts nobody demos.")
EMAIL = "hello@roglia.ro"
REPO_URL = "https://github.com/tonyc973/chirilus-site"
SAME_AS = [
    "https://github.com/tonyc973",
    "https://www.linkedin.com/in/antonie-chirilus-473a5b251/",
    "https://www.kaggle.com/tonychirilus",
]

NOW = datetime.now()

# Markdown extensions: fenced code, tables, footnotes, abbreviations,
# smart quotes, § heading anchors, syntax highlighting via Pygments.
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
    "toc": {"permalink": "§", "permalink_class": "anchor", "permalink_title": "Link to this section"},
}

# The hero's dispersion spectrum (violet → vermillion). Topics and projects take
# their colour from it, so the "spectrometer" motif carries through the site.
SPECTRUM = [
    (155, 123, 255), (107, 138, 255), (95, 212, 255), (124, 240, 176),
    (190, 235, 150), (255, 176, 112), (255, 138, 95), (255, 107, 61),
]
# Every topic (the post's `tag`) gets a wavelength in nm on the 380–740 scale.
# Unknown tags get a stable wavelength derived from their name.
TOPIC_NM = {
    "meta": 405, "agents": 450, "retrieval": 475, "observability": 490, "evals": 520,
    "reliability": 545, "platform": 570, "systems": 585, "security": 600,
    "inference": 620, "notes": 650,
}


# ─────────────────────────────  HELPERS  ─────────────────────────────


@dataclass
class Post:
    slug: str
    title: str
    date: datetime
    updated: datetime | None
    tag: str
    summary: str
    result: str
    result_note: str
    body_html: str
    reading_time: int
    word_count: int

    @property
    def url_path(self) -> str:
        return f"{SITE_ROOT}posts/{self.slug}/"

    @property
    def url(self) -> str:
        return SITE_URL + self.url_path

    @property
    def date_iso(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    @property
    def modified_iso(self) -> str:
        return (self.updated or self.date).strftime("%Y-%m-%d")

    @property
    def date_human(self) -> str:
        return human_date(self.date)

    @property
    def nm(self) -> int:
        return topic_nm(self.tag)

    @property
    def line(self) -> str:
        return spectrum_at((self.nm - 380) / 360)


def human_date(d: datetime) -> str:
    return f"{d.day} {d:%b %Y}"  # "27 May 2026"


def esc(value: object) -> str:
    """Escape text for HTML element content and attribute values."""
    return html.escape(str(value), quote=True)


def smarten(text: str) -> str:
    """Curly quotes and apostrophes for frontmatter text (the Markdown body gets them from 'smarty')."""
    text = re.sub(r"(\w)'(\w)", "\\1’\\2", text)          # wasn't, 5090's
    text = re.sub(r"(^|[\s(\[{—–-])'", "\\1‘", text)
    text = re.sub(r'(^|[\s(\[{—–-])"', "\\1“", text)
    return text.replace("'", "’").replace('"', "”").replace("...", "…")


def render_template(template: str, context: dict[str, str]) -> str:
    """Substitute {{KEY}} placeholders. A key missing from `context` is a bug, so it fails loudly."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in context:
            raise KeyError(f"template placeholder {{{{{key}}}}} has no value")
        return context[key]
    return re.sub(r"\{\{([A-Z_][A-Z0-9_]*)\}\}", repl, template)


def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def to_datetime(raw: object, name: str, field: str = "date") -> datetime:
    if isinstance(raw, datetime):  # a time with an offset is normalised so all dates compare
        return raw.astimezone(timezone.utc).replace(tzinfo=None) if raw.tzinfo else raw
    if isinstance(raw, Date):  # YAML turns `date: 2026-05-17` into a date
        return datetime(raw.year, raw.month, raw.day)
    if isinstance(raw, str):
        try:
            return to_datetime(datetime.fromisoformat(raw.strip()), name, field)
        except ValueError:
            pass
    raise ValueError(f"{name}: '{field}' must look like 2026-05-17 (got {raw!r})")


def topic_nm(tag: str) -> int:
    key = tag.strip().lower()
    if key in TOPIC_NM:
        return TOPIC_NM[key]
    return 400 + int(hashlib.sha1(key.encode()).hexdigest(), 16) % 301


def spectrum_at(t: float) -> str:
    """RGB triplet ("r,g,b") at position t ∈ [0, 1] along the hero spectrum."""
    t = min(1.0, max(0.0, t))
    x = t * (len(SPECTRUM) - 1)
    i = min(len(SPECTRUM) - 2, int(x))
    f = x - i
    a, b = SPECTRUM[i], SPECTRUM[i + 1]
    return ",".join(str(round(a[k] + (b[k] - a[k]) * f)) for k in range(3))


def parse_post(path: Path) -> Post:
    try:
        post = frontmatter.load(path)
    except Exception as e:  # bad YAML: unclosed quote, wrong indentation, impossible date…
        raise ValueError(f"{path.name}: the frontmatter between the --- lines is invalid ({e})") from e
    meta = post.metadata

    # Slug from frontmatter or filename (strip leading YYYY-MM-DD-).
    slug = str(meta.get("slug") or re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem))
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        raise ValueError(f"{path.name}: the URL slug '{slug}' may only use a-z, 0-9 and dashes")

    title = str(meta.get("title") or "").strip()
    if not title:
        raise ValueError(f"{path.name}: missing 'title' in the frontmatter")
    summary = str(meta.get("summary") or "").strip()
    if not summary:
        print(f"  ! {path.name}: no 'summary' — the homepage and link previews look better with one")

    md = markdown.Markdown(
        extensions=MD_EXTENSIONS,
        extension_configs=MD_EXTENSION_CONFIGS,
        output_format="html",
    )
    body_html = md.convert(post.content)
    # Lazy-load images; wide tables and code scroll sideways on phones (focusable, so keyboards can scroll them too).
    body_html = re.sub(r"<img (?![^>]*\bloading=)", '<img loading="lazy" decoding="async" ', body_html)
    body_html = body_html.replace("<table>", '<div class="table-wrap" tabindex="0"><table>').replace("</table>", "</table></div>")
    body_html = body_html.replace("<pre>", '<pre tabindex="0">')

    words = count_words(post.content)
    return Post(
        slug=slug,
        title=smarten(title),
        date=to_datetime(meta.get("date"), path.name),
        updated=to_datetime(meta["updated"], path.name, "updated") if meta.get("updated") else None,
        tag=str(meta.get("tag") or "Notes").strip(),
        summary=smarten(summary),
        result=str(meta.get("result") or "").strip(),
        result_note=str(meta.get("result_note") or "").strip(),
        body_html=body_html,
        reading_time=max(1, round(words / 225)),
        word_count=words,
    )


def load_posts() -> list[Post]:
    # sorted file list first, so posts sharing a date keep a stable order (and stable N° numbers)
    posts = sorted((parse_post(p) for p in sorted(POSTS.glob("*.md"))), key=lambda p: p.date, reverse=True)
    seen: set[str] = set()
    for p in posts:
        if p.slug in seen:
            raise ValueError(f"two posts share the URL slug '{p.slug}' — rename one file or set 'slug:'")
        seen.add(p.slug)
    return posts


def load_projects() -> dict:
    if not PROJECTS_FILE.exists():
        return {"featured": [], "more": []}
    try:
        data = yaml.safe_load(PROJECTS_FILE.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"projects.yml is not valid YAML ({e})") from e
    if not isinstance(data, dict):
        raise ValueError("projects.yml must contain a 'featured:' and/or a 'more:' list")
    for section in ("featured", "more"):
        items = data.get(section) or []
        if not isinstance(items, list):
            raise ValueError(f"projects.yml: '{section}' must be a list")
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"projects.yml: {section}[{i}] must be a block of 'key: value' lines")
            missing = [k for k in ("title", "url", "description") if not str(item.get(k) or "").strip()]
            if missing:
                raise ValueError(f"projects.yml: {section}[{i}] is missing {', '.join(missing)}")
            if not str(item["url"]).startswith("https://"):
                raise ValueError(f"projects.yml: {section}[{i}] url must start with https://")
        data[section] = items
    return data


def git_commit() -> str:
    sha = os.environ.get("GITHUB_SHA", "")
    if not sha:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""
    return sha[:7]


def asset_version() -> str:
    """Short content hash of the CSS + JS, so browsers fetch them again after every change."""
    h = hashlib.sha1()
    for name in ("site.css", "site.js"):
        f = STATIC / name
        if f.exists():
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def json_ld(data: dict) -> str:
    # <, > and & as JSON unicode escapes: nothing in the data can ever close or confuse the <script> element
    payload = (json.dumps(data, ensure_ascii=False, separators=(",", ":"))
               .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))
    return f'<script type="application/ld+json">{payload}</script>'


def person() -> dict:
    return {"@type": "Person", "name": AUTHOR, "jobTitle": ROLE, "url": SITE_URL + SITE_ROOT, "sameAs": SAME_AS}


def head_meta(*, canonical: str | None, og_type: str = "website", robots: str = "index,follow",
              ld: dict | None = None, post: Post | None = None, dark_chrome: bool = False) -> str:
    lines = [f'<meta name="robots" content="{robots}">', f'<meta property="og:type" content="{og_type}">']
    if canonical:
        lines += [f'<link rel="canonical" href="{esc(canonical)}">',
                  f'<meta property="og:url" content="{esc(canonical)}">']
    if post:
        lines += [f'<meta property="article:published_time" content="{post.date_iso}">',
                  f'<meta property="article:modified_time" content="{post.modified_iso}">',
                  f'<meta property="article:author" content="{esc(AUTHOR)}">',
                  f'<meta property="article:tag" content="{esc(post.tag)}">']
    if dark_chrome:  # the homepage always opens on the dark hero
        lines.append('<meta name="theme-color" content="#0E0E0F">')
    else:
        lines += ['<meta name="theme-color" content="#0E0E0F" media="(prefers-color-scheme: dark)">',
                  '<meta name="theme-color" content="#FBF8F1" media="(prefers-color-scheme: light)">']
    if ld:
        lines.append(json_ld(ld))
    return "\n  ".join(lines)


# ─────────────────────────────  FRAGMENTS  ─────────────────────────────


def result_html(p: Post, cls: str) -> str:
    """The optional measured result ("12 s → 4 s"), set like an instrument readout."""
    if not p.result:
        return ""
    value = '<span class="result-arrow">→</span>'.join(esc(part.strip()) for part in p.result.split("→"))
    # each "·" segment stays on one line, so "qwen3-coder:30b" never breaks at its hyphen
    segments = " · ".join(f'<span class="nowrap">{esc(s.strip())}</span>' for s in p.result_note.split("·"))
    note = f'<span class="result-note">{segments}</span>' if p.result_note else ""
    return (f'<div class="result {cls}"><span class="result-k">Measured</span>'
            f'<span class="result-v tabnum">{value}</span>{note}</div>')


def spectrum_scale(p: Post) -> str:
    """A calibrated 380–740 nm scale with the post's topic marked on it."""
    pos = (p.nm - 380) / 3.6
    majors = "".join(
        f'<span class="scale-major" style="left:{(v - 380) / 3.6:.2f}%"><span>{v}</span></span>'
        for v in (400, 500, 600, 700)
    )
    flip = " scale--flip" if pos > 55 else ""
    return (f'<div class="scale{flip}" style="--line: {p.line}; --pos: {pos:.2f}%" aria-hidden="true">'
            f'<span class="scale-ticks"></span>{majors}<span class="scale-marker"></span>'
            f'<span class="scale-readout">λ {p.nm} nm · <span class="scale-tag">{esc(p.tag)}</span></span></div>')


def render_writing_list(posts: list[Post]) -> str:
    """Editorial entry list: the newest post gets a larger lead-essay treatment."""
    if not posts:
        return '      <li class="entry entry--empty">No essays yet — the first is being drafted.</li>'

    rows: list[str] = []
    for i, p in enumerate(posts):
        cls = "entry entry--lead" if i == 0 else "entry"
        dek = f'\n            <p class="entry-dek">{esc(p.summary)}</p>' if p.summary else ""
        more = '\n            <span class="entry-readmore">Read essay <span class="arrow">→</span></span>' if i == 0 else ""
        rows.append(
            f'      <li class="{cls}" style="--line: {p.line}">\n'
            f'        <a href="{p.url_path}" class="entry-link">\n'
            f'          <p class="entry-meta">\n'
            f'            <span class="entry-issue">N° {len(posts) - i:02d}</span>\n'
            f'            <time class="tabnum" datetime="{p.date_iso}">{p.date_human}</time>\n'
            f'            <span class="entry-tag"><span class="emission" aria-hidden="true"></span>{esc(p.tag)}</span>\n'
            f'            <span class="tabnum">{p.reading_time} min<span class="hide-sm"> read</span></span>\n'
            f'          </p>\n'
            f'          <div class="entry-body">\n'
            f'            <h3 class="entry-title">{esc(p.title)}</h3>{dek}{more}\n'
            f'          </div>\n'
            f'          {result_html(p, "result--list")}\n'
            f'        </a>\n'
            f'      </li>'
        )
    return "\n".join(rows)


def inline_list(items: list) -> str:
    return "".join(f"<li>{esc(s)}</li>" for s in items or [])


def render_projects(data: dict) -> str:
    featured, more = data.get("featured") or [], data.get("more") or []
    n = max(1, len(featured) - 1)
    out: list[str] = []

    if featured:
        p = featured[0]
        highlights = "".join(
            f'<li><span class="spec-num tabnum">{k:02d}</span><span>{esc(h)}</span></li>'
            for k, h in enumerate(p.get("highlights") or [], 1)
        )
        facts = "".join(
            f'<div><dt>{label}</dt><dd>{esc(p[key])}</dd></div>'
            for label, key in (("Context", "context"), ("Year", "year")) if p.get(key)
        )
        out.append(
            f'<article class="flagship" style="--line: {spectrum_at(0)}">\n'
            f'  <a class="flagship-link" href="{esc(p["url"])}">\n'
            f'    <div class="flagship-main">\n'
            f'      <p class="card-kicker"><span class="emission" aria-hidden="true"></span>'
            f'<span class="tabnum">001</span><span class="card-kicker__label">{esc(p.get("kicker", "Flagship"))}</span></p>\n'
            f'      <h3 class="flagship-title">{esc(p["title"])}</h3>\n'
            f'      <p class="flagship-desc">{esc(p["description"])}</p>\n'
            f'      <ul class="tags" aria-label="Stack">{inline_list(p.get("stack"))}</ul>\n'
            f'      <span class="flagship-cta">View on GitHub <span class="arrow" aria-hidden="true">↗</span></span>\n'
            f'    </div>\n'
            f'    <div class="flagship-spec">\n'
            f'      <p class="spec-title">Spec sheet</p>\n'
            + (f'      <ul class="spec-list">{highlights}</ul>\n' if highlights else "")
            + (f'      <dl class="spec-facts">{facts}</dl>\n' if facts else "")
            + '    </div>\n'
            '  </a>\n'
            '</article>'
        )

    cards = []
    for i, p in enumerate(featured[1:], 1):
        year = f'<span class="card-year tabnum">{esc(p["year"])}</span>' if p.get("year") else ""
        cards.append(
            f'  <li class="card" style="--line: {spectrum_at(i / n)}">\n'
            f'    <a class="card-link" href="{esc(p["url"])}">\n'
            f'      <p class="card-kicker"><span class="emission" aria-hidden="true"></span>'
            f'<span class="tabnum">{i + 1:03d}</span><span class="card-kicker__label">{esc(p.get("kicker", "Project"))}</span>{year}</p>\n'
            f'      <h3 class="card-title">{esc(p["title"])} <span class="card-arrow" aria-hidden="true">↗</span></h3>\n'
            f'      <p class="card-desc">{esc(p["description"])}</p>\n'
            f'      <ul class="tags" aria-label="Stack">{inline_list(p.get("stack"))}</ul>\n'
            f'    </a>\n'
            f'  </li>'
        )
    if cards:
        out.append('<ul class="card-grid">\n' + "\n".join(cards) + "\n</ul>")

    if more:
        rows = "\n".join(
            f'    <li><a href="{esc(p["url"])}">'
            f'<span class="index-name">{esc(p["title"])}</span>'
            f'<span class="index-desc">{esc(p["description"])}</span>'
            f'<span class="index-stack">{esc(" · ".join(p.get("stack") or []))}</span>'
            f'<span class="index-year tabnum">{esc(p.get("year", ""))}</span>'
            f'<span class="index-arrow" aria-hidden="true">↗</span></a></li>'
            for p in more
        )
        out.append(
            '<div class="project-index">\n'
            '  <h3 class="project-index__title">More on GitHub</h3>\n'
            f'  <ul>\n{rows}\n  </ul>\n'
            '</div>'
        )
    return "\n".join(out)


def render_post_nav(newer: Post | None, older: Post | None) -> str:
    if not newer and not older:
        return ""

    def item(p: Post | None, label: str, cls: str) -> str:
        if not p:
            return f'<span class="post-nav__item post-nav__item--{cls} is-empty"></span>'
        return (f'<a class="post-nav__item post-nav__item--{cls}" href="{p.url_path}">'
                f'<span class="post-nav__label">{label}</span>'
                f'<span class="post-nav__title">{esc(p.title)}</span></a>')

    return ('<nav class="post-nav" aria-label="More essays">'
            + item(older, "← Older essay", "prev") + item(newer, "Newer essay →", "next")
            + "</nav>")


def render_feed(posts: list[Post]) -> str:
    """RSS 2.0 feed (full content)."""
    items = []
    for p in posts[:20]:
        items.append(
            f"  <item>\n"
            f"    <title>{xml_escape(p.title)}</title>\n"
            f"    <link>{p.url}</link>\n"
            f"    <guid isPermaLink=\"true\">{p.url}</guid>\n"
            f"    <pubDate>{format_datetime(p.date.replace(tzinfo=timezone.utc))}</pubDate>\n"
            f"    <category>{xml_escape(p.tag)}</category>\n"
            f"    <description>{xml_escape(p.summary)}</description>\n"
            f"    <content:encoded><![CDATA[{p.body_html.replace(']]>', ']]]]><![CDATA[>')}]]></content:encoded>\n"
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
        f'  <lastBuildDate>{format_datetime(datetime.now(timezone.utc))}</lastBuildDate>\n'
        f'  <atom:link href="{SITE_URL}{SITE_ROOT}feed.xml" rel="self" type="application/rss+xml"/>\n'
        + "\n".join(items)
        + "\n</channel>\n</rss>\n"
    )


def render_sitemap(posts: list[Post]) -> str:
    urls = [(SITE_URL + SITE_ROOT, max((p.modified_iso for p in posts), default=NOW.strftime("%Y-%m-%d")))]
    urls += [(p.url, p.modified_iso) for p in posts]
    body = "\n".join(f"  <url><loc>{xml_escape(u)}</loc><lastmod>{d}</lastmod></url>" for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + body + "\n</urlset>\n")


LIVE_RELOAD_JS = """<script>
  // preview only: reload when blog.py rebuilds the site
  (function () {
    var last = null;
    setInterval(function () {
      fetch('/__build_id', { cache: 'no-store' }).then(function (r) { return r.ok ? r.text() : null; })
        .then(function (id) { if (!id) return; if (last && id !== last) location.reload(); last = id; })
        .catch(function () {});
    }, 700);
  })();
</script>"""


# ─────────────────────────────  BUILD  ─────────────────────────────


def build(*, live_reload: bool = False) -> list[Post]:
    tpl = {name: (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
           for name in ("base", "index", "post", "404")}
    posts = load_posts()          # parse everything before touching dist/,
    projects = load_projects()    # so a typo never leaves you with a half-built site
    print(f"  • Loaded {len(posts)} post(s), {len(projects['featured']) + len(projects['more'])} project(s)")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    commit = git_commit()
    essays = f"{len(posts)} essay{'s' if len(posts) != 1 else ''}"
    common = {
        "ROOT": SITE_ROOT,
        "YEAR": str(NOW.year),
        "ASSET_V": asset_version(),
        "EMAIL": EMAIL,
        "REPO_URL": REPO_URL,
        "BUILD_INFO": (f'Built {human_date(NOW)} from <a href="{REPO_URL}/commit/{commit}">{commit}</a> · {essays}'
                       if commit else f"Built {human_date(NOW)} · {essays}"),
        "LIVE_RELOAD": LIVE_RELOAD_JS if live_reload else "",
    }
    og_image = f"{SITE_URL}{SITE_ROOT}og.jpg"

    def page(body: str, *, title: str, description: str, meta: str) -> str:
        return render_template(tpl["base"], {
            **common,
            "TITLE": esc(title),
            "DESCRIPTION": esc(description),
            "OG_IMAGE": og_image,
            "HEAD_META": meta,
            "CONTENT": body,
        })

    # 1. Post pages
    for i, p in enumerate(posts):
        newer = posts[i - 1] if i > 0 else None
        older = posts[i + 1] if i + 1 < len(posts) else None
        updated = (f'<span class="sep" aria-hidden="true">·</span><span>Updated '
                   f'<time datetime="{p.modified_iso}">{human_date(p.updated)}</time></span>' if p.updated else "")
        body = render_template(tpl["post"], {
            **common,
            "ISSUE": f"N° {len(posts) - i:02d}",
            "POST_TITLE": esc(p.title),
            "POST_TITLE_URL": quote(f"Re: {p.title}"),
            "DATE_ISO": p.date_iso,
            "DATE_HUMAN": p.date_human,
            "UPDATED": updated,
            "TAG": esc(p.tag),
            "READING_TIME": str(p.reading_time),
            "SUMMARY_BLOCK": f'<p class="post-dek reveal" style="--d:3">{esc(p.summary)}</p>' if p.summary else "",
            "RESULT": result_html(p, "result--post reveal"),
            "SCALE": spectrum_scale(p),
            "LINE": p.line,
            "POST_CONTENT": p.body_html,
            "POST_NAV": render_post_nav(newer, older),
        })
        ld = {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": p.title,
            "description": p.summary or SITE_DESCRIPTION,
            "datePublished": p.date_iso,
            "dateModified": p.modified_iso,
            "author": person(),
            "publisher": person(),
            "url": p.url,
            "mainEntityOfPage": p.url,
            "image": og_image,
            "keywords": p.tag,
            "wordCount": p.word_count,
            "inLanguage": "en",
        }
        out_dir = DIST / "posts" / p.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(page(
            body,
            title=f"{p.title} — {AUTHOR}",
            description=p.summary or SITE_DESCRIPTION,
            meta=head_meta(canonical=p.url, og_type="article", ld=ld, post=p),
        ), encoding="utf-8")
        print(f"  • {p.slug}  →  posts/{p.slug}/")

    # 2. Homepage
    index_body = render_template(tpl["index"], {
        **common,
        "WRITING_LIST": render_writing_list(posts),
        "PROJECTS": render_projects(projects),
    })
    home_ld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_TITLE,
        "url": SITE_URL + SITE_ROOT,
        "description": SITE_DESCRIPTION,
        "inLanguage": "en",
        "author": person(),
    }
    (DIST / "index.html").write_text(page(
        index_body, title=SITE_TITLE, description=SITE_DESCRIPTION,
        meta=head_meta(canonical=SITE_URL + SITE_ROOT, ld=home_ld, dark_chrome=True),
    ), encoding="utf-8")
    print("  • index.html")

    # 3. 404 (GitHub Pages serves it for any unknown path, so all links are root-absolute)
    latest = (f'<a class="text-link" href="{posts[0].url_path}">Latest essay: {esc(posts[0].title)} →</a>'
              if posts else "")
    (DIST / "404.html").write_text(page(
        render_template(tpl["404"], {**common, "LATEST": latest}),
        title=f"Page not found — {AUTHOR}", description=SITE_DESCRIPTION,
        meta=head_meta(canonical=None, robots="noindex"),
    ), encoding="utf-8")

    # 4. Feed, sitemap, robots
    (DIST / "feed.xml").write_text(render_feed(posts), encoding="utf-8")
    (DIST / "sitemap.xml").write_text(render_sitemap(posts), encoding="utf-8")
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}{SITE_ROOT}sitemap.xml\n", encoding="utf-8")
    print("  • 404.html, feed.xml, sitemap.xml, robots.txt")

    # 5. Static files (CSS, JS, icons, images, CNAME)
    if STATIC.exists():
        shutil.copytree(STATIC, DIST, dirs_exist_ok=True)
        print("  • static/ → dist/")

    # 6. .nojekyll so GitHub Pages serves the output as-is
    (DIST / ".nojekyll").write_text("", encoding="utf-8")
    if live_reload:
        (DIST / "__build_id").write_text(str(datetime.now().timestamp()), encoding="utf-8")

    print(f"\nBuilt site → {DIST}")
    return posts


if __name__ == "__main__":
    print("Building site...")
    try:
        build()
    except Exception as e:
        print(f"\nBuild failed: {e}", file=sys.stderr)
        sys.exit(1)
