from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

from docx import Document

from logic.resume_analyzer import generate_suggestions
from logic.resume_parser import (
    ResumeParseError,
    SCANNED_PDF_MESSAGE,
    file_fingerprint,
    parse_resume_file,
)


class FakePage:
    def __init__(self, text: str | None):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, pages, *, encrypted: bool = False, unlocked: int = 1):
        self.pages = pages
        self.is_encrypted = encrypted
        self.unlocked = unlocked

    def decrypt(self, password: str):
        return self.unlocked


def build_docx() -> bytes:
    document = Document()
    document.add_heading("产品经理简历", level=1)
    document.add_paragraph("负责 AI 产品需求分析与用户路径设计。")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "技能"
    table.cell(0, 1).text = "Prompt、数据分析"
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class ResumeParserTest(unittest.TestCase):
    def test_text_encodings_are_supported(self):
        text = "项目经历：AI 简历优化助手"
        for encoding in ("utf-8", "utf-8-sig", "gbk"):
            with self.subTest(encoding=encoding):
                result = parse_resume_file("resume.txt", text.encode(encoding))
                self.assertEqual(text, result.text)
                self.assertEqual("TXT", result.file_type)

    def test_markdown_is_normalized(self):
        result = parse_resume_file("resume.md", b"# Resume\n\n\n- Python   SQL\n")
        self.assertEqual("# Resume\n\n- Python SQL", result.text)

    def test_docx_extracts_paragraphs_and_tables(self):
        result = parse_resume_file("resume.docx", build_docx())
        self.assertIn("负责 AI 产品需求分析与用户路径设计。", result.text)
        self.assertIn("技能 | Prompt、数据分析", result.text)
        self.assertEqual("DOCX", result.file_type)

    def test_parsed_docx_can_feed_rule_suggestion_engine(self):
        parsed = parse_resume_file("resume.docx", build_docx())
        suggestions = generate_suggestions(
            resume_text=parsed.text,
            jd_text="负责 AI 产品需求分析、MVP 设计、Prompt 策略和产品效果评估。",
            task_id="task_upload",
            user_id="user_upload",
            prompt_group="B",
        )
        self.assertGreaterEqual(len(suggestions), 3)
        self.assertTrue(all(row["status"] == "pending" for row in suggestions))

    @patch("logic.resume_parser.PdfReader")
    def test_pdf_extracts_multiple_pages_and_warns_for_empty_page(self, reader):
        reader.return_value = FakeReader([FakePage("第一页内容"), FakePage(None), FakePage("第二页内容")])
        result = parse_resume_file("resume.pdf", b"fake-pdf")
        self.assertEqual("第一页内容\n第二页内容", result.text)
        self.assertEqual("PDF", result.file_type)
        self.assertIn("1 页未提取到文字", result.warnings[0])

    @patch("logic.resume_parser.PdfReader")
    def test_pdf_without_text_shows_scanned_pdf_message(self, reader):
        reader.return_value = FakeReader([FakePage(None), FakePage("")])
        with self.assertRaisesRegex(ResumeParseError, SCANNED_PDF_MESSAGE):
            parse_resume_file("resume.pdf", b"fake-pdf")

    @patch("logic.resume_parser.PdfReader")
    def test_locked_pdf_shows_safe_error(self, reader):
        reader.return_value = FakeReader([], encrypted=True, unlocked=0)
        with self.assertRaisesRegex(ResumeParseError, SCANNED_PDF_MESSAGE):
            parse_resume_file("resume.pdf", b"fake-pdf")

    @patch("logic.resume_parser.PdfReader", side_effect=ValueError("broken"))
    def test_corrupt_pdf_shows_read_error(self, _reader):
        with self.assertRaisesRegex(ResumeParseError, "PDF 文件无法读取"):
            parse_resume_file("resume.pdf", b"fake-pdf")

    def test_legacy_doc_is_rejected(self):
        with self.assertRaisesRegex(ResumeParseError, "另存为 .docx"):
            parse_resume_file("resume.doc", b"legacy-word")

    def test_truncation_is_reported(self):
        result = parse_resume_file("resume.txt", b"123456789", max_chars=5)
        self.assertEqual("12345", result.text)
        self.assertEqual(5, result.char_count)
        self.assertIn("仅保留前 5 字", result.warnings[0])

    def test_fingerprint_is_stable_and_content_sensitive(self):
        self.assertEqual(file_fingerprint(b"same"), file_fingerprint(b"same"))
        self.assertNotEqual(file_fingerprint(b"same"), file_fingerprint(b"different"))


if __name__ == "__main__":
    unittest.main()
