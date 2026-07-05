from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.generate_mock_data import main as generate_mock_data
from logic.metrics import adoption_driver_tables, calculate_funnel, north_star_metrics, prompt_ab_metrics
from logic.resume_analyzer import (
    analyze_resume_gaps,
    build_report_markdown,
    calculate_match_score,
    categorize_keywords,
    extract_jd_keywords,
    generate_suggestions,
    stable_id,
)


DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
SUGGESTION_PROVIDER = "mock"
PLOT_CONFIG = {"displayModeBar": False}
REJECT_REASONS = ["建议太泛", "不符合目标岗位", "表达不自然", "已体现过", "不想修改"]

SAMPLE_RESUME = """项目经历：AI 简历优化助手数据分析项目
- 设计用户行为分析框架，分析用户从上传简历到生成建议的转化路径。
- 使用 Python 处理示例数据，并用可视化图表展示分析结果。
- 输出产品优化建议，帮助提升用户使用体验。

项目经历：校园活动数据复盘
- 整理活动报名和参与数据，分析不同渠道的转化情况。
- 使用 Excel 制作活动复盘表，向团队汇报数据结论。

技能：Python、SQL、Excel、数据分析、可视化。"""

SAMPLE_JD = """AI 产品经理岗位职责：
1. 负责 AI 工具类产品的需求分析、用户路径设计、MVP 方案和产品效果评估；
2. 结合用户场景设计 Prompt 策略，评估 AI 输出质量和用户采纳反馈；
3. 熟悉数据分析、指标体系、A/B 实验、用户增长和产品优化；
4. 了解大模型、Prompt、RAG、Vibe Coding 等 AI 产品能力边界；
5. 能推动从方案验证到迭代路线图的产品闭环。"""


st.set_page_config(page_title="AI 简历优化助手 MVP", page_icon="AI", layout="wide")


def ensure_data() -> None:
    required = ["users.csv", "resume_tasks.csv", "events.csv", "suggestions.csv", "feedback.csv"]
    if not all((DATA_DIR / name).exists() for name in required):
        generate_mock_data()


@st.cache_data
def load_tables() -> Dict[str, pd.DataFrame]:
    ensure_data()
    tables = {
        "users": pd.read_csv(DATA_DIR / "users.csv"),
        "resume_tasks": pd.read_csv(DATA_DIR / "resume_tasks.csv"),
        "events": pd.read_csv(DATA_DIR / "events.csv"),
        "suggestions": pd.read_csv(DATA_DIR / "suggestions.csv"),
        "feedback": pd.read_csv(DATA_DIR / "feedback.csv"),
    }
    tasks = tables["resume_tasks"]
    if "current_match_score" not in tasks.columns:
        tasks["current_match_score"] = tasks["optimized_match_score"] if "optimized_match_score" in tasks.columns else tasks["original_match_score"]
    for column, default in [("adopted_count", 0), ("rejected_count", 0), ("pending_count", 0)]:
        if column not in tasks.columns:
            tasks[column] = default
    suggestions = tables["suggestions"]
    if "status" not in suggestions.columns:
        suggestions["status"] = suggestions["adopted"].map({True: "adopted", False: "rejected"}).fillna("pending")
    for column in ["original_expression", "revised_expression"]:
        if column not in suggestions.columns:
            suggestions[column] = ""
    return tables


