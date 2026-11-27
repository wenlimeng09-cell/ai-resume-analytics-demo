"""Session-scoped résumé review for the portfolio's interactive tool page."""

import hmac
import os
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
import streamlit as st

from logic.resume_analyzer import analyze_resume_gaps, build_report_markdown, generate_suggestions
from logic.resume_parser import ResumeParseError, parse_resume_file

SAMPLES = {
    "数据分析": (
        "在虚构的零售项目中，用 SQL 按门店汇总每日订单，核对退款口径。\n用 Excel 维护销售日报，反馈异常订单。\n技能：Python。",
        "使用 SQL 对照交易明细核对指标口径，用 Python 清洗日志。搭建 BI 看板跟踪门店订单，参与 A/B 实验评估。",
    ),
    "商业分析": (
        "在虚构的连锁经营项目中，按月核算各品类毛利率并核对采购成本。\n整理商品促销价格，向门店负责人提交经营复盘表。",
        "开展经营分析，按品类拆解毛利率，明确指标口径。使用 Excel 和 SQL 对照促销期间的投入产出，为补货决策提供依据。",
    ),
    "运营分析": (
        "在虚构的校园市集活动中，负责整理报名渠道和签到明细。\n用 Excel 汇总各渠道报名人数，在活动复盘中比较到场情况。",
        "参与活动运营，跟踪报名至到场的转化漏斗，通过用户访谈补充流失原因，并制定活动效果评估方案。",
    ),
}
ENGINES = {"mock": "规则引擎", "deepseek": "DeepSeek"}
GROUPS = {"A": "通用表达", "B": "对照岗位要求"}
STATUS = {"pending": "待处理", "adopted": "已采纳", "rejected": "已拒绝"}
REASONS = ["建议太泛", "不符合目标岗位", "并无这段经历", "已经写过", "表达不自然", "其他"]
RESUME_LIMIT, JD_LIMIT = 12_000, 8_000


def _init_state():
    state = st.session_state
    resume, jd = SAMPLES["数据分析"]
    state.setdefault("tool_draft", {"resume": resume, "jd": jd, "group": "B", "engine": "mock"})
    state.setdefault("tool_review", None)
    state.setdefault("tool_events", [])
    if "tool_session_id" not in state:
        state.tool_session_id = uuid4().hex[:12]
    state.setdefault("tool_upload_version", 0)
    state.setdefault("tool_upload_message", None)
    state.setdefault("tool_requests", 0)
    state.setdefault("tool_unlocked", False)
    for field, value in state.tool_draft.items():
        state.setdefault("tool_input_" + field, value)


def _save_field(field):
    state = st.session_state
    state.tool_draft[field] = state["tool_input_" + field]
    if field == "resume":
        state.tool_upload_message = None


def _load_sample():
    state = st.session_state
    for name, text in zip(("resume", "jd"), SAMPLES[state.tool_sample]):
        state.tool_draft[name] = text
        state["tool_input_" + name] = text
    state.tool_upload_version += 1
    state.tool_upload_message = None


def _import_file(widget_key):
    state = st.session_state
    upload = state[widget_key]
    state.tool_upload_message = None
    if upload is None:
        return
    try:
        parsed = parse_resume_file(upload.name, upload.getvalue(), max_chars=RESUME_LIMIT)
    except ResumeParseError as error:
        state.tool_upload_message = ("error", str(error))
        return
    state.tool_draft["resume"] = parsed.text
    state.tool_input_resume = parsed.text
    detail = f"已从 {parsed.file_type} 导入 {parsed.char_count} 字，可在下方修改。"
    state.tool_upload_message = (
        "warning" if parsed.warnings else "success",
        " ".join([detail, *parsed.warnings]),
    )


def _settings():
    def get(name, default=""):
        try:
            return str(st.secrets.get(name, os.environ.get(name, default)) or "").strip()
        except FileNotFoundError:
            return os.environ.get(name, default).strip()

    try:
        quota = int(get("MAX_LLM_CALLS_PER_SESSION", "3"))
    except ValueError:
        quota = 3
    return (
        get("DEEPSEEK_API_KEY"),
        get("DEMO_ACCESS_CODE"),
        get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        min(10, max(1, quota)),
    )


def _unlock(expected):
    state = st.session_state
    entered = state.tool_access_code
    state.tool_unlocked = hmac.compare_digest(entered.encode(), expected.encode())
    state.tool_unlock_failed = not state.tool_unlocked
    state.tool_access_code = ""


def _model_options(settings):
    key, code, model, quota = settings
    state = st.session_state
    st.caption(f"生成时会将当前简历和岗位描述发送至 DeepSeek（{model}），请使用虚构或已脱敏的文本。")
    if not key or not code:
        st.info("此部署尚未配置模型体验，可选择规则引擎。")
        return False
    if not state.tool_unlocked:
        with st.form("tool_unlock_form"):
            st.text_input("演示访问码", type="password", key="tool_access_code")
            st.form_submit_button("解锁模型", on_click=_unlock, args=(code,))
        if state.get("tool_unlock_failed"):
            st.warning("访问码不正确。")
        return False
    remaining = max(0, quota - state.tool_requests)
    st.caption(f"本会话剩余 {remaining} 次模型请求，重试也计入次数。")
    return remaining > 0


