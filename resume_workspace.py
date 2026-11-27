"""Interactive résumé review. Drafts, reports and events belong to one session."""

from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
import streamlit as st

from logic.resume_analyzer import (
    analyze_resume_gaps,
    build_report_markdown,
    calculate_match_score,
    extract_jd_keywords,
    generate_suggestions,
)

SAMPLE_RESUME = """项目经历：简历优化助手的产品分析
设计用户行为分析框架，梳理从上传简历到生成建议的转化路径。
使用 Python 清洗模拟日志，用图表展示分析结果，并整理产品优化建议。

技能：Excel、Python、基础 SQL、数据可视化。"""

SAMPLE_JD = """负责产品数据分析，搭建指标体系与转化漏斗。
使用 SQL 和 Python 清洗用户行为数据，搭建 BI 看板。
参与 A/B 实验设计、Prompt 模板评估，向产品团队解释建议采纳与用户增长表现。"""

STATUS = {"pending": "待处理", "adopted": "已采纳", "rejected": "未采纳"}


def init_workspace():
    defaults = {
        "draft_resume": SAMPLE_RESUME,
        "draft_jd": SAMPLE_JD,
        "draft_group": "B",
        "draft_user_type": "应届生",
        "review": None,
        "event_log": [],
    }
    for name, value in defaults.items():
        st.session_state.setdefault(name, value)
    if "demo_session" not in st.session_state:
        st.session_state.demo_session = uuid4().hex
        log_event(None, "open_workbench")


def save_edit(field):
    st.session_state[field] = st.session_state["edit_" + field]


def load_upload():
    upload = st.session_state.resume_upload
    if upload is None:
        return
    raw = upload.getvalue()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            resume = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        st.session_state.upload_notice = "无法读取文件编码，请直接粘贴简历或另存为 UTF-8 文本。"
        return
    st.session_state.draft_resume = resume
    st.session_state.edit_draft_resume = resume
    st.session_state.upload_notice = None
    log_event(None, "import_resume_file")


def log_event(review, event, suggestion_id=None):
    context = review or {}
    st.session_state.event_log.append(
        {
            "event_id": uuid4().hex,
            "task_id": context.get("id"),
            "session_id": st.session_state.demo_session,
            "user_id": "demo_user",
            "user_type": context.get("user_type"),
            "event_time": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "event_name": event,
            "prompt_group": context.get("group"),
            "suggestion_id": suggestion_id,
        }
    )


def set_status(index, status):
    review = st.session_state.review
    item = review["suggestions"][index]
    if item["status"] != status:
        item["status"] = status
        item["adopted"] = status == "adopted"
        review["last_action"] = item["suggestion_id"]
        log_event(
            review,
            "adopt_suggestion" if item["adopted"] else "reject_suggestion",
            item["suggestion_id"],
        )


def record_export():
    log_event(st.session_state.review, "export_report")


