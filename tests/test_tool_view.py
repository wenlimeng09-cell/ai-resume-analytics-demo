import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from logic.llm_provider import normalize_suggestions
from logic.resume_analyzer import (
    build_report_markdown,
    calculate_match_score,
    extract_jd_keywords,
    generate_suggestions,
)


def tool_app():
    return AppTest.from_string(
        "from tool_view import render_tool\nrender_tool()", default_timeout=10
    ).run()


def click(app, label):
    return next(button for button in app.button if button.label == label).click().run()


class ToolTests(unittest.TestCase):
    def test_keyword_evidence_and_gaps(self):
        jd = "梳理用户访谈、编写 PRD、定义 MVP 的验收标准。"
        rows = generate_suggestions("整理社团会议纪要。", jd, "t", "u")
        self.assertEqual({i["matched_keyword"] for i in rows}, {"用户研究", "需求分析", "MVP 验证"})
        self.assertTrue(
            all(not i["original_expression"] and "【" in i["revised_expression"] for i in rows)
        )
        self.assertEqual(extract_jd_keywords("负责门店收银和点餐"), [])
        self.assertEqual(calculate_match_score("我不会 SQL，只负责记录意见。", "熟悉 SQL"), 0)
        self.assertEqual(calculate_match_score("使用 Tableau 维护看板。", "要求 Power BI"), 0)

    def test_review_tracks_input_and_decisions(self):
        app = tool_app()
        click(app, "生成诊断")
        score = app.metric[0].value
        self.assertEqual(len(app.get("download_button")), 1)
        click(app, "采纳")
        self.assertEqual(score, app.metric[0].value)
        click(app, "拒绝")
        reason = next(field for field in app.selectbox if "拒绝原因" in field.label)
        self.assertIsNone(reason.value)
        reason.select("并无这段经历").run()
        review = app.session_state["tool_review"]
        report = build_report_markdown(
            review["input"]["resume"], review["input"]["jd"], review["suggestions"], 0, 100
        )
        self.assertIn("已拒绝 1 条", report)
        self.assertIn("待处理 3 条", report)
        self.assertIn("并无这段经历", report)
        self.assertNotIn(review["input"]["resume"], report)
        self.assertNotIn(review["input"]["jd"], report)
        app.text_area(key="tool_input_jd").input("负责门店接待").run()
        self.assertEqual(len(app.get("download_button")), 0)
        click(app, "生成诊断")
        self.assertEqual(app.metric[0].value, "暂无")
        self.assertFalse(app.exception)

    def test_fallback_and_no_quota_overrun(self):
        app = tool_app()
        with patch.dict(
            "os.environ",
            {"DEEPSEEK_API_KEY": "fake", "DEMO_ACCESS_CODE": "虚构", "MAX_LLM_CALLS_PER_SESSION": "1"},
        ), patch("logic.llm_provider.generate_deepseek_suggestions") as generate:

            def fail_request(**kwargs):
                kwargs["config"].before_request()
                kwargs["config"].before_request()
                self.fail("The second request should exceed this session's quota.")

            generate.side_effect = fail_request
            app.radio(key="tool_input_engine").set_value("deepseek").run()
            app.text_input(key="tool_access_code").input("虚构")
            click(app, "解锁模型")
            click(app, "生成诊断")
            self.assertEqual(app.session_state["tool_requests"], 1)
            self.assertEqual(app.session_state["tool_review"]["provider"], "fallback")
            events = app.session_state["tool_events"]
            self.assertEqual(
                [(row["event_name"], row["provider"]) for row in events],
                [
                    ("submit_diagnosis", "deepseek"),
                    ("fallback_to_rules", "fallback"),
                    ("generate_suggestion", "fallback"),
                ],
            )
            self.assertNotIn("虚构", str(events))
            self.assertNotIn("fake", str(events))
            self.assertEqual(len(app.get("download_button")), 1)
            self.assertFalse(app.exception)

    def test_event_log_records_only_fired_actions_and_three_outcomes(self):
        app = tool_app()
        self.assertEqual(app.session_state["tool_events"], [])
        click(app, "生成诊断")
        app.run()  # A rerender must not create another event.
        click(app, "采纳")
        click(app, "拒绝")
        next(field for field in app.selectbox if "拒绝原因" in field.label).select("并无这段经历").run()
        click(app, "暂不处理")
        events = app.session_state["tool_events"]
        self.assertEqual(
            [row["event_name"] for row in events],
            [
                "submit_diagnosis",
                "generate_suggestion",
                "adopt_suggestion",
                "reject_suggestion",
                "defer_suggestion",
            ],
        )
        self.assertEqual(len({row["task_id"] for row in events}), 1)
        self.assertEqual(len({row["suggestion_id"] for row in events[2:5]}), 1)
        self.assertEqual(datetime.fromisoformat(events[0]["time_utc"]).tzinfo, timezone.utc)
        app.text_area(key="tool_input_jd").input("需要 SQL").run()
        app.text_area(key="tool_input_resume").input("使用 SQL 统计商品销量。").run()
        click(app, "生成诊断")
        app.text_area(key="tool_input_jd").input("负责门店接待").run()
        click(app, "生成诊断")
        events = app.session_state["tool_events"]
        self.assertEqual(
            [row["event_name"] for row in events[-4:]],
            [
                "submit_diagnosis",
                "review_covered",
                "submit_diagnosis",
                "unsupported_jd",
            ],
        )
        self.assertEqual(len({row["session_id"] for row in events}), 1)
        self.assertEqual(len({row["task_id"] for row in events}), 3)
        for row in events:
            self.assertEqual(
                set(row),
                {"time_utc", "session_id", "task_id", "event_name", "provider", "suggestion_id"},
            )
            self.assertNotIn("商品销量", str(row))
            self.assertNotIn("门店接待", str(row))
        self.assertFalse(app.exception)

    def test_download_records_one_click_for_current_task(self):
        app = tool_app()
        click(app, "生成诊断")
        button = app.get("download_button")[0]
        if not hasattr(button, "click"):
            self.skipTest("This Streamlit AppTest release has no download button interaction.")
        before = len(app.session_state["tool_events"])
        button.click().run()
        events = app.session_state["tool_events"]
        self.assertEqual(len(events), before + 1)
        self.assertEqual(events[-1]["event_name"], "click_download")
        self.assertEqual(events[-1]["task_id"], app.session_state["tool_review"]["id"])

    def test_model_rejects_invented_work_and_invalid_citation(self):
        resume = "负责记录社团会议、分发会议纪要。"
        jd = "梳理用户访谈、编写 PRD、定义 MVP 的验收标准。"
        row = {
            "resume_section": "项目经历",
            "suggestion_type": "表达",
            "original_expression": "负责记录社团会议",
            "current_problem": "这段原文还可以更具体。",
            "suggestion": "请说明实际承担的工作。",
            "revised_expression": "主导产品从用户访谈、编写 PRD 到定义 MVP 验收标准的全流程。",
            "modification_reason": "对应岗位要求，核对原文能获得什么信息。",
            "matched_jd_keywords": ["PRD"],
        }
        self.assertEqual(normalize_suggestions({"suggestions": [row]}, resume, jd, "B"), [])
        row.update(revised_expression="整理社团会议记录。", original_expression="负责产品访谈")
        self.assertEqual(normalize_suggestions({"suggestions": [row]}, resume, jd, "B"), [])
