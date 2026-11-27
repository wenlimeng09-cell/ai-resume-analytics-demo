"""Public entry point for the conversion and operations portfolio."""

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from analysis_data import funnel_counts, segment_export
from conversion_view import render_conversion
from operations_view import render_operations, suggestion_outcomes
from tool_view import render_tool

ROOT = Path(__file__).resolve().parent
PAGES = {
    "overview": "业务概览",
    "conversion": "转化与人群分析",
    "operations": "运营诊断与验证",
    "tool": "工具体验与数据说明",
}
TABLES = {
    "users": ("用户", "一行一名模拟用户", "user_id", "求职身份、目标岗位"),
    "events": ("行为事件", "一行一次行为", "event_id", "任务、用户、时间、事件名"),
    "resume_tasks": ("生成任务", "一行一个已生成建议的任务", "task_id", "采纳数、拒绝数、是否导出"),
    "suggestions": ("建议", "一行一条已生成的建议", "suggestion_id", "所属任务、建议类型、处理状态"),
    "feedback": ("模拟反馈", "一行一份脚本生成的反馈", "feedback_id", "任务、评分、文字反馈"),
}

st.set_page_config(page_title="AI 简历助手 · 用户转化与运营分析", page_icon="📊", layout="wide")


@st.cache_data(show_spinner=False)
def load_tables():
    return {name: pd.read_csv(ROOT / "data" / f"{name}.csv") for name in TABLES}


def go_to_page(slug):
    st.session_state.portfolio_page = slug
    st.session_state.last_view_param = slug
    st.query_params["view"] = slug


def sync_page_selection():
    go_to_page(st.session_state.portfolio_page)


def navigation():
    requested = st.query_params.get("view", "overview")
    slug = requested if requested in PAGES else "overview"
    if "portfolio_page" not in st.session_state or slug != st.session_state.get("last_view_param"):
        st.session_state.portfolio_page = slug
        st.session_state.last_view_param = slug
    return st.radio(
        "作品集页面",
        list(PAGES),
        format_func=PAGES.get,
        key="portfolio_page",
        horizontal=True,
        label_visibility="collapsed",
        on_change=sync_page_selection,
    )


