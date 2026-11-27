from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from logic.metrics import (
    adoption_by_dimension,
    build_task_feature_table,
    calculate_funnel,
    export_rate_by_adopted_count,
    export_rate_by_lift,
    export_rate_by_pending_count,
    north_star_metrics,
    prompt_ab_metrics,
    prompt_adoption_contrast,
    quality_adoption_relation,
    quality_dimension_impact,
    suggestion_summary,
    user_segment_metrics,
)
from resume_workspace import render_workspace

ROOT = Path(__file__).resolve().parent
TABLES = {
    "users": ("登记用户", "每行一名模拟用户，含求职身份和目标岗位。"),
    "events": ("行为事件", "每行一次事件，同一任务可有多次采纳或导出。"),
    "resume_tasks": ("已生成任务", "每行一次已生成建议的任务，含采纳数及导出状态。"),
    "suggestions": ("建议明细", "每行一条已生成建议，用作本项目的曝光口径。"),
    "feedback": ("模拟反馈", "脚本生成的反馈分数和短评，仅用于展示数据结构。"),
}
TEAL = "#136B62"
AMBER = "#AA5528"
PAGES = ["转化总览", "模板与人群", "简历工作台", "数据口径"]

st.set_page_config(page_title="AI 简历助手 · 产品分析", page_icon="📊", layout="wide")


@st.cache_data
def load_tables():
    tables = {name: pd.read_csv(ROOT / "data" / f"{name}.csv") for name in TABLES}
    suggestions = tables["suggestions"]
    if "status" not in suggestions.columns:
        suggestions["status"] = (
            suggestions["adopted"].map({True: "adopted", False: "rejected"}).fillna("pending")
        )
    return tables


def percent(value):
    return "—" if pd.isna(value) else f"{value:.1%}"


def show_table(data, names, rates=()):
    view = data[list(names)].copy()
    for col in rates:
        view[col] = view[col].map(percent)
    st.dataframe(view.rename(columns=names), hide_index=True, width="stretch")


def metric(col, label, value, detail):
    with col.container(border=True):
        st.metric(label, value)
        st.caption(detail)


def header(tables):
    st.markdown(
        """
    <style>
    .block-container {max-width:1140px;padding-top:2.7rem;padding-bottom:3rem}
    .report-cover {border-left:5px solid #c3dc97;background:#143f3a;color:#fff;
      padding:19px 27px 20px;margin-bottom:8px;border-radius:0 12px 12px 0}
    .report-cover p {font-size:.86rem;color:#d0e8d4;letter-spacing:.04em;margin:0 0 4px}
    .report-cover h1 {color:#fff;padding:0;font-size:clamp(1.45rem,3vw,2.25rem);line-height:1.25;
      font-family:"Work Sans","PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:-.025em}
    .st-key-view_nav [role="radiogroup"] {gap:.45rem;flex-wrap:wrap}
    .st-key-view_nav [role="radiogroup"] label {padding:.3rem .75rem;border:1px solid #bed0cb;
      border-radius:20px;margin:0;cursor:pointer}
    .st-key-view_nav [role="radiogroup"] label:has(input:checked) {background:#e3f2e9;border-color:#136b62;color:#134b43}
    [data-testid="stMetricValue"] {font-variant-numeric:tabular-nums}
    @media(max-width:680px){.block-container{padding-top:3.5rem}.report-cover{padding:15px 18px}}
    </style>""",
        unsafe_allow_html=True,
    )
    dates = pd.to_datetime(tables["events"]["event_time"], errors="coerce").dropna()
    period = f" · {dates.min():%Y.%m.%d} – {dates.max():%Y.%m.%d}" if len(dates) else ""
    st.markdown(
        f'<div class="report-cover"><p>产品分析作品集 · 模拟日志{period}</p>'
        "<h1>AI 简历助手的用户转化分析</h1></div>",
        unsafe_allow_html=True,
    )
    return st.radio("页面导航", PAGES, key="view_nav", horizontal=True, label_visibility="collapsed")


def filter_profiles(tables):
    types = sorted(tables["users"]["user_type"].dropna().unique())
    options = ["全部人群", *types]
    selected = st.selectbox(
        "查看人群",
        options,
        index=options.index(st.session_state.get("profile_filter", options[0])),
        key="cohort_choice",
    )
    st.session_state.profile_filter = selected
    if selected == options[0]:
        return tables
    user_ids = tables["users"].loc[tables["users"]["user_type"].eq(selected), "user_id"]
    return {name: df[df.user_id.isin(user_ids)] for name, df in tables.items()}


