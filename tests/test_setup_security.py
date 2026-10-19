"""首次建站/后台鉴权安全回归测试（对应上线前审查 B1/B2/B3）。"""

import re
import tempfile
import unittest
from pathlib import Path

from urllib.parse import unquote

from fastapi.testclient import TestClient

from admin import media, security
from admin.config import settings
from admin.db import connect, create_admin, get_admin, init_db
from admin.main import app


class SetupSecurityBase(unittest.TestCase):
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
        settings.setup_token = ""
        media.MEDIA_ROOT = root / "img"
        (settings.content_root / "posts").mkdir(parents=True)
        (settings.content_root / "projects").mkdir(parents=True)
        settings.config_root.mkdir(parents=True)
        settings.preview_root.mkdir(parents=True)
        media.MEDIA_ROOT.mkdir(parents=True)
        (settings.config_root / "brand.yaml").write_text(
            "name: Audit\nlogo: ''\n", encoding="utf-8"
        )
        (settings.config_root / "profile.yaml").write_text(
            "name: Audit\n", encoding="utf-8"
        )
        init_db()

    def tearDown(self):
        self._tmp.cleanup()
        settings.setup_token = ""

    @staticmethod
    def _csrf(html: str) -> str:
        return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


class AnonSessionBypassTest(SetupSecurityBase):
    """B1：匿名会话不得访问受 require_login 保护的路由。"""

    def setUp(self):
        super().setUp()
        conn = connect()
        create_admin(conn, "admin", security.hash_password("Li&Blog@2026"))
        conn.close()

    def test_anon_session_rejected_on_protected_routes(self):
        with TestClient(app) as client:
            client.get("/admin/login")  # 发放匿名会话 Cookie
            for path in ("/admin/", "/admin/projects", "/admin/media", "/admin/settings/account"):
                r = client.get(path, follow_redirects=False)
                self.assertEqual(r.status_code, 302, path)
                self.assertIn("/admin/login", r.headers.get("location", ""), path)

    def test_real_login_can_access(self):
        with TestClient(app) as client:
            html = client.get("/admin/login").text
            csrf = self._csrf(html)
            r = client.post(
                "/admin/login",
                data={"username": "admin", "password": "Li&Blog@2026", "_csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            r = client.get("/admin/projects", follow_redirects=False)
            self.assertEqual(r.status_code, 200)


class SetupBasicGuardTest(SetupSecurityBase):
    """B2：管理员已存在后，匿名 POST /setup/basic 不得覆写品牌/资料。"""

    def setUp(self):
        super().setUp()
        conn = connect()
        create_admin(conn, "admin", security.hash_password("Li&Blog@2026"))
        conn.close()

    def test_anon_post_cannot_overwrite_brand(self):
        with TestClient(app) as client:
            html = client.get("/admin/login").text
            csrf = self._csrf(html)
            r = client.post(
                "/admin/setup/basic",
                data={
                    "_csrf": csrf,
                    "site_name": "HACKED",
                    "tagline": "x",
                    "promise": "x",
                    "persona": "x",
                    "name": "x",
                    "identity": "x",
                    "direction": "x",
                    "goal": "x",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 302)
            self.assertIn("/admin/", r.headers.get("location", ""))
        brand = (settings.config_root / "brand.yaml").read_text(encoding="utf-8")
        self.assertNotIn("HACKED", brand)
        self.assertIn("Audit", brand)


class SetupTokenTest(SetupSecurityBase):
    """B3：配置 SETUP_TOKEN 后，建站/恢复必须提供令牌，防抢占接管。"""

    TOKEN = "review-setup-token-2026"

    def setUp(self):
        super().setUp()
        settings.setup_token = self.TOKEN

    def test_setup_page_requires_token(self):
        with TestClient(app) as client:
            # GET 正常渲染（含令牌输入框），令牌在 POST 时强制校验
            r = client.get("/admin/setup/basic", follow_redirects=False)
            self.assertEqual(r.status_code, 200)
            self.assertIn('name="setup_token"', r.text)
            # 带请求头亦可进入
            r = client.get(
                "/admin/setup/basic",
                headers={"X-Setup-Token": self.TOKEN},
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 200)

    def test_account_creation_requires_token(self):
        with TestClient(app) as client:
            html = client.get(
                "/admin/setup/basic", headers={"X-Setup-Token": self.TOKEN}
            ).text
            csrf = self._csrf(html)
            # 无令牌：拒绝
            r = client.post(
                "/admin/setup/account",
                data={
                    "_csrf": csrf,
                    "username": "attacker",
                    "password": "AttackerPass123!",
                    "confirm": "AttackerPass123!",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertIn("安装令牌错误", unquote(r.headers.get("location", "")))
            conn = connect()
            self.assertIsNone(get_admin(conn))
            conn.close()
            # 带令牌：允许创建
            r = client.post(
                "/admin/setup/account",
                headers={"X-Setup-Token": self.TOKEN},
                data={
                    "_csrf": csrf,
                    "username": "admin",
                    "password": "Li&Blog@2026",
                    "confirm": "Li&Blog@2026",
                },
                follow_redirects=False,
            )
            self.assertEqual(r.status_code, 303)
            self.assertIn("/admin/setup/oidc", r.headers.get("location", ""))
            conn = connect()
            self.assertIsNotNone(get_admin(conn))
            conn.close()


if __name__ == "__main__":
    unittest.main()