def render_header():
    styles = (ROOT / "portfolio.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)
    st.markdown(
        '<header class="mast"><div class="mast-brand"><span class="signal" aria-hidden="true">'
        "<i></i><i></i><i></i></span><strong>AI 简历助手</strong>"
        '<span class="mast-divider">/</span><span>用户转化与运营分析</span></div>'
        '<span class="mast-source">固定模拟样本</span></header>',
        unsafe_allow_html=True,
    )


def percent(value):
    return "—" if pd.isna(value) else f"{value:.1%}"


def render_overview(tables):
    events = tables["events"]
    timeline = pd.to_datetime(events["event_time"], errors="coerce").dropna()
    period = f"{timeline.min():%Y.%m.%d} – {timeline.max():%Y.%m.%d}" if len(timeline) else "观察期未知"
    path = funnel_counts(events, unit="tasks").set_index("event_name")
    visits = int(path.at["visit_product", "reached"])
    generated = int(path.at["generate_suggestion", "reached"])
    adopted = int(path.at["adopt_suggestion", "reached"])
    exported = int(path.at["export_report", "reached"])
    loss = adopted - exported
    rate = path.at["export_report", "conversion_rate"]
    bar_width = 0 if pd.isna(rate) else float(rate) * 100
    st.markdown(
        f"""<section class="lead-panel">
        <div class="lead-story"><p class="lead-period">观察期 &nbsp; {period}</p>
        <h1>采纳建议后，有多少任务<br>最终导出了报告？</h1>
        <p class="lead-copy">从 {events.user_id.nunique():,} 名模拟用户的 {len(events):,} 条行为记录出发，
        找到流失环节，比较优先调查的人群，再设计运营试点。</p></div>
        <div class="lead-result"><p>采纳后导出率</p>
        <strong>{percent(rate)}</strong>
        <div class="split-bar" aria-hidden="true"><i style="width:{bar_width:.2f}%"></i></div>
        <div class="split-key"><span><b></b>已导出 <em>{exported:,}</em></span>
        <span><b></b>未导出 <em>{loss:,}</em></span></div>
        <small>分母为至少采纳一条建议的 {adopted:,} 个任务</small></div></section>""",
        unsafe_allow_html=True,
    )
    left, right, _ = st.columns([1, 1, 2.4])
    left.button(
        "查看流失分析 →", type="primary", width="stretch", on_click=go_to_page, args=("conversion",)
    )
    right.button("体验一次简历优化", width="stretch", on_click=go_to_page, args=("tool",))

    st.subheader("从流失定位到运营试点")
    segments = segment_export(tables, unit="tasks")
    eligible = segments.dropna(subset=["export_rate"])
    if not eligible.empty:
        most_loss = eligible.loc[eligible["lost"].idxmax()]
        lowest = eligible.loc[eligible["export_rate"].idxmin()]
        segment_detail = (
            f"{most_loss.user_type}有 {int(most_loss.lost)} 个已采纳任务未导出，"
            f"{lowest.user_type}的采纳后导出率最低（{percent(lowest.export_rate)}）。"
            "选择试点前，可以按流失规模安排触达，按转化率选择访谈对象。"
        )
    else:
        segment_detail = "当前没有足够的分群样本。"
    suggestions = tables["suggestions"]
    by_type = suggestion_outcomes(suggestions, "suggestion_type")
    if not by_type.empty:
        top = by_type.rejected.idxmax()
        op_detail = (
            f"「{top}」类有 {int(by_type.at[top, 'rejected'])} 条被拒绝，数量最多。"
            "先抽查原文与改写，再用自愿反馈区分内容问题和个人偏好。"
        )
    else:
        op_detail = "当前没有可比较的建议类型。"
    cards = [
        (
            "数据分析",
            "在哪一步离开？",
            f"将 {visits:,} 个访问任务按事件顺序还原，其中 {generated:,} 个生成了建议。"
            f"从采纳到导出又流失了 {loss:,} 个任务。",
        ),
        ("商业分析", "先调查哪类人？", segment_detail),
        ("运营分析", "先改哪类内容？", op_detail),
    ]
    for col, (role, title, copy) in zip(st.columns(3), cards):
        with col.container(border=True):
            st.caption(role)
            st.markdown(f"#### {title}")
            st.write(copy)


RECONCILIATION_SQL = """SELECT
    u.user_type,
    SUM(CASE WHEN t.adopted_count > 0 THEN 1 ELSE 0 END) AS adopted_tasks,
    SUM(CASE WHEN t.adopted_count > 0 AND t.exported = 1
             THEN 1 ELSE 0 END) AS exported_tasks
FROM users AS u
LEFT JOIN resume_tasks AS t ON t.user_id = u.user_id
GROUP BY u.user_type
ORDER BY u.user_type"""


def render_sources(tables):
    st.header("数据来源与指标口径")
    st.write("分析使用仓库内的五张固定模拟表。下表可用来核对每个数字的来源、粒度与关联键。")
    rows = [
        {
            "主题": label,
            "表名": name,
            "行数": len(tables[name]),
            "记录粒度": grain,
            "主键": pk,
            "用于分析的字段": fields,
        }
        for name, (label, grain, pk, fields) in TABLES.items()
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.subheader("怎么从五张表算到页面上的数字")
    definitions = [
        (
            "六步漏斗",
            "events",
            "同一用户、同一任务按时间依次经过访问、输入简历、输入 JD、生成、采纳、导出。每步每任务只计一次。",
        ),
        (
            "用户漏斗",
            "events",
            "先判断哪些任务有序到达该步，再对已到达的用户去重。同一用户可能有多个任务。",
        ),
        (
            "采纳后导出率",
            "events",
            "有序到达导出的任务数 / 到达采纳的任务数。人群按 users.user_type 划分。",
        ),
        (
            "有效任务完成率",
            "resume_tasks",
            "至少采纳一条且导出的任务数 / 生成过建议的任务数。固定样本的导出任务都已采纳。",
        ),
        (
            "建议采纳率、拒绝率",
            "suggestions",
            "已采纳或已拒绝的建议条数分别除以全部生成的条数。样本没有单条建议实际进入视野的事件。",
        ),
        (
            "分群流失占比",
            "events + users",
            "该人群已采纳却未导出的数量 / 全部人群已采纳却未导出的数量。",
        ),
    ]
    st.dataframe(
        pd.DataFrame(definitions, columns=["指标", "来源", "计算方法"]),
        hide_index=True,
        width="stretch",
    )
    with st.expander("用 SQL 独立核对按人群统计的任务数"):
        st.write(
            "漏斗根据事件发生顺序计算。这里从任务汇总表出发，按人群重新统计采纳和导出，再比较两个来源的差值。"
        )
        st.code(RECONCILIATION_SQL, language="sql")
        if st.button("运行 SQL 对账", key="run_sql_check"):
            with sqlite3.connect(":memory:") as db:
                tables["users"][["user_id", "user_type"]].to_sql("users", db, index=False)
                tables["resume_tasks"][["task_id", "user_id", "adopted_count", "exported"]].to_sql(
                    "resume_tasks", db, index=False
                )
                task_check = pd.read_sql_query(RECONCILIATION_SQL, db)
            event_check = segment_export(tables)[["user_type", "adopted", "exported"]]
            compared = task_check.merge(event_check, on="user_type", how="outer", validate="one_to_one")
            compared["采纳差值"] = compared["adopted_tasks"] - compared["adopted"]
            compared["导出差值"] = compared["exported_tasks"] - compared["exported"]
            result = compared.rename(
                columns={
                    "user_type": "人群",
                    "adopted_tasks": "任务表采纳数",
                    "adopted": "事件采纳数",
                    "exported_tasks": "任务表导出数",
                    "exported": "事件导出数",
                }
            )
            st.dataframe(
                result[
                    [
                        "人群",
                        "任务表采纳数",
                        "事件采纳数",
                        "采纳差值",
                        "任务表导出数",
                        "事件导出数",
                        "导出差值",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "差值 = 任务表统计数减去事件漏斗统计数。逐组为 0 表示两种取数方式在该样本上一致。"
            )
    st.markdown("#### 这些数据能支持哪些判断")
    st.write(
        "快照能回溯流失位置、比较各人群的规模并筛选待调查的内容。采纳与导出概率由模拟脚本设定，用户为什么离开、试点能带来多少增量，需要另外收集真实反馈并做对照验证。"
    )
    st.caption("工具中的输入和反馈按会话处理，与固定样本分开。可选模型仅在解锁并主动生成时使用。")
    st.markdown(
        "[查看生成这批固定样本的源码与 CSV](https://github.com/wenlimeng09-cell/ai-resume-analytics-demo/tree/4de4961c3cdb475aa688729ecf67607540d761ac/data)"
    )


def main():
    render_header()
    page = navigation()
    if page == "tool":
        panel = st.radio("本页内容", ["体验工具", "查看数据口径"], horizontal=True, key="tool_panel")
        if panel == "体验工具":
            render_tool()
            return
    try:
        tables = load_tables()
    except FileNotFoundError as exc:
        st.error(f"固定样本缺少 {Path(exc.filename).name}，请恢复 data 目录的 CSV。")
        return
    if page == "overview":
        render_overview(tables)
    elif page == "conversion":
        render_conversion(tables)
    elif page == "operations":
        render_operations(tables)
    else:
        render_sources(tables)


if __name__ == "__main__":
    main()