def render_funnel(tables):
    users, tasks, events, suggestions = (
        tables[k] for k in ("users", "resume_tasks", "events", "suggestions")
    )
    funnel = calculate_funnel(events)
    summary = north_star_metrics(tasks, events, suggestions)
    exposed = suggestion_summary(suggestions)
    cols = st.columns(3)
    metric(
        cols[0],
        "有效任务完成率",
        percent(summary["effective_completion_rate"]),
        f"{summary['effective_tasks']:,} 个已采纳且导出 / {len(tasks):,} 个已生成任务",
    )
    metric(
        cols[1],
        "建议采纳率",
        percent(exposed["adoption_rate"]),
        f"{exposed['adopted']:,} 条已采纳 / {exposed['exposed']:,} 条已生成建议",
    )
    metric(
        cols[2],
        "用户生成率",
        percent(summary["suggestion_generation_rate"]),
        f"{funnel.at[3, 'users']:,} 人生成建议 / {funnel.at[0, 'users']:,} 人访问",
    )
    funnel["loss"] = (funnel.tasks.shift() - funnel.tasks).astype("Int64")
    transitions = funnel.iloc[1:].dropna(subset=["task_dropoff_rate"])
    largest = transitions["task_dropoff_rate"].idxmax() if not transitions.empty else None
    with st.container(border=True):
        st.subheader("任务在哪一步流失？")
        st.caption("同一次任务必须依次完成各步骤。横条表示达到该步的任务数。")
        chart_col, detail_col = st.columns([1.65, 1], gap="large")
        fig = go.Figure(
            go.Bar(
                x=funnel.tasks,
                y=funnel.step,
                orientation="h",
                marker_color=[AMBER if i == largest else TEAL for i in funnel.index],
                text=funnel.tasks.map(lambda n: f"{n:,}"),
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>到达任务数 %{x:,}<extra></extra>",
            )
        )
        fig.update_layout(
            height=265,
            margin=dict(l=0, r=50, t=8, b=5),
            bargap=0.42,
            xaxis=dict(visible=False, range=[0, max(1, funnel.tasks.max()) * 1.16]),
            yaxis=dict(autorange="reversed", automargin=True, fixedrange=True),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=14, color="#25443f"),
        )
        chart_col.plotly_chart(fig, width="stretch", theme=None, config={"displayModeBar": False})
        with detail_col:
            if largest is not None:
                previous, row = funnel.loc[largest - 1], funnel.loc[largest]
                st.markdown("**环节流失率最高**")
                st.metric(f"{previous.step} → {row.step}", percent(row.task_dropoff_rate))
                st.write(
                    f"上一步有 {previous.tasks:,} 个任务，其中 {row.tasks:,} 个进入下一步，{int(row.loss):,} 个在此流失。"
                )
            else:
                st.write("当前人群没有足够事件计算相邻步骤的流失率。")
        with st.expander("查看每一步的任务数、用户数和分母"):
            show_table(
                funnel,
                {
                    "step": "步骤",
                    "tasks": "到达任务",
                    "users": "去重用户",
                    "loss": "较上步流失任务",
                    "task_conversion_rate": "环节转化率",
                    "task_dropoff_rate": "环节流失率",
                },
                ("task_conversion_rate", "task_dropoff_rate"),
            )
    with st.expander("进一步拆解导出任务"):
        features = build_task_feature_table(users, tasks, suggestions)
        st.write(
            f"当前人群的报告导出率为 {percent(summary['report_export_rate'])}。历史样本的生成脚本要求任务先采纳建议才有机会导出，因此样本中的导出率与有效完成率相同。"
        )
        choice = st.radio("按什么分组", ["采纳条数", "待处理条数", "模拟分数增幅"], horizontal=True)
        if choice == "采纳条数":
            grouped, col = export_rate_by_adopted_count(features), "adopted_count_group"
        elif choice == "待处理条数":
            grouped, col = export_rate_by_pending_count(features), "pending_count_group"
            if len(grouped[grouped.tasks > 0]) < 2:
                st.info("只有一个有样本的分组，无法比较待处理条数与导出的关系。")
        else:
            grouped, col = export_rate_by_lift(features), "match_score_lift_group"
            st.caption("此处的历史分数增幅由采纳条数与模拟参数计算。它无法衡量实际简历质量改善。")
        show_table(
            grouped,
            {col: choice, "tasks": "已生成任务", "exported": "导出任务", "export_rate": "报告导出率"},
            ("export_rate",),
        )
    st.markdown("#### 下一步如何验证导出引导")
    st.write(
        "在首次采纳后展示报告预览和下载入口，以用户为单位随机分组。比较两组“已采纳任务中完成导出的比例”，同时观察有效完成率和后续建议处理率。"
    )


