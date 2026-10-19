"""从备份 ZIP 恢复站点数据：content/config/媒体/SQLite/hugo.toml。"""

import io
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from admin import content as content_store
from admin import media
from admin.backup import build_backup_zip
from admin.config import ROOT, settings
from admin.db import connect, init_db

ALLOWED_DIR_ROOTS = (
    "content/",
    "config/",
    "themes/blog-theme/static/img/",
)


def restore_backup(data: bytes, safety: bool = True) -> dict:
    """恢复备份并返回统计；恢复前默认先生成一份安全备份。"""
    entries = parse_restore_entries(data)
    if not entries:
        raise ValueError("备份中没有可恢复的数据")
    safety_path = _save_safety_backup() if safety else None

    roots = set()
    for arcname, _ in entries:
        if arcname.startswith("content/"):
            roots.add("content")
        elif arcname.startswith("config/"):
            roots.add("config")
        elif arcname.startswith("themes/blog-theme/static/img/"):
            roots.add("media")
    if "content" in roots:
        _clear_dir(settings.content_root)
    if "config" in roots:
        _clear_dir(settings.config_root)
    if "media" in roots:
        _clear_dir(media.MEDIA_ROOT)

    counts = {"content": 0, "config": 0, "media": 0, "database": 0, "hugo": 0}
    for arcname, content in entries:
        target = _target_for(arcname)
        target.parent.mkdir(parents=True, exist_ok=True)
        if arcname == "data/blog.db":
            tmp = target.with_name(target.name + ".tmp")
            tmp.write_bytes(content)
            tmp.replace(target)
            counts["database"] = 1
        else:
            target.write_bytes(content)
            if arcname.startswith("content/"):
                counts["content"] += 1
            elif arcname.startswith("config/"):
                counts["config"] += 1
            elif arcname.startswith("themes/blog-theme/static/img/"):
                counts["media"] += 1
            elif arcname == "hugo.toml":
                counts["hugo"] = 1

    if counts["database"]:
        init_db()
    if counts["config"]:
        try:
            brand = content_store.load_yaml("brand")
            if isinstance(brand, dict):
                brand["icp_icon"] = content_store.sanitize_inline_svg(brand.get("icp_icon", ""))
                brand["police_icon"] = content_store.sanitize_inline_svg(brand.get("police_icon", ""))
                content_store.save_yaml("brand", brand)
        except (ValueError, OSError):
            pass
    _clear_sessions()
    return {"counts": counts, "safety_backup": str(safety_path) if safety_path else None}


def parse_restore_entries(data: bytes) -> list[tuple[str, bytes]]:
    """校验并读取备份 ZIP，只放行受支持的站点数据路径。"""
    entries = []
    total = 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP 文件无法解析") from exc
    with zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"备份含非法路径: {name}")
            if name == "backup-manifest.json":
                continue
            allowed = name == "hugo.toml" or name == "data/blog.db" or name.startswith(
                ALLOWED_DIR_ROOTS
            )
            if not allowed:
                raise ValueError(f"备份包含不允许的路径: {name}")
            if info.file_size > settings.restore_max_bytes:
                raise ValueError(f"{name} 超过大小限制")
            total += info.file_size
            if total > settings.restore_max_bytes:
                raise ValueError("备份解压后超过大小限制")
            if len(entries) >= settings.restore_max_files:
                raise ValueError("备份文件数量超过限制")
            try:
                entries.append((name, zf.read(info)))
            except (RuntimeError, NotImplementedError) as exc:
                raise ValueError(f"{name}: 无法读取（加密或损坏）") from exc
    if len(entries) > settings.restore_max_files:
        raise ValueError("备份文件数量超过限制")
    return entries


def _target_for(arcname: str) -> Path:
    if arcname == "hugo.toml":
        return ROOT / "hugo.toml"
    if arcname == "data/blog.db":
        return settings.db_path
    if arcname.startswith("content/"):
        return _safe_under(settings.content_root, arcname[len("content/") :])
    if arcname.startswith("config/"):
        return _safe_under(settings.config_root, arcname[len("config/") :])
    if arcname.startswith("themes/blog-theme/static/img/"):
        return _safe_under(media.MEDIA_ROOT, arcname[len("themes/blog-theme/static/img/") :])
    raise ValueError(f"不允许的路径: {arcname}")


def _safe_under(root: Path, rel: str) -> Path:
    root_r = root.resolve()
    p = (root_r / rel).resolve()
    if not p.is_relative_to(root_r):
        raise ValueError("path escape")
    return p


def _clear_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _save_safety_backup() -> Path:
    backup_dir = settings.db_path.parent / "restore-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"pre-restore-{ts}.zip"
    path.write_bytes(build_backup_zip())
    return path


def _clear_sessions() -> None:
    conn = connect()
    try:
        conn.execute("DELETE FROM sessions")
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()
