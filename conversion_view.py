import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis_data import filter_cohort, funnel_counts, segment_export

TEAL = "#14695D"
AMBER = "#B35D2C"


def _percent(value):
    return "—" if pd.isna(value) else f"{value:.1%}"


def render_conversion(tables):
    st.header("简历优化在哪一步流失？")
    cohort_col, unit_col = st.columns(2)
    profiles = [
        "全部人群",
        *tables["users"]["user_type"].dropna().drop_duplicates().sort_values().tolist(),
    ]
    # Streamlit removes hidden widgets on page changes. Keep the reader's selection.
    last_cohort, last_measure = st.session_state.get("last_conversion_scope", ("全部人群", "按任务"))
    st.session_state.setdefault(
        "conversion_cohort", last_cohort if last_cohort in profiles else "全部人群"
    )
    st.session_state.setdefault("conversion_measure", last_measure)
    cohort = cohort_col.selectbox("查看人群", profiles, key="conversion_cohort")
    measure = unit_col.radio(
        "统计口径", ["按任务", "按用户"], horizontal=True, key="conversion_measure"
    )
    st.session_state["last_conversion_scope"] = (cohort, measure)
    unit = "tasks" if measure == "按任务" else "users"
    noun, counter = ("任务", "个任务") if unit == "tasks" else ("用户", "人")
    selected = filter_cohort(tables, cohort)
    funnel = funnel_counts(selected["events"], unit)
    if unit == "tasks":
        st.caption("同一任务须按时间依次完成各步，多次采纳只计一次。同一用户发起的不同任务分别计数。")
    else:
        st.caption("每一步统计至少有一个任务依次走到该步的去重用户。同一人有多个任务也只计一次。")

    transitions = funnel.loc[funnel["previous"].gt(0).fillna(False)]
    peak = transitions["loss_rate"].idxmax() if not transitions.empty else None
    chart, detail = st.columns([1.55, 1])
    with chart:
        fig = go.Figure(
            go.Bar(
                x=funnel["reached"],
                y=funnel["step"],
                orientation="h",
                marker_color=[AMBER if index == peak else TEAL for index in funnel.index],
                text=funnel["reached"].map(lambda x: f"{x:,}"),
                textposition="outside",
                cliponaxis=False,
                hovertemplate=f"%{{y}}<br>到达%{{x:,}}{counter}<extra></extra>",
            )
        )
        fig.update_layout(
            height=258,
            margin=dict(l=5, r=48, t=12, b=5),
            bargap=0.46,
            xaxis=dict(visible=False, range=[0, max(1, funnel["reached"].max()) * 1.16]),
            yaxis=dict(autorange="reversed", automargin=True, fixedrange=True),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with detail:
        if peak is None:
            st.info("当前人群没有足够的连续事件计算环节流失率。")
        else:
            stage, previous = funnel.loc[peak], funnel.loc[peak - 1]
            st.metric("最高环节流失率", _percent(stage.loss_rate))
            st.markdown(f"**{previous.step} → {stage.step}**")
            st.write(
                f"{int(stage.previous):,} {counter}走到了上一步，{int(stage.reached):,} {counter}继续到达这一步，流失 {int(stage.lost):,} {counter}。"
            )
    reached = funnel.set_index("event_name")["reached"]
    generated, adopted, exported = (
        int(reached[name]) for name in ("generate_suggestion", "adopt_suggestion", "export_report")
    )
    after_adoption = exported / adopted if adopted else float("nan")
    after_generation = exported / generated if generated else float("nan")
    st.markdown(
        f"**采纳后导出率**　{exported:,} / {adopted:,} = {_percent(after_adoption)}，有 {adopted - exported:,} {counter}已采纳但未导出。"
    )
    st.markdown(
        f"**已生成建议的{noun}中，采纳并导出的比例**　{exported:,} / {generated:,} = {_percent(after_generation)}。"
    )
    with st.expander("核对每一步的分子与分母"):
        ledger = funnel[["step", "previous", "reached", "lost", "conversion_rate", "loss_rate"]].copy()
        ledger.columns = [
            "步骤",
            f"上一步{noun}数",
            f"本步{noun}数",
            f"流失{noun}数",
            "环节转化率",
            "环节流失率",
        ]
        for column in ["环节转化率", "环节流失率"]:
            ledger[column] = ledger[column].map(_percent)
        st.dataframe(ledger, hide_index=True, width="stretch")

    st.subheader("采纳建议后，先关注哪类人群？")
    groups = segment_export(tables, unit)
    st.caption(
        f"以下对照始终展示全体人群，沿用上方{measure}口径。导出率的分母为至少采纳一条建议的{noun}数。"
    )
    if not groups["adopted"].sum():
        st.info("样本中没有到达采纳环节的记录。")
        return
    view = groups.copy()
    for column in ["export_rate", "loss_share"]:
        view[column] = view[column].map(_percent)
    view.columns = [
        "人群",
        f"已采纳{noun}数",
        f"已导出{noun}数",
        f"未导出{noun}数",
        "采纳后导出率",
        "占全部未导出",
    ]
    st.dataframe(view, hide_index=True, width="stretch")
    with st.expander("情景测算 · 相同的导出率增幅，各人群能多导出多少？"):
        lift = st.number_input(
            "假设采纳后导出率增加的百分点",
            min_value=0.0,
            max_value=100.0,
            value=5.0,
            step=0.5,
            key="conversion_lift",
        )
        scenario = groups[["user_type", "adopted", "lost"]].copy()
        scenario["increment"] = (
            (scenario["adopted"] * (lift / 100)).clip(upper=scenario["lost"]).round(2)
        )
        scenario.columns = ["人群", f"已采纳{noun}数", f"当前未导出{noun}数", f"推算新增导出{noun}数"]
        st.dataframe(scenario, hide_index=True, width="stretch")
        st.caption(
            f"以各人群已采纳{noun}数乘以 {lift:g}%，新增量最多等于该人群当前未导出的{noun}数。"
            "该测算只展示假设情景，实际增幅仍待验证、实施成本也未知。应结合对照试点测得的新增导出量和成本决定是否推广。"
        )
    valid = groups.loc[groups["adopted"].gt(0)]
    if int(valid["lost"].sum()) == 0:
        st.write("所有已采纳的样本均已导出。")
        return
    most_loss = valid[valid["lost"].eq(valid["lost"].max())]
    lowest = valid[valid["export_rate"].eq(valid["export_rate"].min())]
    volume_name, rate_name = "、".join(most_loss["user_type"]), "、".join(lowest["user_type"])
    volume, rate = most_loss.iloc[0], lowest.iloc[0]
    st.markdown("**如果只能先做一次试点**")
    each = "各" if len(most_loss) > 1 else ""
    st.write(
        f"若优先覆盖更多未导出的{noun}，可先选{volume_name}，其中{each}有 {int(volume.lost):,} {counter}采纳后未导出，"
        f"{each}占全部未导出的 {_percent(volume.loss_share)}。若要调查转化困难的人群，可先访谈{rate_name}，其采纳后导出率最低，为 {_percent(rate.export_rate)}。"
    )
    if cohort != "全部人群":
        focus = groups.loc[groups["user_type"].eq(cohort)]
        if not focus.empty and focus.iloc[0].adopted:
            row = focus.iloc[0]
            st.caption(
                f"当前所选的{cohort}中，{int(row.adopted)} {counter}采纳过建议，{int(row.exported)} {counter}随后导出。"
            )
    st.caption("以上为固定模拟样本。可向采纳后未导出的体验者询问原因，再测试报告预览或导出提醒。")
