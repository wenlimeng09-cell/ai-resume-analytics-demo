from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from pypdf import PdfReader


SCANNED_PDF_MESSAGE = (
    "该 PDF 可能是扫描件、图片文件或受保护文件，请上传可复制文字的 "
    "PDF/DOCX，或直接粘贴简历文本。"
)


class ResumeParseError(ValueError):
    """Raised when an uploaded resume cannot be converted to usable text."""


@dataclass(frozen=True)
class ParsedResume:
    text: str
    file_type: str
    char_count: int
    warnings: tuple[str, ...] = ()


def file_fingerprint(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


def normalize_resume_text(text: str) -> str:
    normalized_lines: list[str] = []
    previous_blank = False
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"[ \t\u00a0]+", " ", raw_line).strip()
        if line:
            normalized_lines.append(line)
            previous_blank = False
        elif normalized_lines and not previous_blank:
            normalized_lines.append("")
            previous_blank = True
    return "\n".join(normalized_lines).strip()


def _decode_text(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ResumeParseError("文本文件编码无法识别，请将文件另存为 UTF-8 后重试。")


def _extract_docx_text(file_bytes: bytes) -> str:
    try:
        document = Document(BytesIO(file_bytes))
    except Exception as exc:
        raise ResumeParseError("Word 文件无法读取，请确认文件未损坏且格式为 .docx。") from exc

    parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _extract_pdf_text(file_bytes: bytes) -> tuple[str, list[str]]:
    try:
        reader = PdfReader(BytesIO(file_bytes), strict=False)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:
                raise ResumeParseError(SCANNED_PDF_MESSAGE) from exc
            if not unlocked:
                raise ResumeParseError(SCANNED_PDF_MESSAGE)

        page_texts: list[str] = []
        empty_pages = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            if text.strip():
                page_texts.append(text)
            else:
                empty_pages += 1
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError("PDF 文件无法读取，请确认文件未损坏且未设置访问密码。") from exc

    if not page_texts:
        raise ResumeParseError(SCANNED_PDF_MESSAGE)

    warnings: list[str] = []
    if empty_pages:
        warnings.append(f"PDF 中有 {empty_pages} 页未提取到文字，请检查下方文本是否完整。")
    return "\n".join(page_texts), warnings


def parse_resume_file(
    filename: str,
    file_bytes: bytes,
    *,
    max_chars: int | None = None,
) -> ParsedResume:
    if not file_bytes:
        raise ResumeParseError("上传的文件为空，请选择包含简历内容的文件。")

    suffix = Path(filename or "").suffix.lower()
    warnings: list[str] = []
    if suffix in {".txt", ".md"}:
        raw_text = _decode_text(file_bytes)
    elif suffix == ".docx":
        raw_text = _extract_docx_text(file_bytes)
    elif suffix == ".pdf":
        raw_text, warnings = _extract_pdf_text(file_bytes)
    elif suffix == ".doc":
        raise ResumeParseError("暂不支持旧版 .doc 文件，请在 Word 中另存为 .docx 后上传。")
    else:
        raise ResumeParseError("暂不支持该文件格式，请上传 PDF、DOCX、TXT 或 MD 文件。")

    text = normalize_resume_text(raw_text)
    if not text:
        if suffix == ".pdf":
            raise ResumeParseError(SCANNED_PDF_MESSAGE)
        raise ResumeParseError("文件中没有提取到可用文字，请检查文件内容或直接粘贴简历文本。")

    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rstrip()
        warnings.append(f"简历内容超过 {max_chars} 字，当前仅保留前 {max_chars} 字用于分析。")

    return ParsedResume(
        text=text,
        file_type=suffix.removeprefix(".").upper(),
        char_count=len(text),
        warnings=tuple(warnings),
    )