def render_workspace():
    init_workspace()
    state = st.session_state
    st.header("简历工作台")
    st.write(
        "用示例或自己的简历对照岗位要求，查看每条建议对应的原文，并导出修改清单。输入和处理记录仅在本次会话中使用。"
    )
    for field in ("draft_resume", "draft_jd", "draft_group", "draft_user_type"):
        state.setdefault("edit_" + field, state[field])
    with st.expander("从 TXT 或 Markdown 文件导入简历"):
        st.file_uploader("选择简历文件", type=["txt", "md"], key="resume_upload", on_change=load_upload)
        if state.get("upload_notice"):
            st.warning(state.upload_notice)
    left, right = st.columns(2)
    left.text_area(
        "简历原文", height=200, key="edit_draft_resume", on_change=save_edit, args=("draft_resume",)
    )
    right.text_area(
        "岗位描述（JD）", height=200, key="edit_draft_jd", on_change=save_edit, args=("draft_jd",)
    )
    group_col, profile_col = st.columns(2)
    group_col.radio(
        "建议模板",
        ["A", "B"],
        horizontal=True,
        key="edit_draft_group",
        format_func=lambda g: "A · 通用表达" if g == "A" else "B · 对照岗位原文",
        on_change=save_edit,
        args=("draft_group",),
    )
    profile_col.selectbox(
        "体验身份",
        ["应届生", "实习生", "转行用户"],
        key="edit_draft_user_type",
        help="记录在本次任务日志中，用于演示用户分群。",
        on_change=save_edit,
        args=("draft_user_type",),
    )
    inputs = {
        "resume": state.draft_resume.strip(),
        "jd": state.draft_jd.strip(),
        "group": state.draft_group,
        "user_type": state.draft_user_type,
    }
    review = state.review
    current = review is not None and all(review[k] == v for k, v in inputs.items())
    if st.button("生成优化建议", type="primary", disabled=current):
        if not inputs["resume"] or not inputs["jd"]:
            st.warning("请填写简历和岗位描述。")
        else:
            review = dict(inputs, id=uuid4().hex[:12])
            review["suggestions"] = generate_suggestions(
                inputs["resume"], inputs["jd"], review["id"], "demo_user", inputs["group"]
            )
            state.review = review
            if review["suggestions"]:
                outcome = "generate_suggestion"
            elif extract_jd_keywords(inputs["jd"]):
                outcome = "review_complete"
            else:
                outcome = "unsupported_jd"
            log_event(review, "submit_inputs")
            log_event(review, outcome)
            st.rerun()
    if current:
        render_review(review)
    elif review:
        st.info("输入已更改。重新生成后即可处理或导出与当前输入对应的建议。")
    if state.event_log:
        with st.expander("本次会话的任务日志"):
            st.caption(
                "进入工作台、导入文件、提交文本、生成结果、处理建议和点击下载均按实际操作记录。日志使用 UTC 时间。"
            )
            st.dataframe(pd.DataFrame(state.event_log), hide_index=True, width="stretch")


def render_review(review):
    items = review["suggestions"]
    gaps = analyze_resume_gaps(review["resume"], review["jd"])
    keywords = extract_jd_keywords(review["jd"])
    st.subheader("岗位要求与简历证据")
    if not keywords:
        st.info("此岗位描述未命中当前规则词库，暂时无法计算覆盖率。可补充具体职责或技能要求后重试。")
        return
    score = calculate_match_score(review["resume"], review["jd"])
    adopted = sum(x["status"] == "adopted" for x in items)
    pending = sum(x["status"] == "pending" for x in items)
    cols = st.columns(3)
    cols[0].metric("关键词覆盖率", f"{score}%", help="简历中匹配到的要求数 ÷ 规则识别的岗位要求数。")
    cols[1].metric("已采纳建议", f"{adopted} 条")
    cols[2].metric("待处理建议", f"{pending} 条")
    with st.expander(f"查看 {len(keywords)} 项岗位要求和对应原文", expanded=not items):
        st.dataframe(pd.DataFrame(gaps), hide_index=True, width="stretch")
    if not items:
        st.success("已识别的要求均有经历证据。可以导出本次检查结果。")
    else:
        st.subheader("修改清单")
        st.caption("采纳表示计划采用这条建议。修改简历原文并重新生成后，才会重新计算覆盖率。")
    report = build_report_markdown(review["resume"], review["jd"], items, score, score)
    download = dict(
        data=report,
        file_name=f"简历修改清单_{review['id']}.md",
        mime="text/markdown",
        on_click=record_export,
    )
    st.download_button("导出本次报告（Markdown）", key="download_review", **download)
    for index, item in enumerate(items):
        with st.container(border=True):
            st.markdown(f"#### {item['matched_keyword']} · {STATUS[item['status']]}")
            st.write(item["current_problem"])
            st.write(item["suggestion"])
            with st.expander("对照原文，查看填写模板"):
                for label, value in (
                    ("岗位原文", item.get("jd_evidence")),
                    ("简历原文", item["original_expression"]),
                    ("填写模板", item["revised_expression"]),
                ):
                    if value:
                        st.markdown(f"**{label}**")
                        st.text(value)
            yes, no, next_step = st.columns([1, 1, 3])
            for col, status, label in ((yes, "adopted", "采纳"), (no, "rejected", "不采纳")):
                col.button(
                    label,
                    key=f"{status}_{item['suggestion_id']}",
                    disabled=item["status"] == status,
                    on_click=set_status,
                    args=(index, status),
                    width="stretch",
                )
            if review.get("last_action") == item["suggestion_id"] and item["status"] == "adopted":
                next_step.download_button("导出当前修改清单", key="after_adoption", **download)
