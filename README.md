# roglia.ro

Personal site and blog of Antonie Chirilus — live at **<https://roglia.ro>**.

A small Python script (`build.py`) turns Markdown posts into a static site. Every push to `main`
triggers GitHub Actions, which builds it and publishes it on GitHub Pages. No framework, no database.

---

## Publish a post in 3 commands

```bash
python3 blog.py new "Why my GPU sat at 66%"   # 1. creates posts/2026-10-16-why-my-gpu-sat-at-66.md
python3 blog.py preview                        # 2. opens http://localhost:8000 — refreshes every time you save
python3 blog.py publish                        # 3. checks, commits and pushes — live in about a minute
```

That's the whole workflow:

1. **`new`** creates the post file with today's date and a ready-to-fill header.
2. Open the file in any editor and write in Markdown. Replace the placeholder `summary`.
3. **`preview`** shows the real site on your machine. Leave it running while you write; the page
   reloads on every save. If something is wrong (say, a typo in the header), the terminal tells you
   which file and why, and the page keeps showing the last version that worked. Stop it with `Ctrl+C`.
4. **`publish`** builds the site to make sure nothing is broken, lists what will go live, asks
   `Publish? [y/N]`, then commits and pushes. Follow the deploy at
   <https://github.com/tonyc973/chirilus-site/actions>; the post is at `https://roglia.ro/posts/<slug>/`.

The first time you run `preview` or `publish`, `blog.py` creates `.venv/` and installs the three
dependencies itself. You never need to activate a virtualenv.

> `publish` only ever commits **content**: `posts/`, `static/` and `projects.yml`. Anything else stays
> out of the commit, even if you staged it. It refuses to publish a post that still contains the
> template text. Changes to templates, CSS or `build.py` are committed the usual way (`git commit` + `git push`).

---

## Writing a post

### The header (frontmatter)

Every post starts with a block between `---` lines. `blog.py new` writes it for you:

```markdown
---
title: "Why my GPU sat at 66%"
date: 2026-10-16
tag: Inference
summary: "One or two sentences that make people want to read it."
result: "12 s → 4 s"                 # optional
result_note: "per turn · RTX 5090"   # optional
---
```

| Field         | Required | What it does |
| ------------- | -------- | ------------ |
| `title`       | yes      | The post title. Quotes and apostrophes are turned into curly ones automatically. |
| `date`        | yes      | `YYYY-MM-DD`. Posts are sorted by it; the newest is the lead essay on the homepage. |
| `summary`     | strongly recommended | 1–2 sentences. Shown on the homepage, under the title, in link previews (LinkedIn, X, Slack), in search results and in RSS. |
| `tag`         | no       | One topic (default `Notes`). Each topic gets its own wavelength on the 380–740 nm scale and colour, e.g. Meta 405 nm, Agents 450, Retrieval 475, Observability 490, Evals 520, Reliability 545, Platform 570, Systems 585, Security 600, Inference 620. Any other word works too and gets a stable colour of its own. |
| `result`      | no       | The one measured number that changed, e.g. `"12 s → 4 s"` or `"46 GB → 22 GB"`. Shown big, like an instrument readout, on the homepage and the post. Use `→` between before and after. |
| `result_note` | no       | What was measured, e.g. `"per turn · qwen3-coder:30b · RTX 5090"`. Separate parts with `·`. |
| `updated`     | no       | `YYYY-MM-DD` of a meaningful revision. Shows "Updated …" next to the date and tells search engines. |
| `slug`        | no       | Custom URL: `slug: my-url` → `/posts/my-url/`. Default: the file name without the date. Only `a-z`, `0-9` and `-`. |

Lines starting with `#` inside the header are comments and are ignored.

### The body — Markdown cheat sheet

