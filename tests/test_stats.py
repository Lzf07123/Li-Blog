import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from admin import media, security
from admin.config import settings
from admin.db import connect, create_admin, init_db
from admin.main import app


class StatsRoutesTest(unittest.TestCase):
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
        conn.executemany(
            "INSERT INTO stats (path, day, views) VALUES (?, ?, ?)",
            [
                ("/projects/a/", "2026-07-01", 3),
                ("/projects/b/", "2026-08-01", 5),
                ("/projects/a/", "2026-08-02", 2),
            ],
        )
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
        r = client.get("/admin/stats")
        return re.search(r'name="_csrf" value="([^"]+)"', r.text).group(1)

    def test_stats_month_grouping_and_filter(self):
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/stats?group=month")
            self.assertEqual(r.status_code, 200)
            self.assertIn("2026-07", r.text)
            self.assertIn("2026-08", r.text)
            r = client.get("/admin/stats?start=2026-08-01")
            self.assertIn(">7<", r.text.replace(" ", ""))  # 5+2 次

    def test_stats_path_grouping_deduplicates_paths(self):
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/stats?group=path")
            self.assertEqual(r.status_code, 200)
            # /projects/a/ 存在 07-01 与 08-02 两条记录，应合并为一行并显示最近日期
            self.assertNotIn("2026-07-01", r.text)
            self.assertEqual(r.text.count("2026-08-02"), 1)
            # a 合计 5 次、b 合计 5 次，总访问应为 10
            self.assertIn(">10<", r.text.replace(" ", ""))

    def test_health_page(self):
        with TestClient(app) as client:
            self._login(client)
            r = client.get("/admin/health")
            self.assertEqual(r.status_code, 200)
            self.assertIn("健康检查", r.text)
            self.assertIn("content 目录", r.text)


if __name__ == "__main__":
    unittest.main()
