"""
小說 Markdown 匯出（P2-1）。

結構：書名頁 → 目錄 → 未分卷章節 → 各卷章節；插圖依 linked_chapter_id
附於章節末尾。zip 模式將插圖一併打包（images/），md 內用相對路徑引用，
解壓即為可攜帶的完整書稿。
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR
from app.models.chapter import Chapter
from app.models.illustration import Illustration
from app.models.project import Project
from app.models.volume import Volume

logger = logging.getLogger(__name__)

_CN_NUMS = "零一二三四五六七八九"


def _cn_number(n: int) -> str:
    """1~99 → 中文數字（卷標題用）。"""
    if n <= 0 or n > 99:
        return str(n)
    if n < 10:
        return _CN_NUMS[n]
    tens, ones = divmod(n, 10)
    prefix = "" if tens == 1 else _CN_NUMS[tens]
    return f"{prefix}十{_CN_NUMS[ones] if ones else ''}"


def _volume_title(idx: int, volume: Volume) -> str:
    base = f"第{_cn_number(idx)}集"
    return f"{base}　{volume.subtitle}" if volume.subtitle else base


def _gather(db: Session, project_id: int):
    """回傳 (project, unassigned_chapters, [(volume, chapters)], illustrations_by_chapter)。"""
    project = db.get(Project, project_id)
    if not project:
        return None
    volumes = (
        db.query(Volume)
        .filter(Volume.project_id == project_id)
        .order_by(Volume.order_index)
        .all()
    )
    unassigned = (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id, Chapter.volume_id.is_(None))
        .order_by(Chapter.order_index)
        .all()
    )
    illus_by_chapter: dict[int, list[Illustration]] = {}
    for il in (
        db.query(Illustration)
        .filter(Illustration.project_id == project_id, Illustration.linked_chapter_id.isnot(None))
        .order_by(Illustration.created_at)
    ):
        illus_by_chapter.setdefault(il.linked_chapter_id, []).append(il)
    return project, unassigned, [(v, list(v.chapters)) for v in volumes], illus_by_chapter


def _chapter_md(chapter: Chapter, illustrations: list[Illustration]) -> list[str]:
    lines = [f"## {chapter.title}", ""]
    content = (chapter.content or "").strip()
    if content:
        lines += [content, ""]
    for il in illustrations:
        img_name = Path(il.file_path).name
        caption = (il.caption or "").strip()
        lines.append(f"![{caption}](images/{img_name})")
        if caption:
            lines.append(f"> {caption}")
        lines.append("")
    return lines


def build_markdown(db: Session, project_id: int) -> tuple[str, list[Illustration]] | None:
    """組出全書 Markdown。回傳 (markdown, 用到的插圖清單)；專案不存在回 None。"""
    data = _gather(db, project_id)
    if data is None:
        return None
    project, unassigned, vol_chapters, illus_by_chapter = data

    lines: list[str] = [f"# {project.title}", ""]
    if project.author:
        lines += [f"**作者**：{project.author}", ""]
    if project.synopsis:
        lines += [f"> {project.synopsis}", ""]

    # ── 目錄 ──
    lines += ["## 目錄", ""]
    for ch in unassigned:
        lines.append(f"- {ch.title}")
    for i, (vol, chapters) in enumerate(vol_chapters, start=1):
        lines.append(f"- {_volume_title(i, vol)}")
        for ch in chapters:
            lines.append(f"  - {ch.title}")
    lines.append("")

    used_illustrations: list[Illustration] = []

    def _emit_chapter(ch: Chapter) -> None:
        ills = illus_by_chapter.get(ch.id, [])
        used_illustrations.extend(ills)
        lines.extend(_chapter_md(ch, ills))

    # ── 內文：未分卷章節在前（建卷功能之前的舊資料），其後依卷序 ──
    if unassigned:
        lines += ["---", ""]
        for ch in unassigned:
            _emit_chapter(ch)
    for i, (vol, chapters) in enumerate(vol_chapters, start=1):
        lines += ["---", "", f"# {_volume_title(i, vol)}", ""]
        for ch in chapters:
            _emit_chapter(ch)

    return "\n".join(lines).rstrip() + "\n", used_illustrations


def export_zip(db: Session, project_id: int) -> tuple[bytes, str] | None:
    """打包 {title}.md + images/ 成 zip。回傳 (zip_bytes, 建議檔名)。"""
    result = build_markdown(db, project_id)
    if result is None:
        return None
    markdown, illustrations = result
    project = db.get(Project, project_id)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{project.title}.md", markdown)
        seen: set[str] = set()
        for il in illustrations:
            src = UPLOAD_DIR / il.file_path
            arcname = f"images/{Path(il.file_path).name}"
            if arcname in seen:
                continue
            seen.add(arcname)
            if src.exists():
                zf.write(src, arcname)
            else:
                logger.warning("[export] 插圖檔不存在，略過：%s", src)
    return buf.getvalue(), f"{project.title}.zip"
