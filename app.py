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
from logic.metrics import (
    adoption_by_dimension,
    adoption_driver_tables,
    build_task_feature_table,
    calculate_funnel,
    chi_square_for_prompt_adoption,
    export_factor_table,
    export_rate_by_adopted_count,
    export_rate_by_lift,
    export_rate_by_pending_count,
    indicator_tree,
    north_star_metrics,
    optimization_priority_matrix,
    prompt_ab_metrics,
    quality_adoption_relation,
    quality_dimension_impact,
    segment_strategy_table,
    suggestion_summary,
    user_segment_metrics,
)
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

SAMPLE_RESUME = """项目经历：AI 简历优化助手数据分析项目
- 设计用户行为分析框架，分析用户从上传简历到生成建议的转化路径。
- 使用 Python 处理模拟数据，并用可视化图表展示分析结果。
- 输出产品优化建议，帮助提升用户使用体验。

技能：Excel、Python、基础 SQL、数据可视化。"""

SAMPLE_JD = """岗位职责：
1. 负责 AI 产品用户行为数据分析，搭建指标体系和转化漏斗；
2. 使用 SQL / Python 完成数据清洗、看板搭建和专题分析；
3. 参与 Prompt 优化、A/B 实验设计和建议质量评估；
4. 输出用户增长和产品优化建议。

任职要求：
熟悉数据分析方法，理解 BI 看板、A/B 实验、用户增长、Prompt 或 RAG 相关应用。"""


st.set_page_config(page_title="AI 简历优化助手 Demo", page_icon="AI", layout="wide")


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
    for column, default in [("rejected_count", 0), ("pending_count", 0), ("adopted_count", 0)]:
        if column not in tasks.columns:
            tasks[column] = default
    events = tables["events"]
    for column in ["suggestion_id", "prompt_group"]:
        if column not in events.columns:
            events[column] = None
    suggestions = tables["suggestions"]
    if "status" not in suggestions.columns:
        suggestions["status"] = suggestions["adopted"].map({True: "adopted", False: "rejected"}).fillna("pending")
    for column in ["original_expression", "revised_expression"]:
        if column not in suggestions.columns:
            suggestions[column] = ""
    return tables