def render_comparisons(tables):
    users, tasks, suggestions = (tables[k] for k in ("users", "resume_tasks", "suggestions"))
    ab = prompt_ab_metrics(tasks, suggestions)
    contrast = prompt_adoption_contrast(suggestions)
    st.subheader("两种模板的建议采纳表现")
    cols = st.columns(3)
    for idx, label in enumerate(("A", "B")):
        sample = ab[ab.prompt_group == label]
        title = "A · 通用表达" if label == "A" else "B · 岗位匹配"
        if sample.empty:
            metric(cols[idx], title, "—", "当前人群没有该组样本")
        else:
            row = sample.iloc[0]
            metric(
                cols[idx],
                title,
                percent(row.adoption_rate),
                f"{int(row.adopted):,} 条采纳 / {int(row.suggestions):,} 条建议",
            )
    diff = contrast["difference"]
    value = "—" if pd.isna(diff) else f"{diff * 100:+.1f}"
    metric(cols[2], "B 减 A（百分点）", value, "两组按建议条数计算采纳率")
    st.write(
        "模拟器按任务分配 A、B 组，并预设 B 组有更高的采纳和导出概率。这组差值用于演示分析方法，真实效果仍需线上实验验证。"
    )
    with st.expander("查看模板分组明细与区间估计"):
        show_table(
            ab,
            {
                "prompt_group": "模板",
                "tasks": "已生成任务",
                "exported_tasks": "导出任务",
                "export_rate": "报告导出率",
                "suggestions": "建议数",
                "adopted": "采纳数",
                "adoption_rate": "采纳率",
            },
            ("export_rate", "adoption_rate"),
        )
        if pd.notna(contrast["ci_low"]):
            st.caption(
                f"同一用户可能参与两组，每个任务也可生成多条建议。按 {contrast['users']:,} 名用户聚类，组间差值的近似 95% 区间为 {contrast['ci_low']*100:.1f} 至 {contrast['ci_high']*100:.1f} 个百分点。"
            )
    st.subheader("人群差异")
    segment = user_segment_metrics(users, tasks, suggestions)
    segment["avg_tasks_per_user"] = segment["avg_tasks_per_user"].round(2)
    show_table(
        segment,
        {
            "user_type": "求职身份",
            "users": "登记用户",
            "tasks": "已生成任务",
            "avg_tasks_per_user": "人均生成任务",
            "exported": "导出任务",
            "export_rate": "报告导出率",
            "suggestions": "建议数",
            "adopted": "采纳数",
            "adoption_rate": "建议采纳率",
        },
        ("export_rate", "adoption_rate"),
    )
    st.subheader("哪些建议被采纳？")
    dimension = st.radio("建议分组", ["规则质量评分", "建议类型"], horizontal=True)
    if dimension == "规则质量评分":
        group, key = quality_adoption_relation(suggestions), "quality_bucket"
        st.caption("质量分取具体性、岗位匹配、可执行性三项规则评分的均值。没有样本的分组显示为「—」。")
    else:
        group, key = adoption_by_dimension(suggestions, "suggestion_type"), "suggestion_type"
    show_table(
        group,
        {key: dimension, "suggestions": "建议数", "adopted": "采纳数", "adoption_rate": "建议采纳率"},
        ("adoption_rate",),
    )

    with st.expander("查看质量评分与建议采纳的相关性"):
        impact = quality_dimension_impact(suggestions)
        impact["impact"] = impact["impact"].map(lambda x: "—" if pd.isna(x) else f"{x:.3f}")
        show_table(impact, {"dimension": "评分维度", "impact": "与采纳的相关系数"})
        st.caption(
            "采纳记为 1，其余记为 0。某一维度取值全部相同时，相关系数无法计算。模拟器用评分生成采纳概率。"
        )


def render_sources(tables):
    st.header("数据来源与指标口径")
    st.write("看板读取仓库内的固定模拟样本。简历工作台使用规则词库生成建议，交互记录留在单次会话中。")
    st.dataframe(
        pd.DataFrame(
            [
                {"数据表": k, "主题": name, "记录数": len(tables[k]), "记录粒度": desc}
                for k, (name, desc) in TABLES.items()
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    st.subheader("指标怎么算")
    definitions = [
        ("有效任务完成率", "至少采纳一条建议且导出报告的任务数 / 已生成建议的任务数"),
        ("建议采纳率", "已采纳的建议条数 / 全部生成的建议条数。样本以生成为曝光代理"),
        ("用户生成率", "按顺序走到生成建议的去重用户数 / 访问用户数"),
        ("报告导出率", "导出任务数 / 已生成建议的任务数"),
        ("环节流失率", "同一任务上一步到达、本步未到达的任务数 / 上一步到达的任务数"),
    ]
    st.dataframe(
        pd.DataFrame(definitions, columns=["指标", "分子与分母"]), hide_index=True, width="stretch"
    )
    st.markdown("#### 哪些问题还需要真实数据")
    st.write(
        "模板分数、采纳、导出和反馈都来自模拟规则。若要评估建议是否真的帮助求职者，需要记录实际修改前后的内容，并单独取得使用反馈。现有数据只覆盖报告导出。"
    )


def main():
    try:
        tables = load_tables()
    except FileNotFoundError as error:
        st.error(f"缺少样本文件 {Path(error.filename).name}。请恢复 data 目录中的 CSV 后重新运行。")
        return
    page = header(tables)
    if page == "简历工作台":
        render_workspace()
    elif page == "数据口径":
        render_sources(tables)
    else:
        title, filters = st.columns([2.5, 1], vertical_alignment="bottom")
        with title:
            st.header(page)
        with filters:
            scope = filter_profiles(tables)
        if page == "转化总览":
            render_funnel(scope)
        else:
            render_comparisons(scope)


if __name__ == "__main__":
    main()
