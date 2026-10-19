"""内容体检：扫描内部链接/图片缺失、空正文、短摘要、重复标题与超长标题。"""

import datetime
import re
from pathlib import Path

import yaml

from admin.config import ROOT


def audit_content(root=None) -> list[dict]:
    root = Path(root or ROOT)
    content_root = root / "content"
    issues: list[dict] = []
    if not content_root.exists():
        return issues
    theme_static = root / "themes" / "blog-theme" / "static"
    site_static = root / "static"

    pages = []
    for p in sorted(content_root.rglob("*.md")):
        rel = p.relative_to(content_root)
        section = rel.parts[0] if len(rel.parts) > 1 else ""
        text = p.read_text(encoding="utf-8")
        fm: dict = {}
        body = text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                try:
                    fm = yaml.safe_load(parts[1]) or {}
                    body = parts[2]
                except yaml.YAMLError:
                    issues.append(
                        {
                            "severity": "danger",
                            "section": section,
                            "slug": p.stem,
                            "title": p.stem,
                            "message": "frontmatter 解析失败",
                        }
                    )
        pages.append(
            {
                "path": p,
                "rel": rel.as_posix(),
                "section": section,
                "slug": p.stem,
                "title": str(fm.get("title") or p.stem),
                "fm": fm,
                "body": body,
                "text": text,
            }
        )

    # 链接与图片存在性
    md_link_re = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
    href_re = re.compile(r'\bhref\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    src_re = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
    by_rel = {page["rel"]: page for page in pages}

    def check_url(url: str, page: dict) -> None:
        url = url.strip().split()[0].strip("<>")
        if not url or url.startswith(("#", "http://", "https://", "mailto:", "data:")):
            return
        clean = url.split("#")[0].split("?")[0].rstrip("/")
        if clean.startswith(("/projects/", "/timeline/")):
            rel = clean.lstrip("/")
            if not any(
                k == f"{rel}.md" or k.startswith(f"{rel}/") for k in by_rel
            ) and not (content_root / rel / "_index.md").exists():
                issues.append(
                    {
                        "severity": "danger",
                        "section": page["section"],
                        "slug": page["slug"],
                        "title": page["title"],
                        "message": f"内部链接不存在：{url}",
                    }
                )
        elif clean.startswith(("/img/", "/assets/")):
            rel = clean.lstrip("/")
            if not any((base / rel).exists() for base in (theme_static, site_static)):
                issues.append(
                    {
                        "severity": "danger",
                        "section": page["section"],
                        "slug": page["slug"],
                        "title": page["title"],
                        "message": f"图片/资源缺失：{url}",
                    }
                )

    for page in pages:
        for m in md_link_re.finditer(page["text"]):
            check_url(m.group(1), page)
        for m in href_re.finditer(page["text"]):
            check_url(m.group(1), page)
        for m in src_re.finditer(page["text"]):
            check_url(m.group(1), page)

    # 内容质量
    titles: dict[str, dict[str, str]] = {}
    for page in pages:
        if page["section"] in ("projects", "timeline") and not page["body"].strip():
            issues.append(
                {
                    "severity": "warning",
                    "section": page["section"],
                    "slug": page["slug"],
                    "title": page["title"],
                    "message": "正文为空",
                }
            )
        if len(page["title"]) > 60:
            issues.append(
                {
                    "severity": "warning",
                    "section": page["section"],
                    "slug": page["slug"],
                    "title": page["title"],
                    "message": f"标题过长（{len(page['title'])} 字）",
                }
            )
        seen = titles.setdefault(page["section"], {})
        if page["title"] in seen:
            issues.append(
                {
                    "severity": "warning",
                    "section": page["section"],
                    "slug": page["slug"],
                    "title": page["title"],
                    "message": f"与 {seen[page['title']]} 标题重复",
                }
            )
        else:
            seen[page["title"]] = page["slug"]
    return issues
