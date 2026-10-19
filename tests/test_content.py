import tempfile
import unittest
from pathlib import Path

from admin import content
from admin.config import settings

class TestContent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        settings.content_root = self.root / "content"
        settings.config_root = self.root / "config"
        (settings.content_root / "posts").mkdir(parents=True)
        settings.config_root.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_path_escape_rejected(self):
        with self.assertRaises(ValueError):
            content.safe_resolve(self.root, "../secret")

    def test_write_read_roundtrip(self):
        content.write_markdown(
            "posts",
            "hello-world",
            {"title": "你好", "date": "2026-08-18", "tags": ["Hugo"]},
            "正文内容",
        )
        fm, body = content.read_markdown("posts", "hello-world")
        self.assertEqual(fm["title"], "你好")
        self.assertIn("正文内容", body)

    def test_bad_slug_rejected(self):
        with self.assertRaises(ValueError):
            content.write_markdown("posts", "../evil", {"title": "x"}, "y")

    def test_yaml_save_load(self):
        content.save_yaml("brand", {"name": "Li&Blog", "icp": ""})
        self.assertEqual(content.load_yaml("brand")["name"], "Li&Blog")

    def test_remove_image_references(self):
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text(
            "---\ntitle: Hello\n---\n\n"
            "![图一](/img/2026/08/a.png)\n\n"
            '![](/img/2026/08/a.png "标题")\n\n'
            '<img src="/img/2026/08/a.png" alt="x">\n\n'
            '{{< figure src="/img/2026/08/a.png" caption="x" >}}\n\n'
            "![保留](/img/2026/08/b.png)\n",
            encoding="utf-8",
        )
        changed = content.remove_image_references("2026/08/a.png")
        self.assertEqual(changed, ["posts/hello.md"])
        text = post.read_text(encoding="utf-8")
        self.assertNotIn("a.png", text)
        self.assertIn("b.png", text)

    def test_remove_image_references_keeps_unrelated_files(self):
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text("正文![图](/img/2026/08/b.png)\n", encoding="utf-8")
        self.assertEqual(content.remove_image_references("2026/08/a.png"), [])
        self.assertIn("b.png", post.read_text(encoding="utf-8"))

    def test_remove_image_references_clears_frontmatter(self):
        post = self.root / "content" / "posts" / "hello.md"
        post.write_text(
            "---\ntitle: Hello\ncover: /img/2026/08/a.png\n---\n\n正文保留\n",
            encoding="utf-8",
        )
        changed = content.remove_image_references("2026/08/a.png")
        self.assertEqual(changed, ["posts/hello.md"])
        text = post.read_text(encoding="utf-8")
        self.assertIn("cover: ''", text)
        self.assertIn("正文保留", text)

    def test_clear_config_image_refs(self):
        (self.root / "config" / "brand.yaml").write_text(
            "name: Li&Blog\n"
            "logo: /img/2026/08/a.png\n"
            "favicon: /img/2026/08/a.png\n"
            "icp_icon: /img/2026/08/b.png\n"
            "theme_key: liblog-theme\n",
            encoding="utf-8",
        )
        changed = content.clear_config_image_refs("2026/08/a.png")
        self.assertEqual(changed, ["brand.yaml"])
        data = content.load_yaml("brand")
        self.assertEqual(data["logo"], "")
        self.assertEqual(data["favicon"], "")
        self.assertEqual(data["icp_icon"], "/img/2026/08/b.png")
        self.assertEqual(data["theme_key"], "liblog-theme")

    def test_list_markdown_filter(self):
        content.write_markdown(
            "posts",
            "hello",
            {"title": "Hello Hugo", "date": "2026-08-18", "status": "published", "tags": ["hugo"]},
            "正文",
        )
        content.write_markdown(
            "posts",
            "draft-note",
            {"title": "未完成草稿", "date": "2026-08-18", "status": "draft", "tags": []},
            "正文",
        )
        self.assertEqual(len(content.list_markdown("posts", q="hugo")), 1)
        self.assertEqual(len(content.list_markdown("posts", q="不存在")), 0)

    def test_list_markdown_sort(self):
        content.write_markdown(
            "posts",
            "b",
            {"title": "Beta", "date": "2026-08-20", "status": "published"},
            "正文",
        )
        content.write_markdown(
            "posts",
            "a",
            {"title": "Alpha", "date": "2026-08-10", "status": "draft"},
            "正文",
        )
        asc = content.list_markdown("posts", sort="title", order="asc")
        desc = content.list_markdown("posts", sort="date", order="desc")
        self.assertEqual([i["slug"] for i in asc], ["a", "b"])
        self.assertEqual([i["slug"] for i in desc], ["b", "a"])

    def test_list_markdown_skips_index(self):
        (self.root / "content" / "posts" / "_index.md").write_text(
            "---\ntitle: 文章\n---\n", encoding="utf-8"
        )
        content.write_markdown(
            "posts",
            "real-post",
            {"title": "真实文章", "date": "2026-08-18"},
            "正文",
        )
        slugs = [i["slug"] for i in content.list_markdown("posts")]
        self.assertNotIn("_index", slugs)
        self.assertIn("real-post", slugs)

    def test_list_markdown_includes_pinned(self):
        content.write_markdown(
            "posts", "pinned-post",
            {"title": "置顶", "date": "2026-08-18", "pinned": True},
            "正文",
        )
        content.write_markdown(
            "posts", "normal-post",
            {"title": "普通", "date": "2026-08-18"},
            "正文",
        )
        by_slug = {i["slug"]: i for i in content.list_markdown("posts")}
        self.assertTrue(by_slug["pinned-post"]["pinned"])
        self.assertFalse(by_slug["normal-post"]["pinned"])

    def test_normalize_friend_url_accepts_http_https(self):
        self.assertEqual(
            content.normalize_friend_url("  https://example.com/blog?q=1  "),
            "https://example.com/blog?q=1",
        )
        self.assertEqual(
            content.normalize_friend_url("http://example.com/"),
            "http://example.com/",
        )

    def test_normalize_friend_url_rejects_unsafe(self):
        for bad in ("", "javascript:alert(1)", "ftp://example.com", "https://", "https://u:p@example.com", "https://example.com/a b", "https://example.com/\"><script>"):
            with self.assertRaises(ValueError):
                content.normalize_friend_url(bad)

    def test_list_markdown_includes_friend_fields(self):
        content.write_markdown(
            "friends",
            "example",
            {
                "title": "示例站",
                "href": "https://example.com/",
                "description": "一个示例站点",
                "weight": 2,
            },
            "",
        )
        content.write_markdown(
            "friends",
            "another",
            {
                "title": "另一个",
                "href": "https://another.example/",
                "description": "另一个站点",
                "weight": 1,
            },
            "",
        )
        items = content.list_markdown("friends", sort="weight", order="asc")
        self.assertEqual([i["slug"] for i in items], ["another", "example"])
        self.assertTrue(content.list_markdown("friends", q="another.example"))
        self.assertTrue(content.list_markdown("friends", q="示例站点"))

    def test_sanitize_inline_svg_removes_script_and_events(self):
        safe = '<svg viewBox="0 0 24 24"><path d="M0 0"/></svg>'
        self.assertEqual(content.sanitize_inline_svg(safe), safe)
        evil = '<svg onload="alert(1)"><script>alert(2)</script></svg>'
        cleaned = content.sanitize_inline_svg(evil)
        self.assertNotIn("onload", cleaned)
        self.assertNotIn("<script", cleaned)
        self.assertEqual(content.sanitize_inline_svg("<svg onclick=x>"), "")
        self.assertEqual(content.sanitize_inline_svg("/img/icon.svg"), "/img/icon.svg")

if __name__ == "__main__":
    unittest.main()
