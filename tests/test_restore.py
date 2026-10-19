import io
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Optional

from admin import media, restore, security
from admin.config import settings
from admin.db import connect, create_admin, init_db
from admin.session import create_session, get_session

def make_backup_zip(
    content: bytes,
    config: bytes,
    media_bytes: bytes,
    db: bytes,
    hugo: Optional[bytes] = None,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("content/posts/a.md", content)
        zf.writestr("config/brand.yaml", config)
        zf.writestr("themes/blog-theme/static/img/x.png", media_bytes)
        zf.writestr("data/blog.db", db)
        zf.writestr("backup-manifest.json", "{}")
        if hugo is not None:
            zf.writestr("hugo.toml", hugo)
    return buf.getvalue()

class TestRestore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        settings.content_root = root / "content"
        settings.config_root = root / "config"
        settings.db_path = root / "blog.db"
        media.MEDIA_ROOT = root / "img"
        (settings.content_root / "posts").mkdir(parents=True)
        settings.config_root.mkdir()
        media.MEDIA_ROOT.mkdir()
        init_db()
        conn = connect()
        create_admin(conn, "admin", security.hash_password("pass"))
        conn.close()
        self.session_id = create_session("local")
        (settings.content_root / "posts" / "a.md").write_text(
            "AAA", encoding="utf-8"
        )
        (settings.config_root / "brand.yaml").write_text(
            "name: Li&Blog\n", encoding="utf-8"
        )
        (media.MEDIA_ROOT / "x.png").write_bytes(b"img")

    def tearDown(self):
        self._tmp.cleanup()

    def test_restore_backup_replaces_and_clears_sessions(self):
        backup_zip = make_backup_zip(
            b"---\ntitle: A\n---\nAAA",
            b"name: Restored\n",
            b"img2",
            settings.db_path.read_bytes(),
        )
        (settings.content_root / "posts" / "a.md").write_text(
            "CHANGED", encoding="utf-8"
        )
        (settings.config_root / "brand.yaml").write_text(
            "name: Changed\n", encoding="utf-8"
        )
        (media.MEDIA_ROOT / "x.png").write_bytes(b"other")

        result = restore.restore_backup(backup_zip, safety=True)

        self.assertEqual(
            (settings.content_root / "posts" / "a.md").read_text(encoding="utf-8"),
            "---\ntitle: A\n---\nAAA",
        )
        self.assertIn("Restored", (settings.config_root / "brand.yaml").read_text(encoding="utf-8"))
        self.assertEqual((media.MEDIA_ROOT / "x.png").read_bytes(), b"img2")
        conn = connect()
        admin = conn.execute("SELECT username FROM admin_account WHERE id = 1").fetchone()
        conn.close()
        self.assertEqual(admin["username"], "admin")
        self.assertIsNone(get_session(self.session_id))
        self.assertIsNotNone(result["safety_backup"])
        safety = Path(result["safety_backup"])
        self.assertTrue(safety.exists())

    def test_restore_rejects_unallowed_path(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("admin/main.py", "evil")
        with self.assertRaises(ValueError):
            restore.parse_restore_entries(buf.getvalue())

    def test_restore_rejects_traversal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.md", "x")
        with self.assertRaises(ValueError):
            restore.parse_restore_entries(buf.getvalue())

    def test_restore_without_database_keeps_current_admin(self):
        # 手动构造不含 data/blog.db 的备份
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("content/posts/a.md", b"---\ntitle: A\n---\nAAA")
            zf.writestr("config/brand.yaml", b"name: Restored\n")
            zf.writestr("themes/blog-theme/static/img/x.png", b"img2")
        result = restore.restore_backup(buf.getvalue(), safety=False)
        self.assertEqual(result["counts"]["database"], 0)
        conn = connect()
        admin = conn.execute("SELECT username FROM admin_account WHERE id = 1").fetchone()
        conn.close()
        self.assertEqual(admin["username"], "admin")

    def test_restore_limits_read_from_settings(self):
        original = settings.restore_max_files
        try:
            settings.restore_max_files = 1
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("content/a.md", "x")
                zf.writestr("content/b.md", "y")
            with self.assertRaises(ValueError):
                restore.parse_restore_entries(buf.getvalue())
        finally:
            settings.restore_max_files = original

    def test_restore_sanitizes_svg_icons(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "config/brand.yaml",
                "name: X\nicp_icon: '<svg onload=\"alert(1)\"><path/></svg>'\n",
            )
            zf.writestr("content/posts/a.md", "---\ntitle: A\n---\nAAA")
        restore.restore_backup(buf.getvalue(), safety=False)
        text = (settings.config_root / "brand.yaml").read_text(encoding="utf-8")
        self.assertNotIn("onload", text)
        self.assertIn("<svg>", text)
