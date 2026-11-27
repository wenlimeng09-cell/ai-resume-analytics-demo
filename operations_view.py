from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis_data import funnel_counts


def suggestion_outcomes(suggestions: pd.DataFrame, dimension: str) -> pd.DataFrame:
    """Count the final decision once per generated suggestion."""
    rows = suggestions.dropna(subset=["suggestion_id"]).drop_duplicates("suggestion_id", keep="last")
    rows = rows.assign(
        adopted=rows["status"].eq("adopted"),
        rejected=rows["status"].eq("rejected"),
        pending=rows["status"].eq("pending"),
    )
    summary = rows.groupby(dimension, observed=True).agg(
        generated=("suggestion_id", "size"),
        adopted=("adopted", "sum"),
        rejected=("rejected", "sum"),
        pending=("pending", "sum"),
    )
    return summary.sort_values(["rejected", "generated"], ascending=False)


def percent(numerator: int, denominator: int) -> str:
    return f"{numerator / denominator:.1%}" if denominator else "—"


def render_export_case(events: pd.DataFrame) -> None:
    st.subheader("用户已经采纳建议，接下来还有多少任务导出了报告？")
    funnel = funnel_counts(events, unit="tasks").set_index("event_name")
    adopted = int(funnel.at["adopt_suggestion", "reached"])
    exported = int(funnel.at["export_report", "reached"])
    lost = adopted - exported

    cols = st.columns(3)
    cols[0].metric("至少采纳一条", f"{adopted:,} 个任务")
    cols[1].metric("采纳后未导出", f"{lost:,} 个任务")
    cols[2].metric("采纳后导出率", percent(exported, adopted))
    st.caption(
        f"{exported:,} 个任务按顺序到达导出 ÷ {adopted:,} 个已采纳任务。同一任务在每一步只计一次。"
    )

    st.markdown("**还缺的证据**")
    st.write(
        "未导出的任务里，有人可能没找到入口，也有人看完建议就达到了目的。可以在后续体验中询问用户是否想保留报告，并记录导出提示是否出现、是否被点击。"
    )
    with st.container(border=True):
        st.markdown("**怎么验证导出引导**")
        st.write(
            "按用户随机分组，同一用户固定在一组。对照组保留原入口，实验组在首次采纳后增加一条导出提示。两组保留相同的报告内容和其余操作。"
        )
        st.write(
            "主指标用采纳后导出的任务数除以至少采纳一条的任务数，两组使用相同观察期。同时比较有效优化任务数占全部生成任务的比例。"
        )
        st.write(
            "护栏看还有剩余建议的任务中，有多少在首次采纳后继续处理了建议，以判断提示是否打断后续修改。"
        )


def render_template_case(suggestions: pd.DataFrame) -> None:
    st.subheader("先改哪类内容，改完如何判断有效？")
    summary = suggestion_outcomes(suggestions, "suggestion_type")
    focus = "项目表达"
    if focus not in summary.index:
        st.info("当前样本没有项目表达类建议，无法比较这套模板。")
        return

    row = summary.loc[focus]
    cols = st.columns(3)
    cols[0].metric("样本建议类型", f"{len(summary)} 类")
    cols[1].metric("项目表达被拒绝", f"{row['rejected']:,} 条")
    cols[2].metric("项目表达拒绝率", percent(row["rejected"], row["generated"]))
    st.caption(
        f"明确拒绝 {row['rejected']:,} 条 ÷ 生成 {row['generated']:,} 条。分母取生成记录，样本没有单独的建议曝光事件。"
    )

    remaining = summary.drop(index=focus)
    if not remaining.empty:
        label = "其他类型合计"
        selection = st.selectbox("和哪类建议比较", [label, *remaining.index], key="ops_comparison")
        reference = remaining.sum() if selection == label else remaining.loc[selection]
        comparison = pd.DataFrame([row, reference], index=[focus, selection])
        chart = go.Figure(
            go.Bar(
                x=comparison["rejected"] / comparison["generated"],
                y=comparison.index,
                orientation="h",
                marker_color=["#B35D2C", "#14695D"],
                customdata=comparison[["rejected", "generated"]],
                texttemplate="%{x:.1%}",
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>拒绝 %{customdata[0]} 条 / 生成 %{customdata[1]} 条<extra></extra>",
            )
        )
        chart.update_layout(
            height=145,
            margin=dict(l=0, r=45, t=5, b=0),
            showlegend=False,
            xaxis=dict(tickformat=".0%", rangemode="tozero", title=None),
            yaxis=dict(autorange="reversed", title=None),
            bargap=0.5,
        )
        st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
        st.caption(
            f"{selection}明确拒绝 {reference['rejected']:,} 条，共生成 {reference['generated']:,} 条。"
        )
    with st.expander("查看各类型建议的数量与处理结果"):
        table = (
            summary.rename(
                columns={
                    "generated": "生成",
                    "adopted": "采纳",
                    "rejected": "拒绝",
                    "pending": "待处理",
                }
            )
            .rename_axis("建议类型")
            .reset_index()
        )
        table["拒绝率"] = (table["拒绝"] / table["生成"]).map("{:.1%}".format)
        st.dataframe(table, hide_index=True, width="stretch")

    st.markdown("**还缺的证据**")
    st.write(
        "固定样本只记录处理状态，没有拒绝原因。未处理的建议单独计数。可以抽查被拒绝的项目表达建议，让用户自愿说明原因，未回答的保留为空。"
    )
    with st.container(border=True):
        st.markdown("**怎么验证项目表达模板**")
        st.write(
            "按用户随机分组。对照组继续用现有模板，实验组先引用简历原句，再给出基于该句的改写。两组保持建议位置与每次生成的条数一致。"
        )
        st.write(
            "主指标用组内被采纳的项目表达建议数除以组内生成的同类建议数。同步看拒绝率和待处理率，防止把未响应当成满意。"
        )
        st.write(
            "护栏用人工抽检中含无依据经历或数字的改写条数除以抽检条数。比较时同时给出两组的建议数和参与用户数。"
        )


def render_simulated_groups(suggestions: pd.DataFrame) -> None:
    with st.expander("模拟 A/B 计算示例"):
        summary = suggestion_outcomes(suggestions, "prompt_group")
        if not {"A", "B"}.issubset(summary.index):
            st.caption("两组都需要有生成记录才能比较。")
            return
        rows = summary.loc[["A", "B"], ["generated", "adopted"]].copy()
        rates = rows["adopted"] / rows["generated"]
        rows["建议采纳率"] = rates.map("{:.1%}".format)
        rows = rows.rename(columns={"generated": "生成建议数", "adopted": "采纳建议数"})
        st.dataframe(rows.rename_axis("模板组").reset_index(), hide_index=True, width="stretch")
        difference = (rates.at["B"] - rates.at["A"]) * 100
        st.write(
            f"B 组减 A 组为 {difference:+.1f} 个百分点。模拟脚本按任务分组并预设 B 组采纳概率较高，同一用户可参与多次任务。真实模板效果需要另行验证。"
        )


def render_operations(tables: dict[str, pd.DataFrame]) -> None:
    st.header("运营诊断与验证")
    st.write(
        "用固定模拟样本选择一个值得验证的改动。下列两项实验均尚未上线，页面展示验证方案与判断指标。"
    )
    choice = st.radio(
        "选择要验证的运营动作",
        ["采纳后导出引导", "项目表达模板"],
        horizontal=True,
        key="ops_case",
    )
    if choice == "采纳后导出引导":
        render_export_case(tables["events"])
    else:
        render_template_case(tables["suggestions"])
    render_simulated_groups(tables["suggestions"])