````markdown
Plain paragraphs. **Bold**, *italic*, `inline code`, [a link](https://example.com).

## A section heading          ← use ## and ###; the title is already the page's main heading

- a list item
1. a numbered item

> A quote — rendered as a pull quote.

```python                     ← fenced code with a language gets syntax colours and a Copy button
print("hello")
```

| Column | Another |           ← tables scroll sideways on phones
| ------ | ------- |
| a      | b       |

A claim that needs a source.[^1]

[^1]: The footnote text, collected at the end of the post.

![What the image shows](/images/gpu-utilisation.png)
````

### Images

Put image files in `static/images/` and reference them as `/images/<name>`. They are lazy-loaded.
Keep them under ~500 KB (export PNG screenshots at 2× and compress, or use JPEG/WebP for photos),
and always write a real description in the `[alt text]`.

### What the template already does — don't add these yourself

The title block, date, topic and reading time; the drop cap on the first paragraph; the sign-off
"— Antonie."; the author box with *Reply by email*; links to the previous and next essay; the
reading-progress bar; the share image; the RSS entry; and the sitemap entry.

---

## Editing the projects (`projects.yml`)

The **Selected work** section of the homepage is generated from `projects.yml`:

```yaml
featured:                  # the first one is the flagship (big card with the spec sheet)
  - title: CVEScope
    url: https://github.com/tonyc973/cvescope
    kicker: Security · Retrieval      # 1–3 word category
    year: 2026
    context: Master's project · University of Bucharest   # optional
    description: One or two sentences — what it does and the most interesting idea.
    highlights: [Hybrid BM25 + dense + RRF, ...]           # optional, flagship only
    stack: [Python, FAISS, ...]
more:                      # the compact "More on GitHub" list underneath
  - title: neetcode-gpt
    url: https://github.com/tonyc973/neetcode-gpt
    description: One line.
    stack: [Python, PyTorch]
    year: 2026
```

Order in the file = order on the page. `title`, `url` and `description` are required; the build
stops with a clear message if one is missing. Publish with `python3 blog.py publish`.

## Editing the rest of the homepage

- Hero, Experience and Contact: `templates/index.html`.
- Name, role, SEO/RSS description and email: the constants at the top of `build.py`
  (`AUTHOR`, `ROLE`, `SITE_TITLE`, `SITE_DESCRIPTION`, `EMAIL`).
- Colours, type and layout: `static/site.css` (the theme tokens are at the top).

---

## How it works

```
.
├── blog.py              # new / preview / publish — the only command you need day to day
├── build.py             # the static site generator (Markdown → HTML, RSS, sitemap, 404)
├── projects.yml         # Selected work on the homepage
├── posts/               # one Markdown file per essay
├── templates/
│   ├── base.html        # <head>, nav, footer — shared by every page
│   ├── index.html       # homepage: hero, essays, projects, experience, contact
│   ├── post.html        # one essay
│   └── 404.html         # "Nothing at this wavelength."
├── static/              # copied as-is into the site root
│   ├── site.css  site.js
│   ├── favicon.svg  favicon-32.png  apple-touch-icon.png
│   ├── og.jpg           # share image for LinkedIn / X / Slack previews
│   ├── images/          # images used in posts
│   └── CNAME            # tells GitHub Pages the domain is roglia.ro
├── .github/workflows/deploy.yml   # build + deploy on every push to main
└── dist/                # build output (not committed)
```

`python build.py` writes `dist/`: a page per post (`dist/posts/<slug>/index.html`), the homepage,
`404.html`, `feed.xml` (RSS), `sitemap.xml` and `robots.txt`. It refuses to build on mistakes like a
missing title, an invalid date, two posts with the same URL or an incomplete project entry — and it
checks all posts before deleting the previous `dist/`.

### Hosting and domain

- **GitHub Pages** must stay in *GitHub Actions* mode (Settings → Pages → Source: GitHub Actions).
  If the site ever shows a GitHub 404, check that first:
  `gh api repos/tonyc973/chirilus-site/pages --jq .build_type` must print `workflow`; fix it with
  `gh api -X PUT repos/tonyc973/chirilus-site/pages -f build_type=workflow` and re-run the deploy.
- **DNS** for roglia.ro lives at **Cloudflare** (not at the registrar): four `A` records for `@`
  (185.199.108.153, .109.153, .110.153, .111.153) and `CNAME www → tonyc973.github.io`, all
  "DNS only" (grey cloud). HTTPS is enforced in the Pages settings.
- The footer shows which commit is live ("Built … from a1b2c3d"), so you can confirm a deploy landed.

### Email: hello@roglia.ro

Mail to `hello@roglia.ro` only arrives once **Cloudflare Email Routing** is on (free):
Cloudflare dashboard → roglia.ro → **Email** → **Email Routing** → *Get started* → create the custom
address `hello` → destination: your personal inbox → confirm the verification email → let Cloudflare
add the MX and SPF records it proposes. The GitHub Pages records are not affected. Test by sending a
mail to hello@roglia.ro from another account.

---

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `Build failed: <file>: …` | The message names the file and the problem (missing `title`, a date like `2026-13-45`, an unclosed `"` in the header…). Fix it and save; `preview` rebuilds by itself. |
| `publish` says the push was rejected | Someone (or the GitHub web UI) changed the repo. Run `git pull --rebase && git push`. |
| A change isn't visible online | Wait for the green tick in Actions, then hard-refresh (`Ctrl+Shift+R`); GitHub Pages caches pages for up to 10 minutes. |
| Port 8000 is busy | `preview` automatically takes the next free port (8001, 8002, …) and prints it. |
| Link previews show an old title/image | LinkedIn caches previews: paste the URL into <https://www.linkedin.com/post-inspector/> to refresh it. |

Local build without `blog.py`: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python build.py`.
