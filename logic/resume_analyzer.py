from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Mapping, Sequence


@dataclass(frozen=True)
class KeywordRule:
    keyword: str
    aliases: Sequence[str]
    suggestion_type: str
    resume_section: str
    suggestion_template: str
    example_template: str


KEYWORD_RULES = [
    KeywordRule(
        "SQL", ("sql", "sql server", "mysql", "postgresql", "hivesql", "sparksql"), "技能补强", "技能",
        "写明查的是哪类数据、采用什么统计口径，以及查询结果交给谁使用。",
        "用【实际使用的查询工具】从【数据源】按【口径】统计【指标】，用于【用途】。",
    ),
    KeywordRule(
        "Python", ("python", "pandas", "numpy", "scikit-learn"), "技能补强", "技能",
        "选一项实际做过的数据处理任务，写出输入、处理步骤和输出。",
        "用【实际使用的工具或库】处理【数据】，通过【具体步骤】生成【交付物】。",
    ),
    KeywordRule(
        "Excel", ("excel", "power query", "数据透视表"), "工具表达", "技能",
        "交代工作表处理什么数据，以及你用哪项功能解决了什么问题。",
        "在【实际使用的表格工具】中通过【功能】核算【指标】，供【使用方】核对【事项】。",
    ),
    KeywordRule(
        "数据分析", ("数据分析", "行为分析", "漏斗分析", "归因分析", "专题分析", "data analysis"),
        "项目表达", "项目经历", "选一个业务问题，说明比较了哪些数据、发现了什么。",
        "为回答【业务问题】，按【维度】比较【指标】，观察到【实际发现】。",
    ),
    KeywordRule(
        "A/B 实验", ("a/b", "a/b test", "a/b testing", "ab test", "ab testing", "ab实验", "分流实验", "随机对照"),
        "方法补充", "项目经历", "说明实际参与的实验环节、分组单位和观测指标。有实验结果时再写数值。",
        "在【实验】中负责【本人职责】，按【分组单位】比较【方案】的【指标】。",
    ),
    KeywordRule(
        "用户增长", ("用户增长", "增长分析", "转化漏斗", "转化路径", "用户留存", "拉新", "user growth"),
        "业务表达", "项目经历", "选一个实际跟踪过的用户环节，写清目标人群和判断变化的指标。",
        "跟踪【目标人群】从【环节一】到【环节二】的【指标】，发现【观察结果】。",
    ),
    KeywordRule(
        "指标体系", ("指标体系", "指标口径", "指标监控", "指标定义", "北极星指标", "metric definition"),
        "指标补强", "项目经历", "用一个亲自维护或定义的指标说明口径、统计周期及使用场景。",
        "为【场景】维护【指标】，按【口径与周期】统计，供【使用方】判断【问题】。",
    ),
    KeywordRule(
        "BI", ("bi", "power bi", "powerbi", "tableau", "metabase", "looker", "看板", "dashboard", "business intelligence"),
        "工具表达", "技能", "写出实际使用的看板工具、展示对象和看板支持的业务判断。",
        "用【实际工具】制作【主题】看板，供【使用者】跟踪【指标】。",
    ),
    KeywordRule(
        "Prompt", ("prompt", "prompts", "提示词", "提示工程"), "AI 产品表达", "项目经历",
        "说明提示词解决的任务、你具体调整的内容和核对输出的方式。",
        "围绕【任务】调整【提示词要素】，通过【检查方法】核对【输出】。",
    ),
    KeywordRule(
        "RAG", ("rag", "检索增强", "retrieval augmented generation", "retrieval-augmented generation"),
        "AI 产品表达", "项目经历", "说明你实际参与了哪一步检索或生成，以及如何检查输出有据可查。",
        "在【应用场景】中负责【本人实施的环节】，用【实际方法】核对回答与资料的一致性。",
    ),
    KeywordRule(
        "经营分析", ("经营分析", "经营复盘", "业务复盘", "经营诊断", "商业分析"), "业务表达", "项目经历",
        "写明业务方要做什么决策、选了哪个比较基准，以及结论的使用场景。",
        "为【决策】对照【基准】分析【业务指标】，向【使用方】反馈【观察结果】。",
    ),
    KeywordRule(
        "成本与利润", ("成本分析", "利润分析", "毛利率", "投入产出", "roi"), "指标补强", "项目经历",
        "说清核对的是哪一类成本、收入口径与统计周期，以及本人参与的环节。",
        "按【周期】核对【收入或成本口径】，用于比较【品类或渠道】的【经营指标】。",
    ),
    KeywordRule(
        "运营复盘", ("活动复盘", "活动运营", "渠道运营", "活动效果", "渠道复盘"), "项目表达", "项目经历",
        "选一场实际参与的活动，说明目标、所负责的环节、观察指标及复盘结论。",
        "在【活动】中负责【环节】，跟踪【指标】，复盘时观察到【结果】。",
    ),
    KeywordRule(
        "用户研究", ("用户访谈", "用户研究", "用户调研", "访谈提纲"), "项目表达", "项目经历",
        "说明你实际参与的访谈环节、访谈对象，以及材料如何用于后续决策。",
        "面向【对象】参与【调研环节】，整理【实际发现】，供【使用方】判断【问题】。",
    ),
    KeywordRule(
        "需求分析", ("需求分析", "需求梳理", "需求拆解", "prd", "需求文档"), "方法补充", "项目经历",
        "说明需求来自谁，你如何核对场景和边界，最后交付了什么材料。",
        "围绕【场景】梳理【需求】，输出【本人实际完成的交付物】。",
    ),
    KeywordRule(
        "MVP 验证", ("mvp", "最小可行产品", "方案验证", "原型验证"), "方法补充", "项目经历",
        "说明要验证的用户假设、实际采用的验证方法和验收条件。",
        "为验证【假设】使用【原型或验证方法】，按【验收条件】记录【观察结果】。",
    ),
    KeywordRule(
        "效果评估", ("效果评估", "效果验证", "策略评估", "评估方案"), "方法补充", "项目经历",
        "说明比较对象、观测窗口和评估指标，区分观察差异和可归因的效果。",
        "在【观察窗口】比较【对象】的【指标】，观察到【结果】，并记录【限制】。",
    ),
]

