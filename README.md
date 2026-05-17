# chirilus.dev

Personal site + blog for Antonie Chirilus.

## Posting a new entry

1. Create a Markdown file in `posts/` named `YYYY-MM-DD-slug.md`:

   ```markdown
   ---
   title: "The title of the post"
   date: 2026-05-17
   tag: Inference
   summary: "One sentence shown in the writing list and the post header."
   ---

   Markdown body. Fenced code blocks get syntax-highlighted automatically.
   ```

2. Commit and push:

   ```bash
   git add posts/2026-05-17-my-post.md
   git commit -m "post: my post"
   git push
   ```

3. GitHub Actions builds the site and publishes it. Done.

## Local preview

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python build.py
python -m http.server 8000 --directory dist
```

Open <http://localhost:8000>.

## Layout

```
.
├── build.py                # static site generator
├── requirements.txt
├── templates/
│   ├── base.html           # shared head, nav, footer
│   ├── index.html          # homepage body
│   └── post.html           # single-post body
├── posts/                  # Markdown posts (this is what you edit)
├── static/                 # optional: images, files served from /
├── .github/workflows/
│   └── deploy.yml          # GH Pages auto-deploy on push to main
└── dist/                   # build output (gitignored)
```

## Frontmatter fields

| Field      | Required | Notes                                                      |
| ---------- | -------- | ---------------------------------------------------------- |
| `title`    | yes      | Post title.                                                |
| `date`     | yes      | `YYYY-MM-DD`.                                              |
| `tag`      | no       | Single category shown in the writing list (default `Notes`). |
| `summary`  | no       | One-sentence description used on the post header and RSS. |
| `slug`     | no       | URL slug; defaults to filename minus the date prefix.      |

## Configuring the site URL

GH Pages on a project domain (`<user>.github.io/<repo>/`) needs the build to know
its URL prefix. The deploy workflow sets `SITE_ROOT` and `SITE_URL` automatically.
For local builds, defaults (`/`, `https://chirilus.dev`) are fine.

To switch to a custom domain later, edit `.github/workflows/deploy.yml`:
set `SITE_ROOT=/` and `SITE_URL=https://yourdomain.com`, and add a `CNAME` file
to `static/`.

## Editing the homepage (work, experience, contact)

Edit `templates/index.html` directly. Everything except the Writing list (which is
generated from `posts/`) lives there.