def init_state() -> None:
    defaults = {
        "demo_user_id": "demo_user",
        "demo_task_id": None,
        "demo_session_id": stable_id("session", datetime.now().isoformat(timespec="seconds")),
        "resume_text": SAMPLE_RESUME,
        "jd_text": SAMPLE_JD,
        "prompt_group": "B",
        "user_type": "应届生",
        "suggestions": [],
        "event_log": [],
        "last_uploaded_name": None,
        "visited": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.visited:
        log_event("visit_product")
        st.session_state.visited = True


def log_event(event_name: str, suggestion_id: str | None = None) -> None:
    st.session_state.event_log.append(
        {
            "event_id": f"demo_e_{len(st.session_state.event_log) + 1:04d}",
            "user_id": st.session_state.demo_user_id,
            "task_id": st.session_state.demo_task_id or "pending_task",
            "session_id": st.session_state.demo_session_id,
            "event_time": datetime.now().isoformat(timespec="seconds"),
            "event_name": event_name,
            "suggestion_id": suggestion_id,
            "prompt_group": st.session_state.prompt_group,
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


def suggestion_counts() -> Dict[str, int]:
    suggestions = st.session_state.suggestions
    adopted = sum(1 for item in suggestions if item.get("status") == "adopted")
    rejected = sum(1 for item in suggestions if item.get("status") == "rejected")
    pending = sum(1 for item in suggestions if item.get("status", "pending") == "pending")
    return {
        "total": len(suggestions),
        "adopted": adopted,
        "rejected": rejected,
        "pending": pending,
        "processed": adopted + rejected,
    }


def current_scores() -> Dict[str, int]:
    original = calculate_match_score(st.session_state.resume_text, st.session_state.jd_text)
    counts = suggestion_counts()
    current = min(100, original + counts["adopted"] * 7)
    potential = max(0, min(100, original + counts["total"] * 7) - current)
    return {"original": original, "current": current, "potential": potential}


def set_suggestion_status(index: int, status: str) -> None:
    item = st.session_state.suggestions[index]
    previous = item.get("status", "pending")
    if previous == status:
        return
    item["status"] = status
    item["adopted"] = True if status == "adopted" else False if status == "rejected" else None
    event_name = "adopt_suggestion" if status == "adopted" else "reject_suggestion"
    log_event(event_name, suggestion_id=item["suggestion_id"])


def report_payload() -> tuple[str, str]:
    scores = current_scores()
    report = build_report_markdown(
        resume_text=st.session_state.resume_text,
        jd_text=st.session_state.jd_text,
        suggestions=st.session_state.suggestions,
        original_match_score=scores["original"],
        optimized_match_score=scores["current"],
    )
    task_id = st.session_state.demo_task_id or "pending_task"
    return report, f"AI简历优化建议报告_{task_id}.md"


def render_export_button(key: str, label: str = "导出优化建议报告") -> None:
    disabled = not st.session_state.suggestions
    report, report_name = report_payload()
    if st.download_button(
        label,
        report,
        file_name=report_name,
        mime="text/markdown",
        use_container_width=True,
        disabled=disabled,
        key=key,
    ):
        OUTPUT_DIR.mkdir(exist_ok=True)
        (OUTPUT_DIR / report_name).write_text(report, encoding="utf-8")
        log_event("export_report")


def render_header() -> None:
    st.title("AI 简历优化助手用户行为分析与效果评估作品集")
    st.caption("当前项目为作品集 Demo，基于模拟产品日志展示 AI 简历优化产品的用户路径、建议采纳机制和数据分析方法，不涉及真实用户隐私数据。")


def render_portfolio_overview(tables: Dict[str, pd.DataFrame]) -> None:
    users = tables["users"]
    tasks = tables["resume_tasks"]
    events = tables["events"]
    suggestions = tables["suggestions"]
    north_star = north_star_metrics(tasks, events, suggestions)

    with st.container(border=True):
        st.markdown("### 项目总览")
        st.markdown(
            "**一句话介绍：** 这是一个 AI 简历优化助手 Demo + 用户行为数据分析与产品效果评估项目，用于展示数据分析框架、AI 产品理解和产品优化思路。"
        )
        cols = st.columns(4)
        cols[0].metric("模拟用户数", f"{len(users):,}")
        cols[1].metric("优化任务数", f"{len(tasks):,}")
        cols[2].metric("建议采纳率", f"{north_star['suggestion_adoption_rate']:.1%}")
        cols[3].metric("有效完成率", f"{north_star['effective_completion_rate']:.1%}")

        overview_tabs = st.tabs(["业务背景", "用户路径与指标", "分析方法与结论", "技术栈与边界"])
        with overview_tabs[0]:
            st.markdown(
                """
求职用户在针对不同 JD 修改简历时，常见问题是岗位要求理解不清、简历表达泛化、修改成本高。本项目模拟一个 AI 简历优化助手 MVP，通过规则模拟生成结构化建议，并用模拟产品日志评估用户是否愿意采纳建议、是否完成报告导出。

项目不作为真实上线产品，不接入真实 API，不追踪真实投递或面试结果，也不宣称真实提升面试率。
"""
            )
        with overview_tabs[1]:
            st.markdown(
                """
**用户路径：** 访问产品 → 上传简历 → 上传 JD → 生成建议 → 采纳 / 不采纳建议 → 导出优化报告。

**北极星指标：** 有效优化任务完成率 = 完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数。

**核心指标：** 建议生成率、建议采纳率、报告导出率、Prompt A/B 采纳差异、建议质量评分与采纳率关系、用户分群转化差异。
"""
            )
        with overview_tabs[2]:
            st.markdown(
                """
**分析方法：** 漏斗分析、Prompt A/B 实验、用户分群、AI 建议质量评分、导出转化影响因素分析、产品优化优先级矩阵。

**关键结论（基于模拟产品日志）：** 主要流失点集中在“采纳建议 → 导出报告”；JD 匹配型 Prompt 的采纳率更高；JD 匹配度越高，用户越容易采纳建议；转行用户需要更强的能力映射和岗位差距解释。

**产品优化建议：** 导出按钮前置、采纳后增加下一步引导、增强 JD 关键词绑定解释、为转行用户提供可迁移能力识别、增加有用 / 无用反馈按钮。
"""
            )
        with overview_tabs[3]:
            st.markdown(
                """
**技术栈：** Streamlit、Python、pandas、NumPy、Plotly、CSV / SQLite。

**展示模式：** 默认加载固定模拟数据，数据分析看板无需用户操作即可完整展示；用户在页面中的体验数据仅保存在当前 session，不会影响作品集样例数据。

**项目边界：** 示例简历、示例 JD 和用户行为数据均为虚构或模拟数据，不包含真实手机号、邮箱、地址、身份证、API Key 或真实用户身份信息。
"""
            )


def render_task_overview() -> None:
    counts = suggestion_counts()
    scores = current_scores()
    st.markdown("#### 当前任务概览")
    cols = st.columns(3)
    cols[0].metric("当前 JD 匹配分", scores["current"], help="基于 JD 关键词覆盖率、简历技能表达强度和项目经历相关性模拟计算。")
    cols[1].metric("待优化建议数", counts["total"])
    cols[2].metric("预计提升空间", f"+{scores['potential']}")
    cols = st.columns(3)
    cols[0].metric("已采纳建议数", counts["adopted"])
    cols[1].metric("已拒绝建议数", counts["rejected"])
    cols[2].metric("待处理建议数", counts["pending"])
    if counts["total"]:
        st.progress(counts["processed"] / counts["total"])
    st.caption(
        f"建议采纳进度：已处理 {counts['processed']} / {counts['total']} 条建议；"
        f"已采纳 {counts['adopted']} 条，未采纳 {counts['rejected']} 条，待处理 {counts['pending']} 条。"
    )
    render_export_button("export_top")


def render_resume_optimizer() -> None:
    st.subheader("简历优化")
    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        st.selectbox("用户类型", ["应届生", "实习生", "转行用户"], key="user_type")
        st.radio(
            "Prompt 实验组",
            ["A", "B"],
            key="prompt_group",
            horizontal=True,
            help="A 组为通用建议型 Prompt，B 组为 JD 匹配型 Prompt。",
        )
        uploaded_file = st.file_uploader("上传简历文件（txt / md）", type=["txt", "md"])
        if uploaded_file is not None and uploaded_file.name != st.session_state.last_uploaded_name:
            st.session_state.resume_text = decode_uploaded_file(uploaded_file)
            st.session_state.last_uploaded_name = uploaded_file.name
            log_event("upload_resume")
        st.text_area("简历文本", key="resume_text", height=220)
        st.text_area("目标岗位 JD", key="jd_text", height=220)

        if st.button("生成优化建议", type="primary", use_container_width=True):
            if not st.session_state.resume_text.strip() or not st.session_state.jd_text.strip():
                st.warning("请先填写简历文本和目标岗位 JD。")
            else:
                task_id = stable_id("task", st.session_state.demo_session_id, st.session_state.resume_text, st.session_state.jd_text)
                st.session_state.demo_task_id = task_id
                log_event("upload_resume")
                log_event("upload_jd")
                st.session_state.suggestions = generate_suggestions(
                    resume_text=st.session_state.resume_text,
                    jd_text=st.session_state.jd_text,
                    task_id=task_id,
                    user_id=st.session_state.demo_user_id,
                    prompt_group=st.session_state.prompt_group,
                    suggestion_provider=SUGGESTION_PROVIDER,
                )
                log_event("generate_suggestion")
                st.success(f"已生成 {len(st.session_state.suggestions)} 条结构化优化建议。")

    with right:
        render_task_overview()
        st.markdown("#### 当前 JD 关键词")
        st.write("、".join(extract_jd_keywords(st.session_state.jd_text)))
        st.info("首页聚焦产品 Demo 体验；会话行为日志已移至“数据分析看板”的数据表区域。")

    render_suggestion_cards()


def render_suggestion_cards() -> None:
    st.markdown("### 结构化优化建议")
    if not st.session_state.suggestions:
        st.info("点击“生成优化建议”后，这里会展示问题定位、修改建议、前后对比和匹配 JD 关键词。")
        return

    status_label = {"pending": "待处理", "adopted": "已采纳", "rejected": "未采纳"}
    for index, item in enumerate(st.session_state.suggestions):
        status = item.get("status", "pending")
        with st.container(border=True):
            top_cols = st.columns([1.2, 1.4, 1])
            top_cols[0].markdown(f"**简历模块：** {item['resume_section']}")
            top_cols[1].markdown(f"**匹配 JD 关键词：** {', '.join(item['matched_jd_keywords'])}")
            top_cols[2].markdown(f"**当前处理状态：** {status_label[status]}")
            st.markdown(f"**问题定位：** {item['current_problem']}")
            st.markdown(f"**修改建议：** {item['suggestion']}")
            action_cols = st.columns([1, 1, 3])
            if action_cols[0].button("采纳", key=f"adopt_{item['suggestion_id']}", type="primary" if status == "adopted" else "secondary"):
                set_suggestion_status(index, "adopted")
                st.rerun()
            if action_cols[1].button("不采纳", key=f"reject_{item['suggestion_id']}", type="primary" if status == "rejected" else "secondary"):
                set_suggestion_status(index, "rejected")
                st.rerun()
            action_cols[2].caption("可重新选择状态；系统只在状态发生变化时写入一条新的行为日志。")

            with st.expander("查看示例改写、评分与前后对比"):
                comparison = pd.DataFrame(
                    [
                        {"版本": "原表达", "内容": item.get("original_expression", "")},
                        {"版本": "优化后表达", "内容": item.get("revised_expression", item.get("revised_example", ""))},
                    ]
                )
                st.dataframe(comparison, use_container_width=True, hide_index=True)
                st.markdown(f"**示例改写：** {item['revised_example']}")
                score_cols = st.columns(3)
                score_cols[0].metric("具体性评分", item["specificity_score"])
                score_cols[1].metric("JD 匹配度评分", item["jd_match_score"])
                score_cols[2].metric("可执行性评分", item["actionability_score"])

    render_export_button("export_bottom")


def render_jd_parser() -> None:
    st.subheader("JD 解析")
    keywords = extract_jd_keywords(st.session_state.jd_text)
    categories = categorize_keywords(keywords)
    st.markdown("#### JD 关键词能力分类")
    cols = st.columns(2)
    for idx, (category, values) in enumerate(categories.items()):
        with cols[idx % 2]:
            st.markdown(f"**{category}**")
            st.write("、".join(values))

    scores = current_scores()
    metric_cols = st.columns([1, 2])
    metric_cols[0].metric("当前模拟匹配分", scores["current"])
    metric_cols[1].info("匹配分基于 JD 关键词覆盖率、简历技能表达强度和项目经历相关性模拟计算，仅用于 Demo 效果评估，不代表真实招聘筛选结果。")

    gaps = pd.DataFrame(analyze_resume_gaps(st.session_state.resume_text, st.session_state.jd_text))
    st.markdown("#### 简历缺口分析")
    st.dataframe(gaps, use_container_width=True, hide_index=True)
    high_priority = gaps[gaps["优先级"].isin(["高", "中"])]["JD 要求"].tolist()
    if high_priority:
        st.warning("建议优先补强关键词：" + "、".join(high_priority))
    else:
        st.success("简历已覆盖大部分 JD 关键词，可以继续优化表达的具体性和量化结果。")


def render_metric_card(column, label: str, value: str, help_text: str) -> None:
    column.metric(label, value, help=help_text)
    column.caption(help_text)


def render_insight(interpretation: str, action: str) -> None:
    st.markdown(f"**业务解读：** {interpretation}")
    st.markdown(f"**可落地动作：** {action}")


def render_dashboard(tables: Dict[str, pd.DataFrame]) -> None:
    st.subheader("数据分析看板")
    st.caption("以下结论均基于模拟产品日志，用于展示产品效果评估方法和分析框架。")
    users = tables["users"]
    tasks = tables["resume_tasks"]
    events = tables["events"]
    suggestions = tables["suggestions"]

    st.markdown("### 核心指标体系")
    north_star = north_star_metrics(tasks, events, suggestions)
    summary = suggestion_summary(suggestions)
    metric_cols = st.columns(5)
    render_metric_card(metric_cols[0], "简历优化任务数", f"{north_star['resume_task_count']:,}", "模拟产品日志中已生成建议的简历优化任务数量。")
    render_metric_card(metric_cols[1], "建议生成率", f"{north_star['suggestion_generation_rate']:.1%}", "生成建议用户数 / 访问产品用户数。")
    render_metric_card(metric_cols[2], "建议采纳率", f"{north_star['suggestion_adoption_rate']:.1%}", "被用户点击采纳的建议数 / 建议曝光数。")
    render_metric_card(metric_cols[3], "报告导出率", f"{north_star['report_export_rate']:.1%}", "导出报告任务数 / 生成建议任务数。")
    render_metric_card(metric_cols[4], "有效优化任务完成率", f"{north_star['effective_completion_rate']:.1%}", "完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数。")
    st.dataframe(indicator_tree(), use_container_width=True, hide_index=True)
    render_insight(
        "北极星指标将“采纳建议”和“导出报告”绑定，避免只看单点点击行为，更贴近一次有效简历优化任务是否完成。",
        "后续分析都围绕有效优化任务完成率拆解，优先定位导出、采纳和建议质量上的瓶颈。",
    )

    st.markdown("### 路径漏斗与主要流失点")
    funnel = calculate_funnel(events)
    fig_funnel = px.funnel(funnel, x="users", y="step", title="1. 用户路径漏斗图（模拟产品日志）")
    st.plotly_chart(fig_funnel, use_container_width=True, config=PLOT_CONFIG)
    st.dataframe(
        funnel.assign(
            conversion_rate=funnel["conversion_rate"].map(lambda x: f"{x:.1%}"),
            dropoff_rate=funnel["dropoff_rate"].map(lambda x: f"{x:.1%}"),
        ),
        use_container_width=True,
        hide_index=True,
    )
    render_insight(
        "从模拟漏斗数据看，主要流失点出现在“采纳建议 → 导出报告”环节，说明用户虽然愿意采纳 AI 建议，但未必会完成最终报告导出。",
        "优化导出入口位置、增加顶部固定导出按钮，并在用户采纳建议后给出明确的下一步引导。",
    )

    st.markdown("### 关键问题诊断：为什么采纳建议后没有导出报告？")
    task_features = build_task_feature_table(users, tasks, suggestions)
    diag_cols = st.columns(3)
    adopted_export = export_rate_by_adopted_count(task_features)
    lift_export = export_rate_by_lift(task_features)
    pending_export = export_rate_by_pending_count(task_features)
    fig_adopted_export = px.bar(adopted_export, x="adopted_count_group", y="export_rate", text_auto=".1%", title="不同已采纳建议数下的导出率")
    fig_lift_export = px.bar(lift_export, x="match_score_lift_group", y="export_rate", text_auto=".1%", title="不同匹配分提升下的导出率")
    fig_pending_export = px.bar(pending_export, x="pending_count_group", y="export_rate", text_auto=".1%", title="不同待处理建议数下的导出率")
    for fig in [fig_adopted_export, fig_lift_export, fig_pending_export]:
        fig.update_yaxes(tickformat=".0%")
    diag_cols[0].plotly_chart(fig_adopted_export, use_container_width=True, config=PLOT_CONFIG)
    diag_cols[1].plotly_chart(fig_lift_export, use_container_width=True, config=PLOT_CONFIG)
    diag_cols[2].plotly_chart(fig_pending_export, use_container_width=True, config=PLOT_CONFIG)
    st.markdown("#### 导出转化影响因素表")
    st.dataframe(export_factor_table(task_features), use_container_width=True, hide_index=True)
    render_insight(
        "基于模拟产品日志，报告导出率与已采纳建议数、匹配分提升幅度通常呈正相关；待处理建议数较多时导出率下降，说明建议数量过多可能增加用户决策负担。",
        "在用户采纳建议后减少下一步选择成本，提供“继续处理剩余建议 / 直接导出报告”的明确分流，并控制单次建议数量。",
    )

    st.markdown("### Prompt A/B 实验效果")
    ab = prompt_ab_metrics(tasks, suggestions)
    chi = chi_square_for_prompt_adoption(suggestions)
    fig_ab = px.bar(ab, x="prompt_group", y="adoption_rate", text_auto=".1%", title="2. Prompt A/B 实验建议采纳率对比图（模拟数据）")
    fig_ab.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_ab, use_container_width=True, config=PLOT_CONFIG)
    render_insight(
        "在模拟数据下，B 组 JD 匹配型 Prompt 的建议采纳率高于 A 组通用建议型 Prompt，说明“绑定 JD 关键词 + 给出改写示例”的建议形式更容易被用户采纳。",
        "优先将建议模板升级为 JD 关键词绑定型，并在建议卡片中固定展示关键词、问题定位和改写示例。",
    )
    st.caption(f"卡方检验：chi-square={chi['chi_square']:.3f}，p-value={chi['p_value']:.4f}。仅用于模拟数据下的方法展示。")

    st.markdown("### 建议采纳驱动因素分析")
    driver_tables = adoption_driver_tables(users, suggestions)
    driver_cols = st.columns(3)
    fig_driver_quality = px.bar(driver_tables["quality"], x="quality_bucket", y="adoption_rate", text_auto=".1%", title="不同质量分层的采纳率")
    fig_driver_type = px.bar(driver_tables["type"], x="suggestion_type", y="adoption_rate", text_auto=".1%", title="不同建议类型的采纳率")
    fig_driver_prompt = px.bar(driver_tables["prompt"], x="prompt_group", y="adoption_rate", text_auto=".1%", title="不同 Prompt 组的采纳率")
    for fig in [fig_driver_quality, fig_driver_type, fig_driver_prompt]:
        fig.update_yaxes(tickformat=".0%")
    driver_cols[0].plotly_chart(fig_driver_quality, use_container_width=True, config=PLOT_CONFIG)
    driver_cols[1].plotly_chart(fig_driver_type, use_container_width=True, config=PLOT_CONFIG)
    driver_cols[2].plotly_chart(fig_driver_prompt, use_container_width=True, config=PLOT_CONFIG)
    st.markdown("#### 质量维度与采纳行为的模拟相关性参考")
    st.dataframe(driver_tables["impact"], use_container_width=True, hide_index=True)
    render_insight(
        "JD 匹配度越高，用户越容易采纳建议，说明用户更关注建议是否真正对应目标岗位要求，而不是泛泛的简历修改意见。该结论基于模拟产品日志，用于展示分析思路。",
        "将“匹配 JD 关键词”作为建议卡片的核心信息，并持续优化 JD 匹配度评分低的建议模板。",
    )

    st.markdown("### 用户分群分析")
    segment = user_segment_metrics(users, tasks, suggestions)
    segment_long = segment.melt(
        id_vars="user_type",
        value_vars=["adoption_rate", "export_rate"],
        var_name="metric",
        value_name="rate",
    )
    segment_long["metric"] = segment_long["metric"].replace({"adoption_rate": "建议采纳率", "export_rate": "报告导出率"})
    fig_segment = px.bar(
        segment_long,
        x="user_type",
        y="rate",
        color="metric",
        barmode="group",
        text_auto=".1%",
        title="3. 不同用户类型采纳率 / 导出率对比图（模拟数据）",
    )
    fig_segment.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_segment, use_container_width=True, config=PLOT_CONFIG)
    render_insight(
        "分群结果显示，不同用户类型在建议采纳率和报告导出率上存在差异。若转行用户导出率较低，可能是因为其经历与目标 JD 的能力映射难度更高。",
        "针对不同人群设计差异化建议：实习生强调一键改写，应届生补项目模板，转行用户补可迁移能力识别和岗位差距分析。",
    )
    st.markdown("#### 分群诊断 + 策略建议")
    st.dataframe(segment_strategy_table(segment), use_container_width=True, hide_index=True)

    st.markdown("### 建议质量与建议类型分析")
    quality = quality_adoption_relation(suggestions)
    fig_quality = px.bar(quality, x="quality_bucket", y="adoption_rate", text_auto=".1%", title="4. AI 建议质量评分与采纳率关系图（模拟数据）")
    fig_quality.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_quality, use_container_width=True, config=PLOT_CONFIG)
    low_quality = quality[quality["quality_bucket"].astype(str).str.contains("低质量")]
    if low_quality.empty or int(low_quality["suggestions"].sum()) < 30:
        st.warning("低质量建议样本量不足，因此当前主要比较中质量与高质量建议的采纳差异。")
        render_insight(
            "基于模拟产品日志，低质量建议样本不足会限制低/中/高质量之间的完整比较，但仍可观察中高质量建议的采纳差异。",
            "后续接入真实用户反馈后，应主动收集“无用/不采纳”原因，补足低质量样本以优化质量评分规则。",
        )
    else:
        render_insight(
            "模拟数据中，高质量建议的采纳率通常高于低质量建议，说明具体、匹配 JD 且可执行的建议更容易被用户接受。",
            "将低质量建议模板改为更明确的“问题定位 + 改写示例 + JD 关键词解释”结构。",
        )

    type_adoption = adoption_by_dimension(suggestions, "suggestion_type")
    fig_type = px.bar(type_adoption, x="suggestion_type", y="adoption_rate", text_auto=".1%", title="5. 不同建议类型采纳率对比图（模拟数据）")
    fig_type.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig_type, use_container_width=True, config=PLOT_CONFIG)
    render_insight(
        "不同建议类型的采纳率差异可帮助产品判断优先优化哪些建议模板，而不是平均改所有建议。",
        "优先改造低采纳建议类型，补充前后对比、量化结果示例和 JD 关键词绑定解释。",
    )

    impact = quality_dimension_impact(suggestions)
    st.markdown("#### 质量维度与采纳行为的模拟相关性参考（补充口径）")
    st.caption("该指标基于模拟数据计算，用于展示 AI 建议质量评估的分析思路，不代表真实因果关系。impact 越高，表示该质量维度与采纳行为在模拟数据中的相关性越强。")
    st.dataframe(impact, use_container_width=True, hide_index=True)

    st.markdown("### 产品优化优先级矩阵")
    st.dataframe(optimization_priority_matrix(), use_container_width=True, hide_index=True)
    render_insight(
        "优先级排序围绕北极星指标展开：先解决“采纳后不导出”的路径断点，再提升建议可信度和分群适配。",
        "P0 优先做导出按钮前置和采纳后的下一步引导；P1 做 JD 关键词解释、转行用户专项能力映射和反馈闭环；P2 再接入真实 API 验证生成质量。",
    )

    st.markdown("#### 当前 Demo 会话行为日志")
    event_df = pd.DataFrame(st.session_state.event_log)
    if event_df.empty:
        st.info("暂无当前会话行为日志。")
    else:
        st.dataframe(event_df, use_container_width=True, hide_index=True)


