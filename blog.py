#!/usr/bin/env python3
"""
Write and publish posts for roglia.ro — three commands:

    python3 blog.py new "My post title"   create posts/YYYY-MM-DD-my-post-title.md
    python3 blog.py preview               show the site at http://localhost:8000, refreshing on every save
    python3 blog.py publish               check, build, commit and push → live in about a minute

The first run sets up .venv/ and installs requirements.txt by itself. See README.md.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import importlib
import io
import os
import re
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "posts"
VENV = ROOT / ".venv"
VENV_PYTHON = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
SITE = "https://roglia.ro"
ACTIONS = "https://github.com/tonyc973/chirilus-site/actions"
CONTENT = ["posts", "static", "projects.yml"]  # what `publish` commits — never code or templates

# Text from the new-post template; `publish` refuses a post that still contains it.
BODY_PLACEHOLDER = "Write the post here."
SUMMARY_PLACEHOLDER = "One or two sentences that make people want to read it."
TEMPLATE = """---
title: "{title}"
date: {date}
tag: Notes  # one topic, e.g. Inference, Agents, Evals, Retrieval, Observability, Platform, Security
summary: "{summary}"
# result: "12 s → 4 s"               # optional: the one number that changed, shown like an instrument readout
# result_note: "per turn · RTX 5090"  # optional: what was measured
---

{body} The first paragraph gets a drop cap. Use ## for section headings
(the title above is already the page heading).
"""


# ─────────────────────────────  setup  ─────────────────────────────


def ensure_deps() -> None:
    """Run inside .venv (creating it and installing requirements on first use), so plain `python3 blog.py` works."""
    try:
        import frontmatter, markdown, pygments, yaml  # noqa: F401,E401
        return
    except ImportError:
        pass
    hops = int(os.environ.get("BLOG_PY_HOPS", "0"))
    if hops >= 2:
        sys.exit("Could not set up the Python packages automatically.\n"
                 "Run:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt")
    os.environ["BLOG_PY_HOPS"] = str(hops + 1)
    me = str(Path(__file__).resolve())
    if Path(sys.prefix).resolve() != VENV.resolve():
        if not VENV_PYTHON.exists():
            print("First run: creating .venv/ …")
            subprocess.run([sys.executable, "-m", "venv", "--clear", str(VENV)], check=True)
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), me, *sys.argv[1:]])
    print("Installing the packages from requirements.txt (one time) …")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)
    os.execv(sys.executable, [sys.executable, me, *sys.argv[1:]])


def load_build():
    sys.path.insert(0, str(ROOT))
    import build
    return build


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed:\n{r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


# ─────────────────────────────  new  ─────────────────────────────


def slugify(title: str) -> str:
    """'Cum am făcut ș și ț — 3× mai rapid' → 'cum-am-facut-s-si-t-3-mai-rapid' (max 60 chars)."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    if len(slug) > 60:
        slug = slug[:60].rsplit("-", 1)[0]
    return slug


def cmd_new(args: list[str]) -> None:
    title = " ".join(args).strip()
    if not title:
        sys.exit('Usage: python3 blog.py new "My post title"')
    slug = slugify(title)
    if not slug:
        sys.exit("The title needs at least one letter or digit (it becomes the URL).")
    clash = [p for p in POSTS.glob("*.md") if re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem) == slug]
    if clash:
        sys.exit(f"{rel(clash[0])} already uses the URL /posts/{slug}/ — pick another title or edit that file.")
    today = date.today().isoformat()
    path = POSTS / f"{today}-{slug}.md"
    yaml_title = title.replace("\\", "\\\\").replace('"', '\\"')
    path.write_text(TEMPLATE.format(title=yaml_title, date=today, summary=SUMMARY_PLACEHOLDER,
                                    body=BODY_PLACEHOLDER), encoding="utf-8")
    print(f"Created {rel(path)}  →  will live at {SITE}/posts/{slug}/\n")
    print("Next:")
    print(f"  1. Open {rel(path)} and write (Markdown). Replace the summary line too.")
    print("  2. python3 blog.py preview    see it at http://localhost:8000 while you write")
    print("  3. python3 blog.py publish    put it online")


# ─────────────────────────────  preview  ─────────────────────────────