def _reserve_request(quota):
    from logic.llm_provider import LLMProviderError

    if st.session_state.tool_requests >= quota:
        raise LLMProviderError("Session quota exhausted")
    st.session_state.tool_requests += 1


def _record_event(event_name, task_id, provider, suggestion_id=None):
    state = st.session_state
    state.tool_events.append(
        {
            "time_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "session_id": state.tool_session_id,
            "task_id": task_id,
            "event_name": event_name,
            "provider": provider,
            "suggestion_id": suggestion_id,
        }
    )


def _generate(draft, settings):
    review = {"input": dict(draft), "id": uuid4().hex[:16], "provider": draft["engine"]}
    _record_event("submit_diagnosis", review["id"], draft["engine"])
    args = (draft["resume"], draft["jd"], review["id"], "demo", draft["group"])
    if draft["engine"] == "deepseek":
        from logic.llm_provider import LLMProviderError

        key, _, model, quota = settings
        try:
            suggestions = generate_suggestions(
                *args,
                suggestion_provider="deepseek",
                provider_config={
                    "api_key": key,
                    "model": model,
                    "before_request": lambda: _reserve_request(quota),
                },
            )
        except LLMProviderError:
            review["provider"] = "fallback"
            _record_event("fallback_to_rules", review["id"], review["provider"])
            suggestions = generate_suggestions(*args)
    else:
        suggestions = generate_suggestions(*args)
    review["suggestions"] = suggestions
    review["gaps"] = analyze_resume_gaps(draft["resume"], draft["jd"])
    if suggestions:
        outcome = "generate_suggestion"
    elif review["gaps"]:
        outcome = "review_covered"
    else:
        outcome = "unsupported_jd"
    _record_event(outcome, review["id"], review["provider"])
    return review


def _set_decision(index, status):
    review = st.session_state.tool_review
    item = review["suggestions"][index]
    if item["status"] == status:
        return
    item["status"] = status
    item["adopted"] = {"pending": None, "adopted": True, "rejected": False}[status]
    if status != "rejected":
        item["reject_reason"] = ""
        st.session_state.pop("reason_" + item["suggestion_id"], None)
    events = {
        "adopted": "adopt_suggestion",
        "rejected": "reject_suggestion",
        "pending": "defer_suggestion",
    }
    _record_event(events[status], review["id"], review["provider"], item["suggestion_id"])


def _save_reason(index, key):
    item = st.session_state.tool_review["suggestions"][index]
    item["reject_reason"] = st.session_state.get(key) or ""


def _render_result(review):
    items, gaps = review["suggestions"], review["gaps"]
    provider = review["provider"]
    if provider == "fallback":
        st.warning("模型请求未完成或输出未通过校验。本次结果由规则引擎生成。")
    else:
        st.caption(f"本次使用{ENGINES[provider]} · {GROUPS[review['input']['group']]}")
    covered = sum(bool(row["简历原文"]) for row in gaps)
    adopted = sum(item["status"] == "adopted" for item in items)
    pending = sum(item["status"] == "pending" for item in items)
    metrics = st.columns(3)
    score = round(100 * covered / len(gaps)) if gaps else 0
    metrics[0].metric(
        "岗位关键词覆盖率",
        f"{score}% · {covered}/{len(gaps)}" if gaps else "暂无",
        help="当前简历提及的关键词类别数 ÷ 规则识别出的岗位类别数。仅提及技能也计入。",
    )
    metrics[1].metric("已采纳", f"{adopted} 条")
    metrics[2].metric("待处理", f"{pending} 条")
    if gaps:
        with st.expander("查看岗位要求和简历原句", expanded=not items):
            st.dataframe(
                pd.DataFrame(gaps)[["JD 要求", "简历覆盖状态", "JD 原文", "简历原文"]],
                hide_index=True,
                width="stretch",
            )
    else:
        st.info("这段岗位描述尚未命中规则词库，无法计算关键词覆盖率。")
    if not items and gaps:
        st.success("已识别的岗位要求均有相应工作动作的表述。")
    if items:
        st.caption("采纳表示计划修改。可先导出清单，修改原文后再生成并比较覆盖率。")
    for index, item in enumerate(items):
        status = item["status"]
        with st.expander(f"{item['matched_keyword']} · {STATUS[status]}", expanded=index == 0):
            st.write(item["current_problem"])
            for label, field in (("岗位依据", "jd_evidence"), ("简历原句", "original_expression")):
                if item.get(field):
                    st.caption(label)
                    st.text(item[field])
            st.write(item["suggestion"])
            st.caption(
                "模型改写草稿 · 请核对职责与结果"
                if provider == "deepseek"
                else "填写模板 · 按真实经历补全"
            )
            st.text(item["revised_expression"])
            if provider == "deepseek" and item.get("modification_reason"):
                st.caption("修改理由")
                st.write(item["modification_reason"])
            cols = st.columns(3)
            for col, decision, label in zip(
                cols, ("adopted", "rejected", "pending"), ("采纳", "拒绝", "暂不处理")
            ):
                col.button(
                    label,
                    key=f"{decision}_{item['suggestion_id']}",
                    disabled=status == decision,
                    on_click=_set_decision,
                    args=(index, decision),
                    width="stretch",
                )
            if status == "rejected":
                key = "reason_" + item["suggestion_id"]
                reason = item.get("reject_reason")
                st.selectbox(
                    "拒绝原因（选填）",
                    REASONS,
                    index=REASONS.index(reason) if reason in REASONS else None,
                    placeholder="请选择原因",
                    key=key,
                    on_change=_save_reason,
                    args=(index, key),
                )
    draft = review["input"]
    report = build_report_markdown(draft["resume"], draft["jd"], items, score, score)
    st.download_button(
        "导出修改清单",
        report,
        file_name=f"简历修改清单_{review['id']}.md",
        mime="text/markdown",
        key="download_" + review["id"],
        on_click=_record_event,
        args=("click_download", review["id"], review["provider"]),
    )


