import io
import os
import re
import tempfile
import types
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

os.environ.setdefault("LIBLOG_BOOTSTRAP_BUILD", "0")

from admin import content as store, media, security
from admin.config import settings
from admin.db import connect, create_admin, init_db
from admin.main import app, build, rewrite_preview_html, safe_stats_href

class AdminRoutesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        settings.db_path = root / "blog.db"
        settings.content_root = root / "content"
        settings.config_root = root / "config"
        settings.output_root = root / "output"
        settings.preview_root = root / "preview"
        settings.beacon_log = root / "beacon.log"
        settings.ip_whitelist = []
        media.MEDIA_ROOT = root / "img"
        (settings.content_root / "posts").mkdir(parents=True)
        (settings.content_root / "projects").mkdir(parents=True)
        settings.config_root.mkdir(parents=True)
        settings.preview_root.mkdir(parents=True)
        media.MEDIA_ROOT.mkdir(parents=True)
        (settings.config_root / "brand.yaml").write_text(
            "name: Audit\nlogo: ''\n", encoding="utf-8"
        )
        init_db()
        conn = connect()
        create_admin(conn, "admin", security.hash_password("Li&Blog@2026"))
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def _login(self, client: TestClient) -> str:
        r = client.get("/admin/login")
        csrf0 = re.search(r'name="_csrf" value="([^"]+)"', r.text).group(1)
        client.post(
            "/admin/login",
            data={"username": "admin", "password": "Li&Blog@2026", "_csrf": csrf0},
            follow_redirects=False,
        )
        r = client.get("/admin/")
        return re.search(r'name="_csrf" value="([^"]+)"', r.text).group(1)

    def test_preview_out_requires_login(self):
        target = settings.preview_root / "posts" / "draft" / "index.html"
        target.parent.mkdir(parents=True)
        target.write_text("<html>草稿</html>", encoding="utf-8")
        with TestClient(app) as client:
            r = client.get("/admin/preview-out/posts/draft/index.html", follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self._login(client)
            r = client.get("/admin/preview-out/posts/draft/index.html")
            self.assertEqual(r.status_code, 200)
            self.assertIn("草稿", r.text)

    def test_stats_javascript_href_sanitized(self):
        conn = connect()
        conn.execute(
            "INSERT INTO stats (path, day, views) VALUES (?, ?, 1)",
            ("javascript:alert(1)", "2026-08-18"),
        )
        conn.commit()
        conn.close()
        self.assertEqual(safe_stats_href("javascript:alert(1)"), "")
        self.assertEqual(safe_stats_href("/posts/ok/"), "/posts/ok/")
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/stats")
            self.assertNotIn('href="javascript:', r.text)

    def test_stats_csv_escapes_formula_and_quotes(self):
        conn = connect()
        conn.execute(
            "INSERT INTO stats (path, day, views) VALUES (?, ?, 1)",
            ('=HYPERLINK("https://evil")', "2026-08-18"),
        )
        conn.execute(
            "INSERT INTO stats (path, day, views) VALUES (?, ?, 1)",
            ('/posts/a"b', "2026-08-18"),
        )
        conn.commit()
        conn.close()
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/stats/export")
            self.assertEqual(r.status_code, 200)
            self.assertIn("'=HYPERLINK", r.text)
            self.assertIn('"/posts/a""b"', r.text)

    def test_rename_slug_removes_old_file(self):
        store.write_markdown(
            "projects", "old-slug", {"title": "Old", "date": "2026-08-18"}, "正文"
        )
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post(
                "/admin/projects/save",
                data={
                    "_csrf": csrf,
                    "slug": "old-slug",
                    "new_slug": "new-slug",
                    "action": "save_stay",
                    "title": "Renamed",
                    "date": "2026-08-18",
                    "status": "published",
                    "body": "新正文",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertFalse((settings.content_root / "projects" / "old-slug.md").exists())
            self.assertTrue((settings.content_root / "projects" / "new-slug.md").exists())

    def test_custom_dropdown_referenced_on_list_and_base(self):
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/projects")
            self.assertEqual(r.status_code, 200)
            self.assertIn('data-custom-dropdown', r.text)
            self.assertIn('name="per_page" aria-label="每页条数" data-custom-dropdown', r.text)
            r = client.get("/admin/static/js/admin-dropdown.js")
            self.assertEqual(r.status_code, 200)
            self.assertIn("custom-select", r.text)

    def test_row_actions_confirm_use_data_attribute(self):
        store.write_markdown(
            "projects",
            "confirm-ui",
            {"title": "Confirm UI", "date": "2026-08-18", "status": "published"},
            "正文",
        )
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/projects")
            self.assertEqual(r.status_code, 200)
            self.assertIn('data-confirm="确定移入回收站', r.text)
            self.assertIn("form[data-confirm]", r.text)
            self.assertNotIn('onsubmit="return confirm', r.text)

    def test_project_save_preserves_unknown_fields(self):
        store.write_markdown(
            "projects",
            "proj",
            {
                "title": "P",
                "date": "2026-08-18",
                "status": "active",
                "tech": [],
                "summary": "s",
                "badge": {"label": "B"},
                "show_on_home": False,
                "cover": "/img/x.png",
                "custom_field": "保留我",
            },
            "正文",
        )
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            client.post(
                "/admin/projects/save",
                data={
                    "_csrf": csrf,
                    "slug": "proj",
                    "new_slug": "",
                    "action": "save_stay",
                    "title": "P2",
                    "date": "2026-08-18",
                    "status": "active",
                    "repo": "",
                    "tech": "Docker",
                    "summary": "s2",
                    "badge_label": "B",
                    "badge_color": "",
                    "badge_href": "",
                    "body": "正文",
                },
                follow_redirects=False,
            )
        fm, _ = store.read_markdown("projects", "proj")
        self.assertEqual(fm["cover"], "/img/x.png")
        self.assertEqual(fm["custom_field"], "保留我")
        self.assertFalse(fm["show_on_home"])
        self.assertEqual(fm["tech"], ["Docker"])

    def test_trash_restore_cycle(self):
        store.write_markdown(
            "projects",
            "trash-me",
            {"title": "Trash", "date": "2026-08-18", "status": "published"},
            "正文",
        )
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post(
                "/admin/projects/trash-me/trash",
                data={"_csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertFalse((settings.content_root / "projects" / "trash-me.md").exists())
            self.assertEqual(len(store.list_trash()), 1)
            r = client.get("/admin/trash")
            self.assertIn("Trash", r.text)
            r = client.post(
                "/admin/trash/projects/trash-me/restore",
                data={"_csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertTrue((settings.content_root / "projects" / "trash-me.md").exists())
            self.assertEqual(store.list_trash(), [])

    def test_duplicate_creates_draft(self):
        store.write_markdown(
            "projects",
            "source",
            {"title": "Source", "date": "2026-08-18", "status": "published"},
            "正文内容",
        )
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post(
                "/admin/projects/source/duplicate",
                data={"_csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
        fm, body = store.read_markdown("projects", "source-2")
        self.assertEqual(fm["status"], "draft")
        self.assertEqual(body.strip(), "正文内容")
        self.assertIn("副本", fm["title"])

    def test_slug_check_json(self):
        store.write_markdown(
            "projects",
            "exists",
            {"title": "E", "date": "2026-08-18"},
            "正文",
        )
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/projects/slug-check?slug=exists")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json(), {"valid": True, "exists": True})
            r = client.get("/admin/projects/slug-check?slug=free")
            self.assertEqual(r.json(), {"valid": True, "exists": False})
            r = client.get("/admin/projects/slug-check?slug=BAD SLUG")
            self.assertEqual(r.json(), {"valid": False, "exists": False})

    def test_media_unused_filter(self):
        (media.MEDIA_ROOT / "unused.png").write_bytes(b"png")
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/media?unused=1")
            self.assertEqual(r.status_code, 200)
            self.assertIn("unused.png", r.text)
            self.assertIn("可放心清理", r.text)
            self.assertIn("全部图片", r.text)

    def test_dashboard_widgets(self):
        store.write_markdown(
            "projects",
            "demo",
            {"title": "Demo", "date": "2026-08-18", "status": "active"},
            "正文",
        )
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/")
            self.assertIn("最近活动", r.text)
            self.assertIn("内容体检", r.text)
            self.assertIn("项目", r.text)

    def test_stats_path_maps_to_title(self):
        store.write_markdown(
            "projects",
            "mapped",
            {"title": "可读标题", "date": "2026-08-18"},
            "正文",
        )
        conn = connect()
        conn.execute(
            "INSERT INTO stats (path, day, views) VALUES (?, ?, 1)",
            ("/projects/mapped/", "2026-08-19"),
        )
        conn.commit()
        conn.close()
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/stats")
            self.assertIn("可读标题", r.text)
            self.assertIn("/projects/mapped/", r.text)

    def test_logs_kind_filter_and_pagination(self):
        conn = connect()
        for i in range(3):
            conn.execute(
                "INSERT INTO audit_log (at, kind, detail) VALUES (?, ?, ?)",
                (1000 + i, "content_save", f"posts/{i}"),
            )
        conn.commit()
        conn.close()
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/logs?kind=content_save")
            self.assertIn("posts/0", r.text)
            r = client.get("/admin/logs?kind=login_ok")
            self.assertNotIn("posts/0", r.text)

    def test_logout_post_requires_csrf(self):
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post("/admin/logout", data={"_csrf": "bad"}, follow_redirects=False)
            self.assertEqual(r.status_code, 303)
            self.assertEqual(client.get("/admin/").status_code, 200)
            r = client.post("/admin/logout", data={"_csrf": csrf}, follow_redirects=False)
            self.assertEqual(r.status_code, 302)
            self.assertEqual(client.get("/admin/", follow_redirects=False).status_code, 302)

    def test_ip_whitelist_enforced(self):
        settings.ip_whitelist = ["203.0.113.10"]
        self.addCleanup(setattr, settings, "ip_whitelist", [])
        with TestClient(app) as client:
            r = client.get(
                "/admin/login", headers={"X-Forwarded-For": "203.0.113.9"}
            )
            self.assertEqual(r.status_code, 403)
            r = client.get(
                "/admin/login", headers={"X-Forwarded-For": "203.0.113.10"}
            )
            self.assertEqual(r.status_code, 200)

    def test_config_save_write_failure_redirects_not_500(self):
        with TestClient(app) as client:
            csrf = self._login(client)
            with mock.patch(
                "admin.content.save_yaml", side_effect=OSError("readonly fs")
            ):
                r = client.post(
                    "/admin/config/brand",
                    data={"_csrf": csrf},
                    follow_redirects=False,
                )
            self.assertEqual(r.status_code, 303)
            location = urllib.parse.unquote(r.headers.get("location", ""))
            self.assertIn("不可写", location)

    def test_profile_form_uses_row_indexed_input_names(self):
        (settings.config_root / "profile.yaml").write_text(
            "name: T\n"
            "skills:\n"
            "- name: A\n  icon: a\n"
            "- name: B\n  icon: b\n",
            encoding="utf-8",
        )
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/config/profile")
            self.assertEqual(r.status_code, 200)
            self.assertIn('name="skills[0][name]"', r.text)
            self.assertIn('name="skills[1][name]"', r.text)
            self.assertIn('name="skills[0][icon]"', r.text)
            self.assertNotIn('name="skills[2][name]"', r.text)

    def test_rewrite_preview_html_rewrites_assets(self):
        html = (
            '<link href="/css/style.css">'
            '<script src="/js/app.js"></script>'
            '<img src="/img/a.png">'
            '<div style="background:url(\'/img/b.png\')"></div>'
        )
        out = rewrite_preview_html(html, "admin")
        self.assertIn('href="/admin/static/css/style.css"', out)
        self.assertIn('src="/admin/static/js/app.js"', out)
        self.assertIn('src="/admin/preview-out/img/a.png"', out)
        self.assertIn("url('/admin/preview-out/img/b.png')", out)

    def test_friends_admin_list_and_edit_fields(self):
        store.write_markdown(
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
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/friends")
            self.assertEqual(r.status_code, 200)
            self.assertIn("友情链接", r.text)
            self.assertIn("https://example.com/", r.text)
            self.assertIn("/admin/friends/new", r.text)
            r = client.get("/admin/friends/example/edit")
            self.assertEqual(r.status_code, 200)
            self.assertIn('name="href"', r.text)
            self.assertIn('name="weight"', r.text)

    def test_friends_save_validates_url(self):
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post(
                "/admin/friends/save",
                data={
                    "_csrf": csrf,
                    "slug": "",
                    "new_slug": "bad-link",
                    "action": "save",
                    "title": "坏链接",
                    "href": "javascript:alert(1)",
                    "description": "",
                    "weight": "1",
                    "body": "",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertFalse((settings.content_root / "friends" / "bad-link.md").exists())
            r = client.post(
                "/admin/friends/save",
                data={
                    "_csrf": csrf,
                    "slug": "",
                    "new_slug": "good-link",
                    "action": "save",
                    "title": "好链接",
                    "href": "https://example.com/",
                    "description": "简介",
                    "weight": "1",
                    "body": "",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            fm, _ = store.read_markdown("friends", "good-link")
            self.assertEqual(fm["href"], "https://example.com/")
            self.assertEqual(fm["weight"], 1)

    def test_friends_delete_removes_file(self):
        store.write_markdown(
            "friends",
            "gone",
            {"title": "待删除", "href": "https://example.com/", "weight": 1},
            "",
        )
        original = build.run_full
        build.run_full = lambda: (types.SimpleNamespace(returncode=0, stderr=""), 0.01)
        self.addCleanup(setattr, build, "run_full", original)
        with TestClient(app) as client:
            csrf = self._login(client)
            r = client.post(
                "/admin/friends/gone/delete",
                data={"_csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertFalse((settings.content_root / "friends" / "gone.md").exists())

if __name__ == "__main__":
    unittest.main()