def cmd_preview(args: list[str]) -> None:
    ensure_deps()
    build = load_build()
    watched = [build.POSTS, build.TEMPLATES, build.STATIC, build.PROJECTS_FILE, ROOT / "build.py"]

    def snapshot() -> dict[str, float]:
        files: list[Path] = []
        for w in watched:
            if w.is_dir():
                files += [f for f in w.rglob("*") if f.is_file()]
            elif w.exists():
                files.append(w)
        return {str(f): f.stat().st_mtime for f in files}

    def rebuild() -> bool:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                posts = build.build(live_reload=True)
        except Exception as e:  # keep serving the last good build; show the error
            print(f"  ✗ {time.strftime('%H:%M:%S')}  build failed: {e}")
            return False
        warnings = [line.strip() for line in out.getvalue().splitlines() if line.strip().startswith("!")]
        print(f"  ✓ {time.strftime('%H:%M:%S')}  built {len(posts)} post(s)")
        for w in warnings:
            print(f"    {w}")
        return True

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")  # always show the latest build
            super().end_headers()

        def send_error(self, code, message=None, explain=None):
            page = build.DIST / "404.html"
            if code == 404 and page.exists():  # same behaviour as GitHub Pages
                body = page.read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().send_error(code, message, explain)

    if not rebuild():
        print("  Fix the error above; the preview rebuilds as soon as you save.")
    handler = functools.partial(Handler, directory=str(build.DIST))
    server = None
    for port in range(8000, 8020):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("Ports 8000–8019 are all busy — close another preview first.")
    url = f"http://localhost:{server.server_address[1]}/"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\n  Preview: {url}   (rebuilds and refreshes on every save · Ctrl+C to stop)\n")
    if "--no-open" not in args:
        webbrowser.open(url)

    seen = snapshot()
    try:
        while True:
            time.sleep(0.5)
            now = snapshot()
            if now != seen:
                if now.get(str(ROOT / "build.py")) != seen.get(str(ROOT / "build.py")):
                    build = importlib.reload(build)
                seen = now
                rebuild()
    except KeyboardInterrupt:
        print("\n  Preview stopped.")
    finally:
        server.shutdown()


# ─────────────────────────────  publish  ─────────────────────────────


def cmd_publish(args: list[str]) -> None:
    ensure_deps()
    build = load_build()
    import frontmatter

    branch = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != "main":
        sys.exit(f"You're on branch '{branch}'. The site deploys from 'main' — run: git switch main")

    print("Checking the site builds …")
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            build.build()
    except Exception as e:
        sys.exit(f"✗ Not published — the build failed: {e}")
    for line in out.getvalue().splitlines():
        if line.strip().startswith("!"):
            print(f"  {line.strip()}")

    changes: list[tuple[str, str]] = []
    for line in git("status", "--porcelain", "--untracked-files=all", "--", *CONTENT).splitlines():
        for path in line[3:].split(" -> "):  # a rename lists "old -> new"
            changes.append((line[:2], path.strip().strip('"')))
    if not changes:
        print("Nothing new to publish: posts/, static/ and projects.yml match what's online.")
        return

    new_posts, edited_posts = [], []
    for code, path in changes:
        if path.startswith("posts/") and path.endswith(".md") and (ROOT / path).exists():
            text = (ROOT / path).read_text(encoding="utf-8")
            if BODY_PLACEHOLDER in text or SUMMARY_PLACEHOLDER in text:
                sys.exit(f"✗ Not published — {path} still has the template text "
                         f"(“{BODY_PLACEHOLDER}” or the placeholder summary).")
            title = str(frontmatter.loads(text).get("title", path))
            (new_posts if code in ("??", "A ") else edited_posts).append(title)

    print("\nThese changes will go live:")
    for code, path in changes:
        label = {"??": "new", "A ": "new", " D": "deleted", "D ": "deleted"}.get(code, "changed")
        print(f"  {label:8} {path}")
    if "-y" not in args and "--yes" not in args:
        if input("\nPublish? [y/N] ").strip().lower() not in ("y", "yes", "d", "da"):
            print("Nothing published.")
            return

    if len(new_posts) == 1 and not edited_posts:
        message = f"post: {new_posts[0]}"
    elif len(edited_posts) == 1 and not new_posts:
        message = f"post: update “{edited_posts[0]}”"
    else:
        message = f"content: update {len(changes)} file(s)"
    paths = sorted({path for _, path in changes})
    git("add", "-A", "--", *paths)
    git("commit", "-m", message, "--", *paths)  # only these paths, even if other files are staged
    print(f"Committed: {message}")
    push = subprocess.run(["git", "push"], cwd=ROOT, capture_output=True, text=True)
    if push.returncode != 0:
        print(push.stderr.strip())
        sys.exit("\n✗ Committed locally but the push failed. If it says 'rejected' or 'fetch first', run:\n"
                 "    git pull --rebase && git push")
    print(f"\n✓ Pushed. The site rebuilds now and is live in about a minute: {SITE}/")
    print(f"  Watch the deploy: {ACTIONS}")


# ─────────────────────────────  main  ─────────────────────────────

COMMANDS = {"new": cmd_new, "preview": cmd_preview, "publish": cmd_publish}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print((__doc__ or "").strip())
        sys.exit(0 if len(sys.argv) < 2 else 1)
    try:
        COMMANDS[sys.argv[1]](sys.argv[2:])
    except RuntimeError as e:
        sys.exit(f"✗ {e}")