KEYWORD_CATEGORIES = {
    "数据分析能力": ["SQL", "Python", "Excel", "数据分析", "BI"],
    "实验与增长能力": ["A/B 实验", "用户增长", "指标体系"],
    "经营与运营能力": ["经营分析", "成本与利润", "运营复盘"],
    "产品与评估能力": ["用户研究", "需求分析", "MVP 验证", "效果评估", "Prompt", "RAG"],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip().casefold()


def stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.md5(raw).hexdigest()[:10]}"


@lru_cache(maxsize=64)
def _alias_pattern(aliases: tuple[str, ...]) -> re.Pattern:
    alternatives = []
    for alias in sorted(aliases, key=len, reverse=True):
        alias = normalize_text(alias)
        pattern = re.escape(alias).replace(r"\ ", r"\s+").replace("/", r"\s*/\s*")
        if alias[0].isascii() and alias[0].isalnum():
            pattern = r"(?<![a-z0-9_])" + pattern
        if alias[-1].isascii() and alias[-1].isalnum():
            pattern += r"(?![a-z0-9_])"
        alternatives.append(pattern)
    return re.compile("|".join(alternatives))


_NEGATIVE_PREFIX = re.compile(
    r"(?:不要求|无需|不需要|不涉及|不具备|不会|不熟悉|不了解|未掌握|未使用过?|没用过|没有|尚未|暂无|未接触过?|缺乏|无|计划学习|打算学习|计划使用|"
    r"\bno|\bwithout|\bno experience (?:with|in))\s*"
    r"(?:(?:掌握|熟练|熟悉|使用|接触|相关|任何|过)\s*)*"
    r"(?:[a-z0-9+#.-]+(?:\s+[a-z0-9+#.-]+)*\s*(?:、|或|和|与|及|/)\s*)*$"
)
_NEGATIVE_SUFFIX = re.compile(
    r"^\s*(?:并非必需|不作要求|不是必需|经验不足|经验为零|不熟悉|不会|is not required|not required)"
)
_WORK_ACTION = re.compile(
    r"提取|查询|清洗|汇总|统计|核对|核算|处理|制作|生成|设计|搭建|建立|开发|构建|维护|监控|跟踪|"
    r"分析|评估|比较|定位|筛选|计算|验证|拆解|优化|导出|输出|整理|撰写|测试|调整|"
    r"\b(?:built|queried|cleaned|analy[sz]ed|aggregated|designed|tracked|evaluated|created)\b"
)
_LIST_OR_TITLE = re.compile(
    r"^[-*#\s]*(?:(?:(?:专业|相关|个人|技术|职业|核心|软件)?技能|工具栈|项目名称|项目经历)\s*[:|]|"
    r"熟悉|掌握|了解|精通|擅长|熟练掌握|familiar with|skills\s*:)"
)
# When a JD names a specific product, a different tool from the same family is insufficient.
_TOOL_VARIANTS = {
    "SQL": [("mysql",), ("postgresql",), ("sql server",), ("hivesql",), ("sparksql",)],
    "Python": [("pandas",), ("numpy",), ("scikit-learn",)],
    "BI": [("power bi", "powerbi"), ("tableau",), ("metabase",), ("looker",)],
    "Excel": [("power query",), ("数据透视表",)],
}
_CLAUSE_BREAK = re.compile(r"[\r\n。；;！？!?，,]+|(?<=\w)\.(?=\s|$)")


