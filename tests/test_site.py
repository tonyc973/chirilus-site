"""Smoke tests for the site generator and the posting tool. Run: python -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import blog  # noqa: E402
import build  # noqa: E402


class Helpers(unittest.TestCase):
    def test_slugify_handles_diacritics_symbols_and_length(self):
        self.assertEqual(blog.slugify("Cum am făcut ș și ț — 3× mai rapid"), "cum-am-facut-s-si-t-3-mai-rapid")
        self.assertEqual(blog.slugify("!!!"), "")
        self.assertLessEqual(len(blog.slugify("word " * 40)), 60)

    def test_smarten_curls_quotes(self):
        self.assertEqual(build.smarten('It wasn\'t "fast"...'), "It wasn’t “fast”…")

    def test_dates(self):
        self.assertEqual(build.to_datetime("2026-05-17", "x").day, 17)
        self.assertIsNone(build.to_datetime("2026-05-17T10:00:00+03:00", "x").tzinfo)
        with self.assertRaises(ValueError):
            build.to_datetime("17/05/2026", "x")


class Build(unittest.TestCase):
    def build_into(self, posts_dir: Path, dist: Path):
        saved = build.POSTS, build.DIST
        build.POSTS, build.DIST = posts_dir, dist
        try:
            return build.build()
        finally:
            build.POSTS, build.DIST = saved

    def test_real_site_builds_without_leftover_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            posts = self.build_into(build.POSTS, Path(tmp) / "dist")
            self.assertTrue(posts)
            pages = [Path(tmp) / "dist/index.html", Path(tmp) / "dist/404.html",
                     *(Path(tmp) / "dist/posts").glob("*/index.html")]
            self.assertEqual(len(pages), len(posts) + 2)
            for page in pages:
                self.assertNotRegex(page.read_text(encoding="utf-8"), r"\{\{[A-Z_]+\}\}", page)

    def test_hostile_frontmatter_is_escaped(self):
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            posts.mkdir()
            (posts / "2026-01-02-x.md").write_text(
                '---\ntitle: "<script>alert(1)</script> & \\"q\\""\ndate: 2026-01-02\n'
                'summary: "a <b> \\"c\\""\n---\nBody.\n', encoding="utf-8")
            self.build_into(posts, Path(tmp) / "dist")
            html = (Path(tmp) / "dist/posts/x/index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert", html)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; “q”", html)
            self.assertIn('content="a &lt;b&gt; “c”"', html)

    def test_duplicate_slugs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            posts = Path(tmp) / "posts"
            posts.mkdir()
            for day in ("01", "02"):
                (posts / f"2026-01-{day}-same.md").write_text(f"---\ntitle: T\ndate: 2026-01-{day}\n---\nx\n")
            with self.assertRaisesRegex(ValueError, "share the URL slug"):
                self.build_into(posts, Path(tmp) / "dist")


if __name__ == "__main__":
    unittest.main()