def render_tool():
    _init_state()
    state = st.session_state
    st.subheader("简历与岗位诊断")
    st.caption("选用虚构示例，或贴入自己的脱敏材料。输入、选择和报告保存在当前会话。")
    a, b = st.columns([2, 1], vertical_alignment="bottom")
    a.selectbox("虚构岗位示例", list(SAMPLES), key="tool_sample")
    b.button("载入示例", on_click=_load_sample)
    with st.expander("从 PDF、DOCX、TXT 或 Markdown 导入简历"):
        key = f"tool_upload_{state.tool_upload_version}"
        st.file_uploader(
            "上传简历",
            type=["pdf", "docx", "txt", "md"],
            key=key,
            on_change=_import_file,
            args=(key,),
            help="PDF 需含可复制文字。",
        )
    notice = state.tool_upload_message
    if notice:
        getattr(st, notice[0])(notice[1])
    left, right = st.columns(2)
    left.text_area(
        "简历原文",
        height=160,
        max_chars=RESUME_LIMIT,
        key="tool_input_resume",
        on_change=_save_field,
        args=("resume",),
    )
    right.text_area(
        "目标岗位描述",
        height=160,
        max_chars=JD_LIMIT,
        key="tool_input_jd",
        on_change=_save_field,
        args=("jd",),
    )
    settings = None
    ready = True
    with st.expander("生成方式", expanded=state.tool_draft["engine"] == "deepseek"):
        c, d = st.columns(2)
        c.radio(
            "建议策略",
            list(GROUPS),
            format_func=GROUPS.get,
            horizontal=True,
            key="tool_input_group",
            on_change=_save_field,
            args=("group",),
        )
        d.radio(
            "生成引擎",
            list(ENGINES),
            format_func=ENGINES.get,
            horizontal=True,
            key="tool_input_engine",
            on_change=_save_field,
            args=("engine",),
        )
        if state.tool_draft["engine"] == "deepseek":
            settings = _settings()
            ready = _model_options(settings)
    draft = {name: value.strip() for name, value in state.tool_draft.items()}
    review = state.tool_review
    current = review is not None and draft == review["input"]
    bad_upload = notice and notice[0] == "error"
    if st.button(
        "生成诊断",
        type="primary",
        disabled=bool(current or not ready or bad_upload or not draft["resume"] or not draft["jd"]),
    ):
        with st.spinner("正在对照岗位要求和简历表述…"):
            state.tool_review = _generate(draft, settings)
        st.rerun()
    if current and not bad_upload:
        _render_result(review)
    elif review:
        st.info("材料或生成选项已更换，重新生成后可处理和导出这次诊断。")

    with st.expander("查看本次体验的行为记录"):
        st.caption("以下记录仅保存在当前会话。下载记录表示点击了导出按钮，时间采用 UTC。")
        if state.tool_events:
            events = pd.DataFrame(state.tool_events)
            event_labels = {
                "submit_diagnosis": "提交诊断",
                "generate_suggestion": "生成建议",
                "review_covered": "已覆盖，无需建议",
                "unsupported_jd": "未识别岗位要求",
                "fallback_to_rules": "模型失败，切换规则",
                "adopt_suggestion": "采纳建议",
                "reject_suggestion": "拒绝建议",
                "defer_suggestion": "恢复待处理",
                "click_download": "点击下载",
            }
            events["event_name"] = events["event_name"].map(event_labels)
            events["provider"] = events["provider"].map({**ENGINES, "fallback": "规则引擎（回退）"})
            st.dataframe(
                events.rename(
                    columns={
                        "time_utc": "发生时间 (UTC)",
                        "session_id": "会话 ID",
                        "task_id": "任务 ID",
                        "event_name": "事件",
                        "provider": "引擎",
                        "suggestion_id": "建议 ID",
                    }
                ),
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("提交首次诊断后即可查看。")
