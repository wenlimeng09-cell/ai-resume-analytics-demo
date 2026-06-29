from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence


@dataclass(frozen=True)
class KeywordRule:
    keyword: str
    aliases: Sequence[str]
    suggestion_type: str
    resume_section: str
    problem_template: str
    suggestion_template: str
    example_template: str


KEYWORD_RULES: List[KeywordRule] = [
    KeywordRule(
        keyword="SQL",
        aliases=("sql", "mysql", "hive", "查询", "取数"),
        suggestion_type="技能补强",
        resume_section="技能",
        problem_template="JD 强调 {keyword}，但简历中对数据查询或取数能力表达不足。",
        suggestion_template="补充你使用 {keyword} 完成数据提取、清洗或指标计算的经历，并写清业务场景和结果。",
        example_template="使用 {keyword} 搭建用户行为数据查询逻辑，完成核心漏斗指标口径校验，支持产品优化决策。",
    ),
    KeywordRule(
        keyword="Python",
        aliases=("python", "pandas", "numpy", "sklearn", "脚本"),
        suggestion_type="技能补强",
        resume_section="技能",
        problem_template="JD 提到 {keyword}，但简历没有充分体现自动化分析或数据处理能力。",
        suggestion_template="增加使用 {keyword} 清洗数据、构建分析脚本或自动化报表的项目描述。",
        example_template="使用 {keyword} 和 pandas 完成用户行为日志清洗、指标计算和可视化数据准备，提升分析效率。",
    ),
    KeywordRule(
        keyword="数据分析",
        aliases=("数据分析", "分析", "洞察", "归因"),
        suggestion_type="项目表达",
        resume_section="项目经历",
        problem_template="JD 关注 {keyword}，但简历中的分析过程和业务结论还不够完整。",
        suggestion_template="把项目描述改成“问题-指标-分析-结论-动作”的结构，突出你的分析闭环。",
        example_template="围绕简历优化路径建立漏斗和采纳指标，定位建议采纳环节流失，并提出结构化建议展示方案。",
    ),
    KeywordRule(
        keyword="A/B 实验",
        aliases=("a/b", "ab test", "实验", "对照组", "实验组"),
        suggestion_type="方法补充",
        resume_section="项目经历",
        problem_template="JD 出现 {keyword}，但简历没有体现实验设计或效果评估能力。",
        suggestion_template="补充实验分组、核心指标和判断标准，说明你如何比较不同方案效果。",
        example_template="设计 A/B 实验比较通用建议型 Prompt 与 JD 匹配型 Prompt，评估建议采纳率和报告导出率差异。",
    ),
    KeywordRule(
        keyword="用户增长",
        aliases=("用户增长", "增长", "转化", "拉新", "活跃"),
        suggestion_type="业务表达",
        resume_section="项目经历",
        problem_template="JD 提到 {keyword}，但简历没有清楚展示你如何分析用户路径和转化问题。",
        suggestion_template="增加用户路径、关键转化指标和优化动作，让经历更贴近增长或运营分析岗位。",
        example_template="拆解访问、上传简历、生成建议、采纳建议和导出报告路径，识别核心流失环节并提出优化方案。",
    ),
    KeywordRule(
        keyword="指标体系",
        aliases=("指标体系", "指标", "口径", "北极星"),
        suggestion_type="指标补强",
        resume_section="项目经历",
        problem_template="JD 强调 {keyword}，但简历对指标定义和分析口径呈现不足。",
        suggestion_template="补充你设计的核心指标、计算口径和业务用途。",
        example_template="构建覆盖漏斗转化、建议采纳、Prompt A/B、建议质量和用户分群的指标体系。",
    ),
    KeywordRule(
        keyword="BI",
        aliases=("bi", "tableau", "power bi", "looker", "看板", "dashboard", "可视化"),
        suggestion_type="工具表达",
        resume_section="技能",
        problem_template="JD 提到 {keyword} 或看板能力，但简历中可视化交付物不够突出。",
        suggestion_template="写明你使用的看板工具、展示的图表和服务的业务问题。",
        example_template="使用 Streamlit 和 Plotly 搭建本地分析看板，展示漏斗、A/B 实验、用户分群和建议质量分析。",
    ),
    KeywordRule(
        keyword="Prompt",
        aliases=("prompt", "提示词", "大模型", "llm"),
        suggestion_type="AI 产品表达",
        resume_section="项目经历",
        problem_template="JD 关注 {keyword}，但简历没有体现 AI 生成逻辑或 Prompt 评估方法。",
        suggestion_template="补充 Prompt 分组、生成策略和建议质量评估维度。",
        example_template="设计通用建议型与 JD 匹配型 Prompt，对比建议采纳率、导出率和平均质量评分。",
    ),
    KeywordRule(
        keyword="RAG",
        aliases=("rag", "检索增强", "知识库", "向量"),
        suggestion_type="AI 产品表达",
        resume_section="项目经历",
        problem_template="JD 提到 {keyword}，但简历尚未展示相关 AI 产品理解。",
        suggestion_template="如果有相关经历，可补充知识检索、上下文匹配或候选内容召回逻辑；没有则避免硬写，改为说明预留扩展方向。",
        example_template="预留 API provider 与知识库扩展接口，后续可接入 RAG 生成更贴合 JD 的简历改写建议。",
    ),
]

