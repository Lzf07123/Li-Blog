import tempfile
import unittest
from pathlib import Path

from admin.audit import audit_content


class TestAudit(unittest.TestCase):
    def test_audit_detects_links_images_and_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "content" / "posts").mkdir(parents=True)
            (root / "content" / "posts" / "a.md").write_text(
                "---\ntitle: 重复标题\n---\n"
                "![图](/img/missing.png)\n"
                "[坏链](/projects/nope/)\n",
                encoding="utf-8",
            )
            (root / "content" / "posts" / "b.md").write_text(
                "---\ntitle: 重复标题\n---\n正文\n",
                encoding="utf-8",
            )
            issues = audit_content(root)
            messages = " | ".join(i["message"] for i in issues)
            self.assertIn("内部链接不存在", messages)
            self.assertIn("图片/资源缺失", messages)
            self.assertIn("标题重复", messages)


if __name__ == "__main__":
    unittest.main()