def _clauses(text: str) -> list[str]:
    return [clause.strip() for clause in _CLAUSE_BREAK.split(text or "") if clause.strip()]


def _matching_clause(clauses: Sequence[str], aliases: Sequence[str]) -> tuple[str, bool]:
    """Prefer a matching source clause with a concrete action over a skills listing."""
    first_mention = ""
    if not aliases:
        return "", False
    pattern = _alias_pattern(tuple(aliases))
    for clause in clauses:
        normalized = normalize_text(clause)
        listed = _LIST_OR_TITLE.match(normalized)
        for match in pattern.finditer(normalized):
            # Limit the evidence to nearby words even in unpunctuated pasted paragraphs.
            before = normalized[max(0, match.start() - 80):match.start()]
            after = normalized[match.end():match.end() + 80]
            if _NEGATIVE_PREFIX.search(before) or _NEGATIVE_SUFFIX.match(after):
                continue
            if not first_mention:
                first_mention = clause
            if not listed and _WORK_ACTION.search(before + " " + after):
                return clause, True
    return first_mention, False


def text_contains_any(text: str, aliases: Iterable[str]) -> bool:
    evidence, _ = _matching_clause(_clauses(text), tuple(aliases))
    return bool(evidence)


def extract_jd_keywords(jd_text: str) -> List[str]:
    clauses = _clauses(jd_text)
    return [rule.keyword for rule in KEYWORD_RULES if _matching_clause(clauses, rule.aliases)[0]]


def get_rule(keyword: str) -> KeywordRule | None:
    return next((rule for rule in KEYWORD_RULES if rule.keyword == keyword), None)


def categorize_keywords(keywords: Sequence[str]) -> Dict[str, List[str]]:
    result = {}
    for category, category_keywords in KEYWORD_CATEGORIES.items():
        matched = [keyword for keyword in category_keywords if keyword in keywords]
        if matched:
            result[category] = matched
    categorized = {keyword for group in result.values() for keyword in group}
    remaining = [keyword for keyword in keywords if keyword not in categorized]
    if remaining:
        result["其他能力"] = remaining
    return result