DEFAULT_KEYWORDS = ("SQL", "Python", "数据分析", "指标体系", "A/B 实验")

KEYWORD_CATEGORIES = {
    "数据分析能力": ["SQL", "Python", "数据分析", "BI"],
    "实验与增长能力": ["A/B 实验", "用户增长", "指标体系"],
    "AI 产品能力": ["Prompt", "RAG"],
    "业务理解能力": ["用户增长", "产品优化", "指标体系"],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.md5(raw).hexdigest()[:10]}"


def text_contains_any(text: str, aliases: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(alias.lower() in normalized for alias in aliases)


def extract_jd_keywords(jd_text: str) -> List[str]:
    found = [rule.keyword for rule in KEYWORD_RULES if text_contains_any(jd_text, rule.aliases)]
    if found:
        return found
    return list(DEFAULT_KEYWORDS[:3])


def get_rule(keyword: str) -> KeywordRule | None:
    for rule in KEYWORD_RULES:
        if rule.keyword == keyword:
            return rule
    return None


def categorize_keywords(keywords: Sequence[str]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for category, category_keywords in KEYWORD_CATEGORIES.items():
        matched = [keyword for keyword in category_keywords if keyword in keywords]
        if matched:
            result[category] = matched
    uncategorized = [keyword for keyword in keywords if not any(keyword in values for values in KEYWORD_CATEGORIES.values())]
    if uncategorized:
        result["其他能力"] = uncategorized
    return result


def analyze_resume_gaps(resume_text: str, jd_text: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    resume_length = len(resume_text or "")
    for keyword in extract_jd_keywords(jd_text):
        rule = get_rule(keyword)
        if not rule:
            continue
        covered = text_contains_any(resume_text, rule.aliases)
        if covered and resume_length >= 240:
            status = "已覆盖"
            priority = "低"
            advice = "已覆盖该能力，可继续补充量化结果或业务影响。"
        elif covered:
            status = "弱覆盖"
            priority = "中"
            advice = rule.suggestion_template.format(keyword=keyword)
        else:
            status = "未覆盖"
            priority = "高"
            advice = rule.suggestion_template.format(keyword=keyword)
        rows.append(
            {
                "JD 要求": keyword,
                "简历覆盖状态": status,
                "优先级": priority,
                "优化建议": advice,
            }
        )
    priority_order = {"高": 0, "中": 1, "低": 2}
    return sorted(rows, key=lambda row: priority_order[row["优先级"]])


def calculate_match_score(resume_text: str, jd_text: str) -> int:
    jd_keywords = extract_jd_keywords(jd_text)
    if not jd_keywords:
        return 0
    covered = 0
    for rule in KEYWORD_RULES:
        if rule.keyword in jd_keywords and text_contains_any(resume_text, rule.aliases):
            covered += 1
    return int(round(covered / len(jd_keywords) * 100))


def generate_suggestions(
    resume_text: str,
    jd_text: str,
    task_id: str,
    user_id: str,
    prompt_group: str = "B",
    suggestion_provider: str = "mock",
) -> List[Dict[str, object]]:
    if suggestion_provider != "mock":
        raise NotImplementedError("API provider is reserved for future model integration.")

    jd_keywords = extract_jd_keywords(jd_text)
    suggestions: List[Dict[str, object]] = []

    for rule in KEYWORD_RULES:
        if rule.keyword not in jd_keywords:
            continue

        covered = text_contains_any(resume_text, rule.aliases)
        weak_expression = covered and len(resume_text) < 240
        if covered and not weak_expression:
            continue

        jd_match_score = 5 if prompt_group == "B" else 3
        specificity_score = 4 if covered else 5
        actionability_score = 5 if rule.resume_section in ("技能", "项目经历") else 4
        suggestion_id = stable_id("sg", task_id, user_id, rule.keyword)

        suggestions.append(
            {
                "suggestion_id": suggestion_id,
                "task_id": task_id,
                "user_id": user_id,
                "prompt_group": prompt_group,
                "resume_section": rule.resume_section,
                "original_expression": _original_expression_for(rule.keyword, covered),
                "current_problem": rule.problem_template.format(keyword=rule.keyword),
                "suggestion": rule.suggestion_template.format(keyword=rule.keyword),
                "revised_example": rule.example_template.format(keyword=rule.keyword),
                "revised_expression": rule.example_template.format(keyword=rule.keyword),
                "matched_jd_keywords": [rule.keyword],
                "matched_keyword": rule.keyword,
                "suggestion_type": rule.suggestion_type,
                "specificity_score": specificity_score,
                "jd_match_score": jd_match_score,
                "actionability_score": actionability_score,
                "adopted": None,
                "status": "pending",
            }
        )

    if len(suggestions) < 3:
        suggestions.extend(
            _fallback_suggestions(
                resume_text=resume_text,
                task_id=task_id,
                user_id=user_id,
                prompt_group=prompt_group,
                existing_keywords={item["matched_keyword"] for item in suggestions},
            )
        )

    return suggestions[:6]


def _fallback_suggestions(
    resume_text: str,
    task_id: str,
    user_id: str,
    prompt_group: str,
    existing_keywords: set,
) -> List[Dict[str, object]]:
    fallback_rules = [
        ("量化结果", "项目经历", "项目表达", "简历中的项目结果还不够量化。", "为项目补充转化率、效率、采纳率或覆盖用户数等量化结果。", "将“完成数据分析”改为“搭建漏斗看板并定位核心流失环节，推动建议采纳率优化”。"),
        ("业务闭环", "项目经历", "业务表达", "简历对业务问题、分析过程和优化动作的闭环表达不足。", "按“业务问题-指标拆解-分析发现-优化建议”重写项目描述。", "围绕 AI 简历优化流程拆解用户路径，基于模拟日志评估采纳行为并提出产品迭代方向。"),
        ("工具栈", "技能", "工具表达", "简历没有集中展示本项目使用的分析和可视化工具。", "在技能或项目中补充 Python、Pandas、Streamlit、Plotly 等工具。", "使用 Python、Pandas 和 Plotly 完成数据清洗、指标计算和 Streamlit 本地看板搭建。"),
    ]
    rows: List[Dict[str, object]] = []
    for keyword, section, suggestion_type, problem, suggestion, example in fallback_rules:
        if keyword in existing_keywords:
            continue
        rows.append(
            {
                "suggestion_id": stable_id("sg", task_id, user_id, keyword),
                "task_id": task_id,
                "user_id": user_id,
                "prompt_group": prompt_group,
                "resume_section": section,
                "original_expression": f"简历中对“{keyword}”的表达不够具体，缺少场景、动作或结果。",
                "current_problem": problem,
                "suggestion": suggestion,
                "revised_example": example,
                "revised_expression": example,
                "matched_jd_keywords": [keyword],
                "matched_keyword": keyword,
                "suggestion_type": suggestion_type,
                "specificity_score": 4,
                "jd_match_score": 4 if prompt_group == "B" else 3,
                "actionability_score": 5,
                "adopted": None,
                "status": "pending",
            }
        )
    return rows


def _original_expression_for(keyword: str, covered: bool) -> str:
    if covered:
        return f"简历中已提到“{keyword}”，但表达偏概括，缺少业务场景、分析动作或结果。"
    return f"简历中暂未明确体现“{keyword}”相关能力。"


def build_report_markdown(
    resume_text: str,
    jd_text: str,
    suggestions: Sequence[Dict[str, object]],
    original_match_score: int,
    optimized_match_score: int,
) -> str:
    lines = [
        "# AI 简历优化建议报告",
        "",
        "## 匹配度概览",
        "",
        f"- 优化前模拟匹配分：{original_match_score}",
        f"- 优化后模拟匹配分：{optimized_match_score}",
        f"- 建议总数：{len(suggestions)}",
        f"- 已采纳建议数：{sum(1 for item in suggestions if item.get('adopted') is True)}",
        "",
        "## 优化建议",
        "",
    ]
    for index, item in enumerate(suggestions, start=1):
        status = "已采纳" if item.get("adopted") is True else "未采纳"
        keywords = ", ".join(item.get("matched_jd_keywords") or [item.get("matched_keyword", "")])
        lines.extend(
            [
                f"### {index}. {item['suggestion_type']}（{status}）",
                "",
                f"- 匹配 JD 关键词：{keywords}",
                f"- 简历模块：{item['resume_section']}",
                f"- 问题定位：{item['current_problem']}",
                f"- 修改建议：{item['suggestion']}",
                f"- 原表达：{item.get('original_expression', '')}",
                f"- 优化后表达：{item.get('revised_expression', item.get('revised_example', ''))}",
                f"- 示例改写：{item['revised_example']}",
                f"- 质量评分：具体性 {item['specificity_score']} / JD 匹配度 {item['jd_match_score']} / 可执行性 {item['actionability_score']}",
                "",
            ]
        )
    lines.extend(["## 原始输入摘要", "", "### JD", "", jd_text[:1200], "", "### 简历", "", resume_text[:1200]])
    return "\n".join(lines)
