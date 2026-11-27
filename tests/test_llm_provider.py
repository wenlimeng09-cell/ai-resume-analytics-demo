from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from logic.llm_provider import DeepSeekConfig, LLMProviderError, generate_deepseek_suggestions
from logic.resume_analyzer import build_report_markdown, generate_suggestions


RESUME = "负责用户调研与产品需求分析，整理 Prompt 策略、用户路径和产品效果评估的用户反馈，使用 Python 完成数据整理。"
JD = "负责 AI 产品需求分析、Prompt 策略、用户路径和产品效果评估。"


def suggestion_payload(keywords: list[str] | None = None) -> dict:
    matched_keywords = ["Prompt"] if keywords is None else keywords
    rows = []
    for index, focus in enumerate(("Prompt 策略", "用户路径", "产品效果评估"), start=1):
        rows.append(
            {
                "resume_section": "项目经历",
                "original_expression": "整理 Prompt 策略、用户路径和产品效果评估的用户反馈",
                "current_problem": f"简历对{focus}的表达不够完整。",
                "suggestion": f"补充{focus}的设计过程与产品判断依据。",
                "revised_expression": f"整理与{focus}相关的用户反馈。",
                "modification_reason": f"对应 JD 中的{focus}要求，突出产品设计与效果评估能力。",
                "matched_jd_keywords": matched_keywords,
                "suggestion_type": "AI 产品表达",
            }
        )
    return {"suggestions": rows}


class FakeCompletions:
    def __init__(self, contents: list[str | None]):
        self.contents = contents
        self.calls = 0

    def create(self, **kwargs):
        content = self.contents[min(self.calls, len(self.contents) - 1)]
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def fake_client(contents: list[str | None]):
    completions = FakeCompletions(contents)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


class DeepSeekProviderTest(unittest.TestCase):
    def test_missing_api_key_is_rejected_before_call(self):
        client, completions = fake_client([json.dumps(suggestion_payload(), ensure_ascii=False)])

        with self.assertRaises(LLMProviderError):
            generate_deepseek_suggestions(
                RESUME,
                JD,
                "B",
                DeepSeekConfig(api_key=""),
                client=client,
            )

        self.assertEqual(0, completions.calls)

    def test_valid_json_is_normalized_and_scored(self):
        content = json.dumps(suggestion_payload(), ensure_ascii=False)
        client, completions = fake_client([content])

        result = generate_deepseek_suggestions(
            RESUME,
            JD,
            "B",
            DeepSeekConfig(api_key="test"),
            client=client,
        )

        self.assertEqual(3, len(result))
        self.assertEqual(1, completions.calls)
        self.assertTrue(all(1 <= row["specificity_score"] <= 5 for row in result))
        self.assertTrue(all(row["matched_jd_keywords"] == ["Prompt"] for row in result))

    def test_empty_response_is_retried_once(self):
        content = json.dumps(suggestion_payload(), ensure_ascii=False)
        client, completions = fake_client(["", content])

        result = generate_deepseek_suggestions(
            RESUME,
            JD,
            "B",
            DeepSeekConfig(api_key="test"),
            client=client,
        )

        self.assertEqual(3, len(result))
        self.assertEqual(2, completions.calls)

    def test_new_numeric_claims_are_rejected(self):
        payload = suggestion_payload()
        for row in payload["suggestions"]:
            row["revised_expression"] = "将建议采纳率提升 50%，形成产品迭代闭环。"
        content = json.dumps(payload, ensure_ascii=False)
        client, completions = fake_client([content, content])

        with self.assertRaises(LLMProviderError):
            generate_deepseek_suggestions(
                RESUME,
                JD,
                "B",
                DeepSeekConfig(api_key="test"),
                client=client,
            )

        self.assertEqual(2, completions.calls)

    def test_strategy_a_allows_general_suggestions(self):
        content = json.dumps(suggestion_payload(keywords=[]), ensure_ascii=False)
        client, _ = fake_client([content])

        result = generate_deepseek_suggestions(
            RESUME,
            JD,
            "A",
            DeepSeekConfig(api_key="test"),
            client=client,
        )

        self.assertEqual(3, len(result))
        self.assertTrue(all(row["matched_jd_keywords"] == [] for row in result))

    def test_resume_analyzer_adds_product_state_fields(self):
        content = json.dumps(suggestion_payload(), ensure_ascii=False)
        client, _ = fake_client([content])

        result = generate_suggestions(
            resume_text=RESUME,
            jd_text=JD,
            task_id="task_test",
            user_id="user_test",
            prompt_group="B",
            suggestion_provider="deepseek",
            provider_config={"api_key": "test", "client": client},
        )

        self.assertEqual("pending", result[0]["status"])
        self.assertIsNone(result[0]["adopted"])
        self.assertTrue(result[0]["suggestion_id"].startswith("sg_"))
        self.assertEqual("task_test", result[0]["task_id"])

    def test_export_report_does_not_include_raw_inputs(self):
        suggestions = generate_suggestions(
            resume_text=RESUME,
            jd_text=JD,
            task_id="task_report",
            user_id="user_report",
        )

        report = build_report_markdown(RESUME, JD, suggestions, 40, 60)

        self.assertNotIn(RESUME, report)
        self.assertNotIn(JD, report)
        self.assertIn("隐私说明", report)


if __name__ == "__main__":
    unittest.main()