def analyze_resume_gaps(resume_text: str, jd_text: str) -> List[Dict[str, str]]:
    jd_clauses = _clauses(jd_text)
    resume_clauses = _clauses(resume_text)
    rows = []
    for rule in KEYWORD_RULES:
        jd_evidence, _ = _matching_clause(jd_clauses, rule.aliases)
        if not jd_evidence:
            continue
        resume_aliases = rule.aliases
        named_aliases = tuple(
            alias for variant in _TOOL_VARIANTS.get(rule.keyword, [])
            if _matching_clause(jd_clauses, variant)[0] for alias in variant
        )
        if named_aliases:
            # A generic alternative ("Python 或 pandas") also permits other family aliases.
            names = _alias_pattern(named_aliases)
            generic_clauses = [names.sub(" ", normalize_text(clause)) for clause in jd_clauses]
            if not _matching_clause(generic_clauses, (rule.keyword,))[0]:
                resume_aliases = named_aliases
        evidence, has_action = _matching_clause(resume_clauses, resume_aliases)
        if has_action:
            status, priority, advice = "已覆盖", "低", "原文同时提到了相关关键词和工作动作，可核对这句是否准确描述了本人的职责。"
        elif evidence:
            status, priority, advice = "弱覆盖", "中", rule.suggestion_template
        else:
            status, priority = "未覆盖", "高"
            advice = "如果有相关经历，可以按以下方式补充，否则跳过本条。" + rule.suggestion_template
        rows.append({
            "JD 要求": rule.keyword,
            "简历覆盖状态": status,
            "优先级": priority,
            "JD 原文": jd_evidence,
            "简历原文": evidence,
            "优化建议": advice,
        })
    order = {"高": 0, "中": 1, "低": 2}
    return sorted(rows, key=lambda row: order[row["优先级"]])


def calculate_match_score(resume_text: str, jd_text: str) -> int:
    """Percentage of recognized JD keyword groups also mentioned in the resume."""
    gaps = analyze_resume_gaps(resume_text, jd_text)
    if not gaps:
        return 0  # Legacy integer return. The interface shows no score for an unsupported JD.
    mentioned = sum(bool(row["简历原文"]) for row in gaps)
    return round(100 * mentioned / len(gaps))


def generate_suggestions(
    resume_text: str,
    jd_text: str,
    task_id: str,
    user_id: str,
    prompt_group: str = "B",
    suggestion_provider: str = "mock",
    provider_config: Mapping[str, object] | None = None,
) -> List[Dict[str, object]]:
    if suggestion_provider == "deepseek":
        return _generate_deepseek_suggestions(
            resume_text, jd_text, task_id, user_id, prompt_group, provider_config or {}
        )
    if suggestion_provider != "mock":
        raise ValueError(f"Unsupported suggestion provider: {suggestion_provider}")

    suggestions = []
    for gap in analyze_resume_gaps(resume_text, jd_text):
        if gap["简历覆盖状态"] == "已覆盖":
            continue
        keyword = gap["JD 要求"]
        rule = get_rule(keyword)
        evidence = gap["简历原文"]
        if evidence:
            problem = f"简历提到了{keyword}相关内容，规则未在这段文字里识别到具体工作动作。"
        else:
            problem = f"JD 提到了{keyword}，规则未从简历中识别到相应表述。"
        if prompt_group == "A":
            advice = "回顾一段相关经历，按工作背景、本人动作和实际交付物补写一句。有依据时再填写。"
            template = "在【真实场景】中，我负责【本人动作】，交付【实际成果】。"
        else:
            advice = gap["优化建议"]
            template = rule.example_template
        suggestions.append({
            "suggestion_id": stable_id("sg", task_id, user_id, keyword),
            "task_id": task_id,
            "user_id": user_id,
            "prompt_group": prompt_group,
            "resume_section": rule.resume_section,
            "original_expression": evidence,
            "jd_evidence": gap["JD 原文"],
            "current_problem": problem,
            "suggestion": advice,
            "revised_example": template,
            "revised_expression": template,
            "matched_jd_keywords": [keyword],
            "matched_keyword": keyword,
            "suggestion_type": rule.suggestion_type,
            "specificity_score": 3 + int(bool(evidence)),
            "jd_match_score": 4 if gap["JD 原文"] else 1,
            "actionability_score": 4,
            "adopted": None,
            "status": "pending",
        })
    return suggestions