def init_state() -> None:
    defaults = {
        "pm_user_id": "pm_demo_user",
        "pm_task_id": None,
        "pm_session_id": stable_id("pm_session", datetime.now().isoformat(timespec="seconds")),
        "pm_resume_text": SAMPLE_RESUME,
        "pm_jd_text": SAMPLE_JD,
        "pm_user_type": "应届生",
        "pm_prompt_group": "B",
        "pm_suggestions": [],
        "pm_event_log": [],
        "pm_visited": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.pm_visited:
        log_event("visit_product")
        st.session_state.pm_visited = True


def log_event(event_name: str, suggestion_id: str | None = None, extra: str | None = None) -> None:
    st.session_state.pm_event_log.append(
        {
            "event_id": f"pm_e_{len(st.session_state.pm_event_log) + 1:04d}",
            "user_id": st.session_state.pm_user_id,
            "task_id": st.session_state.pm_task_id or "pending_task",
            "session_id": st.session_state.pm_session_id,
            "event_time": datetime.now().isoformat(timespec="seconds"),
            "event_name": event_name,
            "suggestion_id": suggestion_id,
            "prompt_group": st.session_state.pm_prompt_group,
            "extra": extra,
        }
    )


def decode_uploaded_file(uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    raw = uploaded_file.read()
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def load_ai_pm_sample() -> None:
    st.session_state.pm_resume_text = SAMPLE_RESUME
    st.session_state.pm_jd_text = SAMPLE_JD
    st.session_state.pm_user_type = "应届生"
    st.session_state.pm_prompt_group = "B"
    st.session_state.pm_suggestions = []
    st.session_state.pm_task_id = None
    log_event("load_ai_pm_sample")


def suggestion_counts() -> Dict[str, int]:
    suggestions = st.session_state.pm_suggestions
    adopted = sum(1 for item in suggestions if item.get("status") == "adopted")
    rejected = sum(1 for item in suggestions if item.get("status") == "rejected")
    pending = sum(1 for item in suggestions if item.get("status", "pending") == "pending")
    return {"total": len(suggestions), "adopted": adopted, "rejected": rejected, "pending": pending, "processed": adopted + rejected}


def current_scores() -> Dict[str, int]:
    original = calculate_match_score(st.session_state.pm_resume_text, st.session_state.pm_jd_text)
    counts = suggestion_counts()
    current = min(100, original + counts["adopted"] * 7)
    potential = max(0, min(100, original + counts["total"] * 7) - current)
    return {"original": original, "current": current, "potential": potential}


def enrich_suggestions(suggestions: List[Dict[str, object]]) -> List[Dict[str, object]]:
    enriched = []
    for item in suggestions:
        keywords = item.get("matched_jd_keywords") or [item.get("matched_keyword", "JD 关键词")]
        keyword_text = "、".join(str(keyword) for keyword in keywords)
        row = dict(item)
        row.setdefault("reject_reason", "")
        row["modification_reason"] = (
            f"这条建议绑定了目标 JD 中的 {keyword_text} 要求，"
            "通过补充场景、动作和结果，帮助简历表达更贴合目标岗位。"
        )
        if not row.get("original_expression"):
            row["original_expression"] = f"简历中对“{keyword_text}”的表达不够明确，缺少岗位匹配解释。"
        if not row.get("revised_expression"):
            row["revised_expression"] = row.get("revised_example", "")
        enriched.append(row)
    return enriched


def set_suggestion_status(index: int, status: str, reason: str | None = None) -> None:
    item = st.session_state.pm_suggestions[index]
    previous = item.get("status", "pending")
    if previous == status and (status != "rejected" or item.get("reject_reason") == reason):
        return
    item["status"] = status
    item["adopted"] = True if status == "adopted" else False if status == "rejected" else None
    if status == "rejected":
        item["reject_reason"] = reason or item.get("reject_reason") or REJECT_REASONS[0]
        log_event("reject_suggestion", suggestion_id=item["suggestion_id"], extra=item["reject_reason"])
    elif status == "adopted":
        item["reject_reason"] = ""
        log_event("adopt_suggestion", suggestion_id=item["suggestion_id"])
    else:
        item["reject_reason"] = ""
        log_event("defer_suggestion", suggestion_id=item["suggestion_id"])


def report_payload() -> tuple[str, str]:
    scores = current_scores()
    report = build_report_markdown(
        resume_text=st.session_state.pm_resume_text,
        jd_text=st.session_state.pm_jd_text,
        suggestions=st.session_state.pm_suggestions,
        original_match_score=scores["original"],
        optimized_match_score=scores["current"],
    )
    task_id = st.session_state.pm_task_id or "pending_task"
    return report, f"resume_optimization_report_{task_id}.md"


def render_metric_card(column, label: str, value: str, help_text: str) -> None:
    column.metric(label, value, help=help_text)
    column.caption(help_text)


STRATEGY_LABELS = {"A": "通用建议型", "B": "JD 匹配型"}
QUALITY_BUCKET_LABELS = {
    "低质量(≤3)": "低质量",
    "中质量(3-4)": "中质量",
    "高质量(>4)": "高质量",
}
FUNNEL_STEP_LABELS = {
    "访问产品": "访问产品",
    "上传简历": "上传简历",
    "上传 JD": "输入目标 JD",
    "生成建议": "生成建议",
    "采纳建议": "采纳建议",
    "导出报告": "导出优化报告",
}


def strategy_label(value: object) -> str:
    return STRATEGY_LABELS.get(str(value), str(value))


def build_prompt_chart_data(metrics: pd.DataFrame) -> pd.DataFrame:
    chart_data = metrics.copy()
    chart_data["生成策略"] = chart_data["prompt_group"].map(strategy_label)
    chart_data["建议采纳率"] = chart_data["adoption_rate"]
    return chart_data


def build_quality_chart_data(metrics: pd.DataFrame) -> pd.DataFrame:
    chart_data = metrics.copy()
    chart_data["建议质量分层"] = chart_data["quality_bucket"].astype(str).replace(QUALITY_BUCKET_LABELS)
    chart_data["建议采纳率"] = chart_data["adoption_rate"]
    return chart_data


def build_funnel_chart_data(funnel: pd.DataFrame) -> pd.DataFrame:
    chart_data = funnel.copy()
    chart_data["用户路径"] = chart_data["step"].replace(FUNNEL_STEP_LABELS)
    chart_data["用户数"] = chart_data["users"]
    return chart_data


def render_header() -> None:
    st.title("AI 简历优化助手 MVP 设计与效果评估")
    st.caption("基于目标岗位 JD 识别简历差距，生成结构化优化建议，并通过采纳、导出和质量评分评估建议效果。")


def render_overview(tables: Dict[str, pd.DataFrame]) -> None:
    users = tables["users"]
    tasks = tables["resume_tasks"]
    events = tables["events"]
    suggestions = tables["suggestions"]
    north_star = north_star_metrics(tasks, events, suggestions)

    st.subheader("项目总览：AI 简历优化助手 MVP")
    st.caption("从用户问题、核心路径和评估指标三个角度说明这个 MVP 的设计思路。")
    cols = st.columns(4)
    render_metric_card(cols[0], "目标用户", "求职用户", "重点关注应届生、实习生、转行用户。")
    render_metric_card(cols[1], "核心任务路径", "5 步", "上传简历、解析 JD、生成建议、采纳反馈、导出优化报告。")
    render_metric_card(cols[2], "示例优化任务", f"{len(tasks):,}", "演示样本数据中的优化任务数量。")
    render_metric_card(cols[3], "有效优化完成率", f"{north_star['effective_completion_rate']:.1%}", "导出优化报告且至少采纳 1 条建议的任务占比。")

    st.markdown("#### 用户痛点 -> 产品功能 -> AI 能力 -> 评估指标")
    pm_map = pd.DataFrame(
        [
            {"用户痛点": "不知道如何根据 JD 修改简历", "产品功能": "JD 解析与关键词分类", "AI 能力": "识别岗位能力要求与简历覆盖情况", "评估指标": "JD 关键词覆盖率、匹配分提升"},
            {"用户痛点": "AI 建议泛泛而谈，不知道怎么改", "产品功能": "结构化建议卡片", "AI 能力": "输出问题定位、原文、改写、理由、关键词", "评估指标": "建议采纳率、具体性、可执行性"},
            {"用户痛点": "不信任 AI 建议是否贴合目标岗位", "产品功能": "JD 关键词绑定解释", "AI 能力": "把建议和岗位关键词显式关联", "评估指标": "JD 匹配度、可信度/可解释性"},
            {"用户痛点": "采纳建议后不知道下一步做什么", "产品功能": "导出优化报告与下一步引导", "AI 能力": "沉淀可执行优化清单", "评估指标": "优化报告导出率、有效优化完成率"},
        ]
    )
    st.dataframe(pm_map, use_container_width=True, hide_index=True)

    st.markdown("#### MVP 范围与边界")
    scope = pd.DataFrame(
        [
            {"类别": "当前版本包含", "说明": "简历/JD 输入、规则引擎生成建议、采纳/拒绝/暂不处理反馈、导出优化报告、效果评估看板。"},
            {"类别": "当前版本暂不包含", "说明": "真实大模型接口、登录系统、真实投递追踪、真实面试反馈、商业化能力。"},
            {"类别": "数据说明", "说明": "页面中的行为数据为演示样本数据，用于验证用户路径、指标体系和效果评估框架。"},
            {"类别": "后续扩展", "说明": "接入真实大模型接口、岗位类型模板、用户反馈标注、生成策略模板管理与效果追踪。"},
        ]
    )
    st.dataframe(scope, use_container_width=True, hide_index=True)


def render_product_experience() -> None:
    st.subheader("产品体验：完成一次简历优化")
    st.caption("填写简历和目标 JD 后，系统会生成可处理的优化建议；采纳至少 1 条建议后，可以导出优化报告。")
    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        if st.button("加载 AI 产品岗位示例", use_container_width=True):
            load_ai_pm_sample()
            st.success("已加载 AI 产品岗位示例，可直接点击“生成优化建议”。")
        st.selectbox("用户类型", ["应届生", "实习生", "转行用户"], key="pm_user_type")
        st.radio(
            "生成策略",
            ["A", "B"],
            key="pm_prompt_group",
            horizontal=True,
            format_func=strategy_label,
            help="通用建议型适合基础优化，JD 匹配型会更强调岗位关键词和修改理由。",
        )
        uploaded_file = st.file_uploader("上传简历文件（txt / md）", type=["txt", "md"])
        if uploaded_file is not None:
            st.session_state.pm_resume_text = decode_uploaded_file(uploaded_file)
            log_event("upload_resume")
        st.text_area("简历文本", key="pm_resume_text", height=210)
        st.text_area("目标岗位 JD", key="pm_jd_text", height=210)
        if st.button("生成优化建议", type="primary", use_container_width=True):
            if not st.session_state.pm_resume_text.strip() or not st.session_state.pm_jd_text.strip():
                st.warning("请先填写简历文本和目标岗位 JD。")
            else:
                task_id = stable_id("pm_task", st.session_state.pm_session_id, st.session_state.pm_resume_text, st.session_state.pm_jd_text)
                st.session_state.pm_task_id = task_id
                log_event("upload_resume")
                log_event("upload_jd")
                raw_suggestions = generate_suggestions(
                    resume_text=st.session_state.pm_resume_text,
                    jd_text=st.session_state.pm_jd_text,
                    task_id=task_id,
                    user_id=st.session_state.pm_user_id,
                    prompt_group=st.session_state.pm_prompt_group,
                    suggestion_provider=SUGGESTION_PROVIDER,
                )
                st.session_state.pm_suggestions = enrich_suggestions(raw_suggestions)
                log_event("generate_suggestion")
                st.success(f"已生成 {len(st.session_state.pm_suggestions)} 条结构化建议。")

    with right:
        counts = suggestion_counts()
        scores = current_scores()
        st.markdown("#### 当前任务状态")
        cols = st.columns(2)
        cols[0].metric("当前匹配分", scores["current"])
        cols[1].metric("预计提升空间", f"+{scores['potential']}")
        st.progress(counts["processed"] / counts["total"] if counts["total"] else 0)
        st.caption(f"已处理 {counts['processed']} / {counts['total']} 条；采纳 {counts['adopted']} 条，拒绝 {counts['rejected']} 条，待处理 {counts['pending']} 条。")
        st.markdown("#### 当前 JD 关键词")
        st.write("、".join(extract_jd_keywords(st.session_state.pm_jd_text)))
        report, report_name = report_payload()
        if counts["adopted"] < 1:
            st.info("至少采纳 1 条建议后，可导出优化报告。")
        if st.download_button("导出优化报告", report, file_name=report_name, mime="text/markdown", use_container_width=True, disabled=counts["adopted"] < 1):
            OUTPUT_DIR.mkdir(exist_ok=True)
            (OUTPUT_DIR / report_name).write_text(report, encoding="utf-8")
            log_event("export_report")

    render_suggestion_cards()


def render_suggestion_cards() -> None:
    st.markdown("#### 结构化建议卡片")
    if not st.session_state.pm_suggestions:
        st.info("点击“生成优化建议”后，这里会展示问题定位、绑定 JD 关键词、原文片段、优化后表达、修改理由和用户反馈操作。")
        return

    status_label = {"pending": "待处理", "adopted": "已采纳", "rejected": "已拒绝"}
    for index, item in enumerate(st.session_state.pm_suggestions):
        status = item.get("status", "pending")
        with st.container(border=True):
            top_cols = st.columns([1.2, 1.4, 1])
            top_cols[0].markdown(f"**建议类型：** {item['suggestion_type']}")
            top_cols[1].markdown(f"**绑定 JD 关键词：** {', '.join(item['matched_jd_keywords'])}")
            top_cols[2].markdown(f"**状态：** {status_label[status]}")
            st.markdown(f"**问题定位：** {item['current_problem']}")
            st.markdown(f"**原文片段：** {item.get('original_expression', '')}")
            st.markdown(f"**优化后表达：** {item.get('revised_expression', item.get('revised_example', ''))}")
            st.markdown(f"**修改理由：** {item.get('modification_reason', '')}")

            action_cols = st.columns([1, 1, 1, 3])
            if action_cols[0].button("采纳", key=f"pm_adopt_{item['suggestion_id']}", type="primary" if status == "adopted" else "secondary"):
                set_suggestion_status(index, "adopted")
                st.rerun()
            if action_cols[1].button("拒绝", key=f"pm_reject_{item['suggestion_id']}", type="primary" if status == "rejected" else "secondary"):
                if not item.get("reject_reason"):
                    item["reject_reason"] = REJECT_REASONS[0]
                set_suggestion_status(index, "rejected", reason=item["reject_reason"])
                st.rerun()
            if action_cols[2].button("暂不处理", key=f"pm_defer_{item['suggestion_id']}", type="primary" if status == "pending" else "secondary"):
                set_suggestion_status(index, "pending")
                st.rerun()
            action_cols[3].caption("可根据建议是否适合当前经历选择处理方式，系统会同步更新任务状态。")

            if status == "rejected":
                reason = st.selectbox(
                    "拒绝原因",
                    REJECT_REASONS,
                    index=REJECT_REASONS.index(item.get("reject_reason", REJECT_REASONS[0])) if item.get("reject_reason") in REJECT_REASONS else 0,
                    key=f"pm_reason_{item['suggestion_id']}",
                )
                if reason != item.get("reject_reason"):
                    set_suggestion_status(index, "rejected", reason=reason)
                    st.rerun()

            with st.expander("查看质量评分"):
                score_cols = st.columns(4)
                score_cols[0].metric("具体性", item["specificity_score"])
                score_cols[1].metric("JD 匹配度", item["jd_match_score"])
                score_cols[2].metric("可执行性", item["actionability_score"])
                score_cols[3].metric("可信度/可解释性", item["jd_match_score"])


def render_ai_capability_design() -> None:
    st.subheader("AI 能力设计：从 JD 到结构化建议")
    st.caption("本页说明建议如何生成、如何解释，以及如何评估输出质量。")
    st.caption("当前版本使用规则引擎生成演示结果，保证流程稳定和输出可控；后续可接入真实大模型接口，提升建议生成的灵活性和自然语言表达质量。")
    st.markdown("#### 建议生成流程")
    st.markdown("`JD 输入 -> 关键词识别 -> 简历覆盖判断 -> 缺口分析 -> 结构化建议生成 -> 质量评分 -> 用户反馈`")

    keywords = extract_jd_keywords(st.session_state.pm_jd_text)
    categories = categorize_keywords(keywords)
    cols = st.columns(2)
    for index, (category, values) in enumerate(categories.items()):
        with cols[index % 2]:
            st.markdown(f"**{category}**")
            st.write("、".join(values))

    st.markdown("#### 简历缺口分析")
    st.dataframe(pd.DataFrame(analyze_resume_gaps(st.session_state.pm_resume_text, st.session_state.pm_jd_text)), use_container_width=True, hide_index=True)

    st.markdown("#### AI 输出质量评估体系")
    quality_system = pd.DataFrame(
        [
            {"维度": "具体性", "产品含义": "建议是否定位到具体简历模块、能力点或项目表达", "当前实现": "围绕明确关键词、简历模块和问题定位生成评分"},
            {"维度": "JD 匹配度", "产品含义": "建议是否真正对应目标岗位要求", "当前实现": "B 组 JD 匹配型策略更强调岗位关键词绑定"},
            {"维度": "可执行性", "产品含义": "用户是否能直接照着建议修改简历", "当前实现": "建议包含原文片段、优化后表达和修改理由"},
            {"维度": "可信度/可解释性", "产品含义": "建议是否说明为什么这样修改，是否能绑定目标 JD 关键词", "当前实现": "在建议卡片中展示绑定关键词和修改理由"},
        ]
    )
    st.dataframe(quality_system, use_container_width=True, hide_index=True)

    st.markdown("#### 生成能力扩展设计")
    provider_design = pd.DataFrame(
        [
            {"能力层": "生成引擎", "当前实现": "当前版本使用规则引擎，保证流程稳定和输出可控", "后续扩展": "后续接入真实大模型接口，提升建议生成的灵活性和自然语言表达质量"},
            {"能力层": "生成策略管理", "当前实现": "当前内置通用建议型与 JD 匹配型两类生成策略", "后续扩展": "后续支持生成策略模板管理、版本对比和效果追踪"},
            {"能力层": "输出安全", "当前实现": "当前通过固定规则避免输出虚假经历", "后续扩展": "后续增加隐私脱敏、事实校验和安全提示"},
        ]
    )
    st.dataframe(provider_design, use_container_width=True, hide_index=True)


def render_prompt_strategy(tables: Dict[str, pd.DataFrame]) -> None:
    st.subheader("生成策略对比：通用建议 vs JD 匹配")
    st.caption("本页重点验证：生成策略可以通过建议采纳率、质量评分和优化报告导出转化为可评估的产品指标。")
    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("### 通用建议型")
            st.markdown("**策略目标：** 指出简历问题并给出通用修改建议。")
            st.markdown("**预期优势：** 覆盖广、实现简单、适合冷启动。")
            st.markdown("**潜在问题：** 建议可能偏泛，和目标 JD 绑定不强。")
            st.markdown("**适用场景：** 用户没有明确岗位方向，或只需要基础简历优化。")
    with col_b:
        with st.container(border=True):
            st.markdown("### JD 匹配型")
            st.markdown("**策略目标：** 结合目标 JD 输出问题定位、修改建议和示例改写。")
            st.markdown("**预期优势：** 更贴合岗位要求，用户更容易理解和采纳。")
            st.markdown("**潜在问题：** 对 JD 解析质量更敏感。")
            st.markdown("**适用场景：** 用户有明确目标岗位，希望提升简历与岗位的匹配度。")

    ab = prompt_ab_metrics(tables["resume_tasks"], tables["suggestions"])
    chart_data = build_prompt_chart_data(ab)
    fig_ab = px.bar(
        chart_data,
        x="生成策略",
        y="建议采纳率",
        text_auto=".1%",
        title="不同生成策略的建议采纳率",
        labels={"生成策略": "生成策略", "建议采纳率": "建议采纳率"},
    )
    fig_ab.update_yaxes(tickformat=".0%")
    fig_ab.update_traces(hovertemplate="生成策略=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>")
    st.plotly_chart(fig_ab, use_container_width=True, config=PLOT_CONFIG)
    st.success("演示样本数据显示，JD 匹配型策略的建议采纳率更高，说明用户更愿意采纳能够解释岗位匹配关系的建议。因此后续默认采用 JD 匹配型策略，并在建议卡片中固定展示“绑定 JD 关键词、原文片段、优化后表达、修改理由”。")


def render_core_findings() -> None:
    st.markdown("### 产品复盘卡片")
    rows = [
        {
            "标题": "导出环节流失最高",
            "说明": "用户采纳建议后缺少明确下一步引导，导出动作没有形成足够强的任务完成感。",
            "动作": "用户采纳 1 条建议后展示“生成优化报告”按钮，并说明报告价值。",
        },
        {
            "标题": "JD 匹配型策略采纳率更高",
            "说明": "用户更愿意采纳和岗位要求强相关、解释更清楚的建议。",
            "动作": "默认采用 JD 匹配型策略，并强化 JD 关键词解释。",
        },
        {
            "标题": "高质量建议更容易被采纳",
            "说明": "具体、可执行、能直接改写的建议更容易被接受。",
            "动作": "固定输出“原文片段—优化后表达—修改理由—绑定关键词”的建议结构。",
        },
    ]
    cols = st.columns(3)
    for col, row in zip(cols, rows):
        with col:
            with st.container(border=True):
                st.markdown(f"#### {row['标题']}")
                st.markdown(f"**说明：** {row['说明']}")
                st.markdown(f"**动作：** {row['动作']}")


def render_segment_personas() -> None:
    st.markdown("### 用户分群策略")
    personas = [
        {
            "title": "实习生用户",
            "特点": "简历内容较少，项目表达偏简单。",
            "主要问题": "不知道如何把课程、项目、校园经历转化为岗位相关能力表达。",
            "产品策略": "强化 JD 关键词匹配和示例改写，帮助用户把经历转化成岗位能力表达。",
            "推荐功能": "JD 关键词匹配、示例改写",
        },
        {
            "title": "应届生用户",
            "特点": "项目经历较多，但重点不突出。",
            "主要问题": "经历和岗位能力之间的对应关系不清晰。",
            "产品策略": "提供项目亮点提炼、能力标签绑定和结构化表达建议。",
            "推荐功能": "项目亮点提炼、能力标签绑定",
        },
        {
            "title": "转行用户",
            "特点": "原经历与目标岗位差异较大。",
            "主要问题": "用户不确定哪些能力可以迁移到目标岗位。",
            "产品策略": "增加可迁移能力识别、岗位差距分析和转行动机表达建议。",
            "推荐功能": "可迁移能力识别、岗位差距分析",
        },
    ]
    cols = st.columns(3)
    for col, persona in zip(cols, personas):
        with col:
            with st.container(border=True):
                st.markdown(f"#### {persona['title']}")
                st.markdown(f"**特点：** {persona['特点']}")
                st.markdown(f"**主要问题：** {persona['主要问题']}")
                st.markdown(f"**产品策略：** {persona['产品策略']}")
                st.markdown(f"**推荐功能：** {persona['推荐功能']}")


def render_directional_observations(tables: Dict[str, pd.DataFrame]) -> None:
    tasks = tables["resume_tasks"].copy()
    if "current_match_score" not in tasks.columns:
        tasks["current_match_score"] = tasks.get("optimized_match_score", tasks["original_match_score"])
    tasks["match_score_lift"] = tasks["current_match_score"] - tasks["original_match_score"]
    observations = pd.DataFrame(
        [
            {
                "影响因素": "已采纳建议数",
                "方向性观察": "采纳越多，导出意愿越高",
                "产品含义": "用户看到有效建议后，更愿意完成任务闭环",
                "后续动作": "在用户采纳建议后立即提示导出优化报告",
            },
            {
                "影响因素": "待处理建议数",
                "方向性观察": "待处理越多，导出意愿下降",
                "产品含义": "建议过多会增加决策负担",
                "后续动作": "控制单次建议数量，优先展示高价值建议",
            },
            {
                "影响因素": "匹配分提升",
                "方向性观察": "提升越明显，用户越容易感知价值",
                "产品含义": "用户需要看到优化前后的明确变化",
                "后续动作": "展示匹配分变化和前后对比",
            },
            {
                "影响因素": "生成策略",
                "方向性观察": "JD 匹配型策略表现更好",
                "产品含义": "用户更信任和目标岗位强绑定的建议",
                "后续动作": "默认使用 JD 匹配型策略",
            },
        ]
    )
    st.dataframe(observations, use_container_width=True, hide_index=True)


def render_product_evaluation(tables: Dict[str, pd.DataFrame]) -> None:
    st.subheader("产品效果评估：建议采纳与优化报告导出")
    st.caption("本页重点验证：用户不是只需要生成建议，更需要清晰的下一步引导和可解释的修改理由。")
    users = tables["users"]
    tasks = tables["resume_tasks"]
    events = tables["events"]
    suggestions = tables["suggestions"]
    north_star = north_star_metrics(tasks, events, suggestions)

    cols = st.columns(4)
    render_metric_card(cols[0], "建议采纳率", f"{north_star['suggestion_adoption_rate']:.1%}", "用户是否愿意接受 AI 输出。")
    render_metric_card(cols[1], "优化报告导出率", f"{north_star['report_export_rate']:.1%}", "用户是否完成任务闭环。")
    render_metric_card(cols[2], "有效优化完成率", f"{north_star['effective_completion_rate']:.1%}", "导出优化报告且至少采纳 1 条建议。")
    render_metric_card(cols[3], "示例任务数", f"{len(tasks):,}", "演示样本数据中的任务数量。")

    render_core_findings()

    funnel = build_funnel_chart_data(calculate_funnel(events))
    fig_funnel = px.funnel(
        funnel,
        x="用户数",
        y="用户路径",
        title="核心任务路径漏斗",
        labels={"用户数": "用户数", "用户路径": "用户路径"},
    )
    fig_funnel.update_traces(hovertemplate="用户路径=%{y}<br>用户数=%{x}<extra></extra>")
    st.plotly_chart(fig_funnel, use_container_width=True, config=PLOT_CONFIG)
    st.caption("业务解读：演示样本数据中，主要流失发生在采纳建议之后，说明用户对建议有兴趣，但导出动作还没有形成明确的任务完成感。可落地动作：采纳 1 条建议后前置展示“导出优化报告”按钮，并说明报告价值。")

    drivers = adoption_driver_tables(users, suggestions)
    cols = st.columns(2)
    quality_chart = build_quality_chart_data(drivers["quality"])
    fig_quality = px.bar(
        quality_chart,
        x="建议质量分层",
        y="建议采纳率",
        text_auto=".1%",
        title="不同建议质量下的采纳率",
        labels={"建议质量分层": "建议质量分层", "建议采纳率": "建议采纳率"},
        category_orders={"建议质量分层": ["低质量", "中质量", "高质量"]},
    )
    fig_quality.update_yaxes(tickformat=".0%")
    fig_quality.update_traces(hovertemplate="建议质量=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>")
    cols[0].plotly_chart(fig_quality, use_container_width=True, config=PLOT_CONFIG)
    low_quality_note = "低质量建议样本量不足，当前主要比较中质量与高质量建议的采纳差异。" if (quality_chart["suggestions"] == 0).any() else ""
    cols[0].caption(f"业务解读：建议越具体、越可执行，用户越容易采纳。{low_quality_note} 可落地动作：固定输出“原文片段—优化后表达—修改理由—绑定关键词”的建议结构。")
    prompt_chart = build_prompt_chart_data(drivers["prompt"])
    fig_prompt = px.bar(
        prompt_chart,
        x="生成策略",
        y="建议采纳率",
        text_auto=".1%",
        title="不同生成策略的建议采纳率",
        labels={"生成策略": "生成策略", "建议采纳率": "建议采纳率"},
    )
    fig_prompt.update_yaxes(tickformat=".0%")
    fig_prompt.update_traces(hovertemplate="生成策略=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>")
    cols[1].plotly_chart(fig_prompt, use_container_width=True, config=PLOT_CONFIG)
    cols[1].caption("业务解读：JD 匹配型策略更容易让用户理解建议价值。可落地动作：默认采用 JD 匹配型策略，并在卡片中展示关键词绑定解释。")

    st.markdown("### 导出优化报告转化的方向性观察")
    render_directional_observations(tables)
    render_segment_personas()


def render_iteration_roadmap() -> None:
    st.subheader("迭代路线图：从核心流程到稳定体验")
    st.caption("本页重点说明：每个产品优化方向都需要对应明确的优先级依据和验收指标，而不是只停留在功能堆叠。")
    roadmap = pd.DataFrame(
        [
            {
                "阶段": "P0",
                "优化方向": "解释清楚 AI 建议",
                "功能方案": "JD 关键词绑定解释、前后对比、采纳后下一步引导",
                "优先级依据": "影响建议采纳率，是核心转化前置条件",
                "验收指标": "建议采纳率提升，用户拒绝原因中“建议太泛”占比下降",
            },
            {
                "阶段": "P0",
                "优化方向": "提升导出转化",
                "功能方案": "导出按钮前置、报告价值说明",
                "优先级依据": "当前主要流失发生在导出优化报告前",
                "验收指标": "优化报告导出率提升",
            },
            {
                "阶段": "P1",
                "优化方向": "建立反馈闭环",
                "功能方案": "有用/无用反馈、拒绝原因收集、建议质量反馈",
                "优先级依据": "用于持续优化建议质量",
                "验收指标": "有效反馈率提升，低质量建议占比下降",
            },
            {
                "阶段": "P1",
                "优化方向": "增强人群适配",
                "功能方案": "实习生、应届生、转行用户差异化建议",
                "优先级依据": "不同用户的简历问题和优化目标不同",
                "验收指标": "不同用户类型的有效优化完成率提升",
            },
            {
                "阶段": "P2",
                "优化方向": "接入真实大模型接口",
                "功能方案": "真实 LLM API、生成结果安全校验",
                "优先级依据": "依赖真实模型能力，成本和稳定性需要后期验证",
                "验收指标": "响应稳定性、质量评分、成本可控",
            },
            {
                "阶段": "P2",
                "优化方向": "Prompt 模板管理",
                "功能方案": "岗位模板、Prompt 版本对比、效果追踪",
                "优先级依据": "用于支持不同岗位类型和长期策略优化",
                "验收指标": "不同模板的采纳率和质量评分可追踪",
            },
        ]
    )
    st.dataframe(roadmap, use_container_width=True, hide_index=True)

    st.markdown("#### 风险与边界")
    risk_table = pd.DataFrame(
        [
            {"风险": "建议不准确", "说明": "规则或模型可能给出不符合用户经历的建议", "控制思路": "增加用户反馈、人工标注和安全提示"},
            {"风险": "过度包装简历", "说明": "生成建议可能让表达超过真实经历", "控制思路": "强调基于真实经历改写，不生成虚假经历"},
            {"风险": "隐私问题", "说明": "真实简历包含个人信息", "控制思路": "当前页面不持久化保存用户输入，后续接入真实数据时需脱敏和权限控制"},
            {"风险": "样本代表性不足", "说明": "当前结论基于演示样本数据", "控制思路": "接入真实行为数据后重新验证"},
        ]
    )
    st.dataframe(risk_table, use_container_width=True, hide_index=True)


def main() -> None:
    init_state()
    tables = load_tables()
    render_header()
    tab_overview, tab_experience, tab_capability, tab_prompt, tab_eval, tab_roadmap = st.tabs(
        ["项目总览", "产品体验", "AI 能力设计", "生成策略", "产品效果评估", "迭代路线图"]
    )
    with tab_overview:
        render_overview(tables)
    with tab_experience:
        render_product_experience()
    with tab_capability:
        render_ai_capability_design()
    with tab_prompt:
        render_prompt_strategy(tables)
    with tab_eval:
        render_product_evaluation(tables)
    with tab_roadmap:
        render_iteration_roadmap()


if __name__ == "__main__":
    main()
