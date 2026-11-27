import unittest

from logic.resume_analyzer import (
    analyze_resume_gaps,
    build_report_markdown,
    calculate_match_score,
    extract_jd_keywords,
    generate_suggestions,
)


class ResumeEvidenceTests(unittest.TestCase):
    def test_unknown_jd_has_no_fabricated_keywords_or_score_in_report(self):
        for jd in ("", "负责餐饮接待", "mobile storage / bitmap / NoSQL", "在实验室管理知识库"):
            with self.subTest(jd=jd):
                self.assertEqual(extract_jd_keywords(jd), [])
                self.assertEqual(generate_suggestions("会 SQL", jd, "t", "u"), [])
                self.assertIn("无法计算", build_report_markdown("会 SQL", jd, [], 42, 100))

    def test_aliases_are_case_insensitive_and_support_chinese_word_boundaries(self):
        self.assertEqual(extract_jd_keywords("用Ｐｙｔｈｏｎ和MYSQL核对 A / B 实验数据"), ["SQL", "Python", "A/B 实验"])
        self.assertEqual(calculate_match_score("使用 pandas 处理数据。", "Python 和 SQL"), 50)

    def test_named_tool_requires_corresponding_source_evidence(self):
        self.assertEqual(calculate_match_score("使用 Tableau 维护看板", "熟悉 Power BI"), 0)
        self.assertEqual(calculate_match_score("使用 Tableau 维护看板", "会用 Tableau 或 PowerBI"), 100)
        self.assertEqual(calculate_match_score("掌握 Python", "使用 Python 或 pandas 处理数据"), 100)

    def test_negations_and_unrelated_work_do_not_create_evidence(self):
        jd = "无需熟练使用 Power BI。熟悉 SQL、Python 和 RAG"
        text = "技能：SQL。暂不会 SQL、Python。未接触过 RAG。\n" + "在门店负责盘点。" * 100
        rows = {row["JD 要求"]: row for row in analyze_resume_gaps(text, jd)}
        self.assertEqual(set(rows), {"SQL", "Python", "RAG"})
        self.assertEqual(rows["SQL"]["简历覆盖状态"], "弱覆盖")
        self.assertEqual(rows["SQL"]["简历原文"], "技能：SQL")
        self.assertEqual(rows["Python"]["简历原文"], "")
        self.assertEqual(rows["RAG"]["简历原文"], "")

    def test_short_action_beats_skills_listing_and_long_resume(self):
        text = "技能：SQL。用 SQL 汇总每日订单。"
        row = analyze_resume_gaps(text, "用 SQL 取数")[0]
        self.assertEqual(row["简历覆盖状态"], "已覆盖")
        self.assertEqual(row["简历原文"], "用 SQL 汇总每日订单")
        self.assertEqual(generate_suggestions(text, "用 SQL 取数", "t", "u"), [])

    def test_suggestions_cite_source_and_templates_depend_on_group(self):
        jd, resume = "需要 SQL、A/B 实验", "技能：SQL"
        generic = generate_suggestions(resume, jd, "t", "u", "A")
        targeted = generate_suggestions(resume, jd, "t", "u", "B")
        self.assertEqual([item["matched_keyword"] for item in targeted], ["A/B 实验", "SQL"])
        self.assertEqual(targeted[1]["original_expression"], "技能：SQL")
        self.assertEqual(targeted[0]["original_expression"], "")
        self.assertEqual(targeted[0]["jd_evidence"], jd)
        self.assertNotEqual(targeted[0]["revised_expression"], generic[0]["revised_expression"])
        self.assertIn("【", targeted[0]["revised_expression"])

    def test_report_distinguishes_open_decisions_and_keeps_input_literal(self):
        jd, resume = "SQL、Python、RAG", "SQL\n```\n<div>example</div>"
        suggestions = generate_suggestions(resume, jd, "t", "u")
        suggestions[0]["status"] = "adopted"
        suggestions[1]["status"] = "rejected"
        report = build_report_markdown(resume, jd, suggestions, 0, 100)
        self.assertIn("33%（1/3 项）", report)
        self.assertIn("已采纳 1 条，未采纳 1 条，待处理 1 条", report)
        self.assertIn("````text\n" + resume + "\n````", report)
        self.assertNotIn("100%", report)


if __name__ == "__main__":
    unittest.main()