def _generate_deepseek_suggestions(
    resume_text: str,
    jd_text: str,
    task_id: str,
    user_id: str,
    prompt_group: str,
    provider_config: Mapping[str, object],
) -> List[Dict[str, object]]:
    from logic.llm_provider import DeepSeekConfig, generate_deepseek_suggestions

    config = DeepSeekConfig(
        api_key=str(provider_config.get("api_key", "")),
        model=str(provider_config.get("model", "deepseek-v4-flash")),
        timeout_seconds=float(provider_config.get("timeout_seconds", 45.0)),
        max_output_tokens=int(provider_config.get("max_output_tokens", 4000)),
        before_request=provider_config.get("before_request"),
    )
    raw_suggestions = generate_deepseek_suggestions(
        resume_text=resume_text,
        jd_text=jd_text,
        prompt_group=prompt_group,
        config=config,
        client=provider_config.get("client"),
    )
    suggestions: List[Dict[str, object]] = []
    for index, raw in enumerate(raw_suggestions, start=1):
        row = dict(raw)
        keywords = list(row.get("matched_jd_keywords") or [])
        matched_keyword = keywords[0] if keywords else "通用表达"
        row.update(
            {
                "suggestion_id": stable_id("sg", task_id, user_id, matched_keyword, str(index)),
                "task_id": task_id,
                "user_id": user_id,
                "prompt_group": prompt_group,
                "matched_keyword": matched_keyword,
                "adopted": None,
                "status": "pending",
            }
        )
        suggestions.append(row)
    return suggestions


def _report_quote(value: str) -> str:
    # A longer Markdown fence keeps even pasted HTML/Markdown as literal text.
    backticks = re.findall(r"`+", value)
    fence = "`" * max(3, max(map(len, backticks), default=0) + 1)
    return f"{fence}text\n{value}\n{fence}"


def build_report_markdown(
    resume_text: str,
    jd_text: str,
    suggestions: Sequence[Dict[str, object]],
    original_match_score: int,
    optimized_match_score: int,
) -> str:
    """Build from source text. Old score arguments remain available to existing callers."""
    gaps = analyze_resume_gaps(resume_text, jd_text)
    mentioned = sum(bool(row["简历原文"]) for row in gaps)
    coverage = f"{round(100 * mentioned / len(gaps))}%（{mentioned}/{len(gaps)} 项）" if gaps else "无法计算（未识别到支持的 JD 关键词）"
    labels = {"adopted": "已采纳", "rejected": "已拒绝", "pending": "待处理"}
    statuses = []
    for item in suggestions:
        legacy_status = {True: "adopted", False: "rejected"}.get(item.get("adopted"), "pending")
        statuses.append(labels.get(item.get("status", legacy_status), "待处理"))
    lines = [
        "# 简历优化建议报告", "", "## 匹配概览", "",
        f"- 输入简历的 JD 关键词覆盖率 {coverage}",
        "- 覆盖率按当前简历提及的关键词类别数除以 JD 中识别的类别数计算。采纳操作只记录修改意向。",
        f"- 共 {len(suggestions)} 条建议，已采纳 {statuses.count('已采纳')} 条，已拒绝 {statuses.count('已拒绝')} 条，待处理 {statuses.count('待处理')} 条。",
        "", "## 优化建议", "",
    ]
    if not suggestions:
        lines.append("已识别的关键词均有相关工作动作表述。" if gaps and all(row["简历覆盖状态"] == "已覆盖" for row in gaps)
                     else "此次没有可展示的建议。")
    for index, (item, status) in enumerate(zip(suggestions, statuses), start=1):
        keywords = "、".join(item.get("matched_jd_keywords") or []) or "通用表达"
        lines.extend([f"### 建议 {index}（{status}）", "", "对应岗位要求", "", _report_quote(keywords), ""])
        for label, field in (("问题", "current_problem"), ("建议", "suggestion"),
                             ("填写参考", "revised_expression"), ("拒绝原因", "reject_reason")):
            value = str(item.get(field) or "")
            if not value:
                continue
            # A model may repeat the input verbatim in one of its output fields.
            for source in (resume_text, jd_text):
                if source.strip() and len(source.strip()) > 8:
                    value = value.replace(source.strip(), "【原文已省略】")
            lines.extend([label, "", _report_quote(value), ""])
    lines.extend(["## 隐私说明", "", "报告保留修改清单与处理状态。原始简历与岗位描述仅在本次会话中查看。"])
    return "\n".join(lines)