def render_project_notes() -> None:
    st.subheader("项目说明")
    st.markdown(
        """
**项目定位**  
AI 简历优化助手 Demo + 用户行为数据分析与效果评估项目。它是一个可本地演示的 MVP，用于验证简历优化路径、建议采纳行为和产品效果评估方法，不作为真实上线产品，也不宣称真实提升面试率。

**技术实现说明**

- 前端展示：Streamlit；
- 数据处理：Python / pandas；
- 建议生成：规则模拟，预留 API Provider；
- 数据存储：CSV 或 SQLite；
- 可视化：Plotly / Streamlit 图表；
- 分析方法：漏斗分析、分群分析、Prompt A/B 实验、建议质量评分分析。

**核心数据表**  
`users`、`resume_tasks`、`events`、`suggestions`、`feedback`。其中 `resume_tasks` 用来区分同一用户针对多个 JD 的多次优化任务，避免只按 `user_id` 分析导致口径混乱。

**数据分析思路**

- 业务目标：提升用户完成有效简历优化任务的比例；
- 核心指标：有效优化任务完成率，即完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数；
- 分析路径：漏斗定位问题 → 分群拆解差异 → A/B 验证 Prompt 效果 → 建议质量评分分析采纳驱动因素 → 输出产品优化优先级；
- 项目边界：当前分析基于模拟产品日志，用于展示数据分析框架和产品效果评估思路，不宣称真实提升面试率。

**项目边界说明**  
当前项目为 MVP Demo，主要验证产品流程和分析方法。用户行为数据主要为模拟产品日志，少量体验反馈可用于辅助验证，不代表真实上线后的商业结果；面试反馈率等长期结果指标未作为核心分析目标。

**产品优化建议**

- 将 AI 建议展示为“问题定位 + 修改建议 + 示例改写 + 前后对比”的结构；
- 增加 JD 关键词绑定解释，提升用户信任；
- 将导出报告按钮前置，降低最后一步流失；
- 针对转行用户增加可迁移能力识别和岗位差距分析；
- 增加“有用 / 无用”反馈按钮，持续优化建议生成逻辑。

**简历写法**  
搭建 AI 简历优化助手 Demo，支持简历文本/文件上传、JD 关键词解析、结构化优化建议生成与建议采纳反馈；设计 users、resume_tasks、events、suggestions 等核心数据表，基于模拟产品日志完成漏斗转化、Prompt A/B 实验、用户分群和 AI 建议质量评估，定位“采纳建议至导出报告”为主要流失环节，并提出导出入口前置、JD 关键词绑定和建议结构化展示等产品优化方案。

**面试讲述稿**  
1. 求职用户常常不知道如何根据 JD 修改简历，所以我做了一个可演示 MVP。  
2. 用户路径是上传简历、粘贴 JD、生成建议、采纳/拒绝建议、导出报告。  
3. 数据设计新增 `resume_tasks`，因为一个用户可能针对多个 JD 多次优化。  
4. 指标体系重点看漏斗转化、建议采纳率、Prompt A/B 效果、质量评分和分群差异。  
5. 分析重点是哪些建议更容易被采纳，以及 JD 匹配型 Prompt 是否优于通用建议型 Prompt。  
6. 产品结论是降低采纳门槛、增强 JD 匹配解释、提升建议具体性和可执行性。
"""
    )


def main() -> None:
    init_state()
    tables = load_tables()
    render_header()
    render_portfolio_overview(tables)
    tab_optimize, tab_jd, tab_dashboard, tab_notes = st.tabs(["简历优化", "JD 解析", "数据分析看板", "项目说明"])
    with tab_optimize:
        render_resume_optimizer()
    with tab_jd:
        render_jd_parser()
    with tab_dashboard:
        render_dashboard(tables)
    with tab_notes:
        render_project_notes()


if __name__ == "__main__":
    main()
