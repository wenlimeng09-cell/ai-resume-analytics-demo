from __future__ import annotations

import sys
from datetime import datetime
from html import escape
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
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}
CHART_COLORS = ["#176B5B", "#D28A32", "#5C7C74", "#C65D4B", "#7D8F89"]
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


st.set_page_config(
    page_title="AI 简历优化助手 MVP",
    page_icon="AI",
    layout="wide",
    initial_sidebar_state="auto",
)


def inject_portfolio_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ink: #18211f;
            --muted: #68736f;
            --line: #dfe6e2;
            --canvas: #f4f7f5;
            --surface: #ffffff;
            --brand: #176b5b;
            --brand-dark: #123f36;
            --brand-soft: #e8f3ef;
            --amber: #a86516;
            --amber-soft: #fff3df;
            --coral: #a94f43;
            --coral-soft: #fff0ed;
        }

        .stApp {
            background: var(--canvas);
            color: var(--ink);
        }

        [data-testid="stDecoration"] {
            background: var(--brand);
        }

        [data-testid="stMainBlockContainer"] {
            max-width: 1420px;
            padding-top: 2rem;
            padding-bottom: 4rem;
        }

        h1, h2, h3, p, label, button {
            letter-spacing: 0 !important;
        }

        h1, h2, h3 {
            color: var(--ink);
        }

        .case-hero {
            position: relative;
            overflow: hidden;
            background: var(--brand-dark);
            color: #ffffff;
            border-radius: 8px;
            padding: 2.35rem 2.5rem 2.15rem;
            margin: 0 0 1rem;
            box-shadow: 0 16px 36px rgba(18, 63, 54, 0.13);
        }

        .case-hero::after {
            content: "01";
            position: absolute;
            right: 2rem;
            bottom: -1.45rem;
            color: rgba(255, 255, 255, 0.055);
            font-size: 9rem;
            font-weight: 800;
            line-height: 1;
        }

        .case-kicker {
            color: #a9d6c9;
            font-size: 0.75rem;
            font-weight: 750;
            margin-bottom: 0.65rem;
        }

        .case-title {
            color: #ffffff;
            font-size: clamp(1.85rem, 3vw, 2.8rem);
            font-weight: 780;
            line-height: 1.2;
            margin: 0;
            max-width: 900px;
        }

        .case-copy {
            color: #d8e7e2;
            font-size: 0.98rem;
            line-height: 1.75;
            margin: 0.85rem 0 1.2rem;
            max-width: 880px;
        }

        .case-tags,
        .keyword-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.42rem;
        }

        .case-tag {
            display: inline-flex;
            align-items: center;
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 999px;
            color: #f3f8f6;
            font-size: 0.74rem;
            font-weight: 650;
            padding: 0.32rem 0.66rem;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.3rem;
            overflow-x: auto;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 0.38rem;
            margin-bottom: 1.1rem;
            box-shadow: 0 5px 16px rgba(26, 47, 41, 0.04);
            scrollbar-width: none;
        }

        .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
            display: none;
        }

        .stTabs [data-baseweb="tab"] {
            flex: 0 0 auto;
            min-height: 2.6rem;
            border-radius: 6px;
            color: #53615c;
            font-weight: 650;
            padding: 0 0.9rem;
        }

        .stTabs [aria-selected="true"] {
            background: var(--brand-soft);
            color: var(--brand) !important;
        }

        .stTabs [data-baseweb="tab-highlight"] {
            display: none;
        }

        .page-intro {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            gap: 1rem;
            align-items: start;
            margin: 1.35rem 0 1.25rem;
        }

        .page-number {
            display: grid;
            place-items: center;
            width: 2.6rem;
            height: 2.6rem;
            border-radius: 7px;
            background: var(--brand);
            color: #ffffff;
            font-size: 0.78rem;
            font-weight: 750;
        }

        .page-kicker {
            color: var(--brand);
            font-size: 0.72rem;
            font-weight: 750;
            margin-bottom: 0.18rem;
        }

        .page-title {
            color: var(--ink);
            font-size: 1.5rem;
            font-weight: 760;
            line-height: 1.3;
            margin: 0;
        }

        .page-conclusion {
            color: var(--muted);
            font-size: 0.9rem;
            line-height: 1.65;
            margin-top: 0.3rem;
        }

        .section-heading {
            display: flex;
            align-items: center;
            gap: 0.55rem;
            color: var(--ink);
            font-size: 1.08rem;
            font-weight: 730;
            margin: 1.35rem 0 0.7rem;
        }

        .section-heading::before {
            content: "";
            width: 0.32rem;
            height: 1.05rem;
            border-radius: 2px;
            background: var(--amber);
        }

        div[data-testid="stMetric"] {
            min-height: 118px;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 7px;
            padding: 0.85rem 0.95rem;
            box-shadow: 0 5px 16px rgba(26, 47, 41, 0.035);
        }

        div[data-testid="stMetricLabel"] {
            color: var(--muted);
        }

        div[data-testid="stMetricValue"] {
            color: var(--ink);
            font-size: 1.65rem;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: var(--surface);
            border-color: var(--line);
            border-radius: 8px;
            box-shadow: 0 5px 18px rgba(26, 47, 41, 0.04);
        }

        .metric-help {
            color: var(--muted);
            font-size: 0.76rem;
            line-height: 1.55;
            margin-top: -0.35rem;
        }

        .logic-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 0.55rem;
        }

        .logic-row {
            display: grid;
            grid-template-columns: 1fr 1fr 1.28fr 1fr;
            gap: 1px;
            overflow: hidden;
            background: var(--line);
            border: 1px solid var(--line);
            border-radius: 7px;
        }

        .logic-cell {
            min-height: 92px;
            background: var(--surface);
            padding: 0.8rem 0.9rem;
        }

        .logic-label {
            color: var(--brand);
            font-size: 0.68rem;
            font-weight: 750;
            margin-bottom: 0.3rem;
        }

        .logic-value {
            color: #2a3532;
            font-size: 0.84rem;
            line-height: 1.55;
        }

        .scope-grid,
        .provider-grid,
        .quality-grid,
        .persona-grid,
        .finding-grid,
        .risk-grid {
            display: grid;
            gap: 0.7rem;
        }

        .scope-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .provider-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0.7rem; }
        .quality-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); }
        .persona-grid, .finding-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .risk-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }

        .info-card,
        .quality-card,
        .persona-card,
        .finding-card,
        .risk-card {
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 7px;
            padding: 1rem;
            box-shadow: 0 4px 14px rgba(26, 47, 41, 0.03);
        }

        .info-card.included { border-top: 3px solid var(--brand); }
        .info-card.excluded { border-top: 3px solid var(--amber); }

        .card-kicker {
            color: var(--brand);
            font-size: 0.69rem;
            font-weight: 750;
            margin-bottom: 0.35rem;
        }

        .card-title {
            color: var(--ink);
            font-size: 0.96rem;
            font-weight: 720;
            line-height: 1.45;
            margin-bottom: 0.38rem;
        }

        .card-copy {
            color: var(--muted);
            font-size: 0.82rem;
            line-height: 1.65;
        }

        .insight-band {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr);
            gap: 0.8rem;
            align-items: start;
            background: var(--brand-soft);
            border-left: 4px solid var(--brand);
            border-radius: 6px;
            padding: 0.9rem 1rem;
            margin: 0.75rem 0 1rem;
        }

        .insight-label {
            color: var(--brand);
            font-size: 0.72rem;
            font-weight: 760;
            white-space: nowrap;
        }

        .insight-copy {
            color: #2c443d;
            font-size: 0.85rem;
            line-height: 1.65;
        }

        .flow-strip {
            display: grid;
            grid-template-columns: repeat(7, minmax(105px, 1fr));
            gap: 0.45rem;
            overflow-x: auto;
            padding-bottom: 0.25rem;
        }

        .flow-step {
            position: relative;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 7px;
            padding: 0.75rem;
            min-height: 86px;
        }

        .flow-no {
            color: var(--amber);
            font-size: 0.68rem;
            font-weight: 760;
            margin-bottom: 0.35rem;
        }

        .flow-name {
            color: var(--ink);
            font-size: 0.82rem;
            font-weight: 700;
            line-height: 1.4;
        }

        .status-chip,
        .keyword-chip,
        .priority-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.26rem 0.58rem;
            font-size: 0.7rem;
            font-weight: 720;
        }

        .status-pending { color: #5f6b67; background: #edf1ef; }
        .status-adopted { color: var(--brand); background: var(--brand-soft); }
        .status-rejected { color: var(--coral); background: var(--coral-soft); }
        .keyword-chip { color: #3f5f56; background: #edf4f1; border-radius: 4px; }
        .priority-p0 { color: #ffffff; background: var(--coral); }
        .priority-p1 { color: #73470f; background: var(--amber-soft); }
        .priority-p2 { color: var(--brand); background: var(--brand-soft); }

        .suggestion-head {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.55rem;
        }

        .suggestion-index {
            color: var(--brand);
            font-size: 0.68rem;
            font-weight: 760;
            margin-bottom: 0.12rem;
        }

        .suggestion-title {
            color: var(--ink);
            font-size: 1.02rem;
            font-weight: 730;
        }

        .compare-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.65rem;
            margin: 0.75rem 0;
        }

        .compare-box {
            border: 1px solid var(--line);
            border-radius: 6px;
            padding: 0.85rem;
            min-height: 112px;
        }

        .compare-box.before { background: #fafbfa; }
        .compare-box.after { background: #eef7f4; border-color: #cce2da; }

        .compare-label {
            color: var(--muted);
            font-size: 0.68rem;
            font-weight: 750;
            margin-bottom: 0.35rem;
        }

        .compare-copy {
            color: #2c3734;
            font-size: 0.84rem;
            line-height: 1.65;
        }

        .empty-state {
            display: grid;
            place-items: center;
            min-height: 230px;
            background: #fbfcfb;
            border: 1px dashed #cbd7d2;
            border-radius: 8px;
            text-align: center;
            padding: 1.5rem;
        }

        .empty-mark {
            display: grid;
            place-items: center;
            width: 2.7rem;
            height: 2.7rem;
            margin: 0 auto 0.7rem;
            border-radius: 50%;
            color: var(--brand);
            background: var(--brand-soft);
            font-size: 0.76rem;
            font-weight: 780;
        }

        .strategy-card {
            min-height: 260px;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 8px;
            padding: 1.15rem;
            box-shadow: 0 5px 18px rgba(26, 47, 41, 0.04);
        }

        .strategy-card.recommended {
            border-top: 4px solid var(--brand);
        }

        .strategy-list {
            display: grid;
            gap: 0.55rem;
            margin-top: 0.85rem;
        }

        .strategy-item {
            color: #41504c;
            font-size: 0.82rem;
            line-height: 1.55;
        }

        .strategy-item strong { color: var(--ink); }

        .finding-card { border-top: 3px solid var(--brand); }
        .persona-card { border-top: 3px solid var(--amber); }

        .finding-step {
            color: var(--brand);
            font-size: 0.68rem;
            font-weight: 750;
            margin-top: 0.65rem;
        }

        .chart-note {
            background: var(--surface);
            border-left: 3px solid var(--amber);
            border-radius: 5px;
            color: #4d5955;
            font-size: 0.8rem;
            line-height: 1.65;
            padding: 0.72rem 0.85rem;
            margin: -0.35rem 0 1rem;
        }

        .roadmap-list {
            display: grid;
            gap: 0.65rem;
        }

        .roadmap-item {
            display: grid;
            grid-template-columns: 72px 1fr 1.25fr 1.25fr;
            gap: 0.8rem;
            align-items: start;
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 7px;
            padding: 0.9rem 1rem;
        }

        .roadmap-label {
            color: var(--muted);
            font-size: 0.66rem;
            font-weight: 730;
            margin-bottom: 0.2rem;
        }

        .roadmap-value {
            color: #34413d;
            font-size: 0.8rem;
            line-height: 1.55;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line);
            border-radius: 7px;
            overflow: hidden;
        }

        .stButton > button,
        .stDownloadButton > button {
            min-height: 2.65rem;
            border-radius: 6px;
            font-weight: 680;
        }

        .stButton > button[kind="primary"] {
            background: var(--brand);
            border-color: var(--brand);
        }

        .stButton > button[kind="primary"]:hover {
            background: #10574a;
            border-color: #10574a;
        }

        textarea, input {
            border-radius: 6px !important;
        }

        [data-testid="stFileUploaderDropzone"] {
            background: #fafcfb;
            border-color: #cdd8d4;
            border-radius: 7px;
        }

        @media (max-width: 900px) {
            .logic-row { grid-template-columns: 1fr 1fr; }
            .quality-grid, .persona-grid, .finding-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .roadmap-item { grid-template-columns: 64px 1fr; }
        }

        @media (max-width: 640px) {
            [data-testid="stMainBlockContainer"] { padding-top: 1rem; }
            .case-hero { padding: 1.45rem 1.25rem; }
            .case-hero::after { display: none; }
            .case-title { font-size: 1.75rem; }
            .page-intro { grid-template-columns: 1fr; gap: 0.55rem; }
            .logic-row,
            .scope-grid,
            .provider-grid,
            .quality-grid,
            .persona-grid,
            .finding-grid,
            .risk-grid,
            .compare-grid { grid-template-columns: 1fr; }
            .roadmap-item { grid-template-columns: 1fr; }
            .insight-band { grid-template-columns: 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    column.markdown(f'<div class="metric-help">{escape(help_text)}</div>', unsafe_allow_html=True)


def render_page_intro(number: str, kicker: str, title: str, conclusion: str) -> None:
    st.markdown(
        f"""
        <div class="page-intro">
            <div class="page-number">{escape(number)}</div>
            <div>
                <div class="page-kicker">{escape(kicker)}</div>
                <h2 class="page-title">{escape(title)}</h2>
                <div class="page-conclusion">{escape(conclusion)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_heading(title: str) -> None:
    st.markdown(f'<div class="section-heading">{escape(title)}</div>', unsafe_allow_html=True)


def render_insight(label: str, copy: str) -> None:
    st.markdown(
        f"""
        <div class="insight-band">
            <div class="insight-label">{escape(label)}</div>
            <div class="insight-copy">{escape(copy)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def style_chart(fig, *, height: int = 390) -> None:
    fig.update_layout(
        colorway=CHART_COLORS,
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#FFFFFF",
        font={"family": "Arial, Microsoft YaHei, sans-serif", "color": "#42504C", "size": 12},
        title={"font": {"size": 16, "color": "#18211F"}, "x": 0.02, "xanchor": "left"},
        margin={"l": 34, "r": 18, "t": 62, "b": 44},
        hoverlabel={"bgcolor": "#FFFFFF", "font_color": "#18211F"},
        showlegend=False,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="#DDE5E1", tickfont={"color": "#64706C"})
    fig.update_yaxes(gridcolor="#E8EEEB", zeroline=False, linecolor="#DDE5E1", tickfont={"color": "#64706C"})


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
    st.markdown(
        """
        <section class="case-hero">
            <div class="case-kicker">AI PRODUCT CASE STUDY · MVP 01</div>
            <h1 class="case-title">AI 简历优化助手<br>MVP 设计与效果评估</h1>
            <p class="case-copy">
                围绕“用户不知道如何根据目标岗位修改简历”的问题，设计从 JD 解析、差距识别、
                结构化建议到采纳反馈与效果评估的完整产品闭环。
            </p>
            <div class="case-tags">
                <span class="case-tag">规则引擎</span>
                <span class="case-tag">演示样本数据</span>
                <span class="case-tag">可交互 MVP</span>
                <span class="case-tag">AI 输出质量评估</span>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_overview(tables: Dict[str, pd.DataFrame]) -> None:
    users = tables["users"]
    tasks = tables["resume_tasks"]
    events = tables["events"]
    suggestions = tables["suggestions"]
    north_star = north_star_metrics(tasks, events, suggestions)

    render_page_intro(
        "01",
        "PROJECT OVERVIEW",
        "项目总览：从问题定义到评估闭环",
        "本页结论：AI 功能不是单独存在的能力点，而应由用户问题出发，并落到可观测、可迭代的产品指标。",
    )
    cols = st.columns(4)
    render_metric_card(cols[0], "目标用户", "求职用户", "重点关注应届生、实习生、转行用户。")
    render_metric_card(cols[1], "核心任务路径", "5 步", "上传简历、解析 JD、生成建议、采纳反馈、导出优化报告。")
    render_metric_card(cols[2], "示例优化任务", f"{len(tasks):,}", "演示样本数据中的优化任务数量。")
    render_metric_card(cols[3], "有效优化完成率", f"{north_star['effective_completion_rate']:.1%}", "导出优化报告且至少采纳 1 条建议的任务占比。")

    render_section_heading("用户问题 → 产品功能 → AI 能力 → 评估指标")
    rows = [
        ("不知道如何根据 JD 修改简历", "JD 解析与关键词分类", "识别岗位能力要求与简历覆盖情况", "关键词覆盖率、匹配分提升"),
        ("AI 建议偏泛，不知道怎么改", "结构化建议卡片", "输出问题、原文、改写、理由与关键词", "建议采纳率、具体性、可执行性"),
        ("不信任建议是否贴合岗位", "JD 关键词绑定解释", "把建议与岗位关键词显式关联", "JD 匹配度、可信度/可解释性"),
        ("采纳后不知道下一步做什么", "导出优化报告与下一步引导", "沉淀可执行的优化清单", "优化报告导出率、有效完成率"),
    ]
    row_html = []
    labels = ["用户痛点", "产品功能", "AI 能力", "评估指标"]
    for row in rows:
        cells = "".join(
            f'<div class="logic-cell"><div class="logic-label">{label}</div><div class="logic-value">{escape(value)}</div></div>'
            for label, value in zip(labels, row)
        )
        row_html.append(f'<div class="logic-row">{cells}</div>')
    st.markdown(f'<div class="logic-grid">{"".join(row_html)}</div>', unsafe_allow_html=True)

    render_section_heading("MVP 范围与边界")
    st.markdown(
        """
        <div class="scope-grid">
            <div class="info-card included">
                <div class="card-kicker">IN SCOPE</div>
                <div class="card-title">当前版本已实现</div>
                <div class="card-copy">简历与 JD 输入、规则引擎生成建议、采纳/拒绝/暂不处理反馈、优化报告导出和产品效果评估。</div>
            </div>
            <div class="info-card excluded">
                <div class="card-kicker">OUT OF SCOPE</div>
                <div class="card-title">当前版本暂不实现</div>
                <div class="card-copy">真实大模型接口、登录与权限、真实投递追踪、面试反馈和商业化能力。</div>
            </div>
            <div class="info-card">
                <div class="card-kicker">DATA NOTE</div>
                <div class="card-title">数据用于验证分析框架</div>
                <div class="card-copy">页面行为数据均为演示样本数据，用于验证用户路径、指标体系和产品效果评估思路。</div>
            </div>
            <div class="info-card">
                <div class="card-kicker">NEXT STEP</div>
                <div class="card-title">后续扩展方向</div>
                <div class="card-copy">接入真实大模型接口、岗位模板、用户反馈标注、生成策略版本管理与效果追踪。</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_product_experience() -> None:
    render_page_intro(
        "02",
        "PRODUCT EXPERIENCE",
        "产品体验：完成一次可解释的简历优化",
        "本页结论：用户需要的不只是生成结果，还包括建议依据、前后对比、处理反馈和清晰的下一步行动。",
    )
    left, right = st.columns([1.08, 0.92], gap="large")

    with left:
        with st.container(border=True):
            st.markdown("#### 准备分析材料")
            st.caption("示例内容均为虚构信息，也可以替换为已脱敏的简历与目标岗位描述。")
            if st.button("加载 AI 产品岗位示例", use_container_width=True):
                load_ai_pm_sample()
                st.success("已加载 AI 产品岗位示例，可直接生成优化建议。")
            profile_col, strategy_col = st.columns(2)
            profile_col.selectbox("用户类型", ["应届生", "实习生", "转行用户"], key="pm_user_type")
            strategy_col.radio(
                "生成策略",
                ["A", "B"],
                key="pm_prompt_group",
                horizontal=True,
                format_func=strategy_label,
                help="通用建议型适合基础优化，JD 匹配型更强调岗位关键词和修改理由。",
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
        with st.container(border=True):
            counts = suggestion_counts()
            scores = current_scores()
            st.markdown("#### 当前任务概览")
            st.caption("建议处理状态会实时反映在匹配分和报告导出条件中。")
            cols = st.columns(2)
            cols[0].metric("当前匹配分", scores["current"], delta=f"较原始 +{scores['current'] - scores['original']}")
            cols[1].metric("预计提升空间", f"+{scores['potential']}")
            st.progress(counts["processed"] / counts["total"] if counts["total"] else 0)
            st.caption(
                f"已处理 {counts['processed']} / {counts['total']} 条 · "
                f"采纳 {counts['adopted']} · 拒绝 {counts['rejected']} · 待处理 {counts['pending']}"
            )

            st.markdown("##### 当前 JD 关键词")
            keywords = extract_jd_keywords(st.session_state.pm_jd_text)
            chips = "".join(f'<span class="keyword-chip">{escape(keyword)}</span>' for keyword in keywords)
            st.markdown(f'<div class="keyword-row">{chips}</div>', unsafe_allow_html=True)

            report, report_name = report_payload()
            if counts["adopted"] < 1:
                st.info("至少采纳 1 条建议后，可导出优化报告。")
            if st.download_button(
                "导出优化报告",
                report,
                file_name=report_name,
                mime="text/markdown",
                use_container_width=True,
                disabled=counts["adopted"] < 1,
            ):
                OUTPUT_DIR.mkdir(exist_ok=True)
                (OUTPUT_DIR / report_name).write_text(report, encoding="utf-8")
                log_event("export_report")

    render_suggestion_cards()


def render_suggestion_cards() -> None:
    render_section_heading("结构化建议与处理反馈")
    if not st.session_state.pm_suggestions:
        st.markdown(
            """
            <div class="empty-state">
                <div>
                    <div class="empty-mark">AI</div>
                    <div class="card-title">优化建议将在这里生成</div>
                    <div class="card-copy">点击“生成优化建议”后，逐条查看问题定位、JD 关键词、前后对比和修改理由。</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    status_label = {"pending": "待处理", "adopted": "已采纳", "rejected": "已拒绝"}
    status_class = {"pending": "status-pending", "adopted": "status-adopted", "rejected": "status-rejected"}
    for index, item in enumerate(st.session_state.pm_suggestions):
        status = item.get("status", "pending")
        keywords = item.get("matched_jd_keywords", [])
        keyword_html = "".join(
            f'<span class="keyword-chip">{escape(str(keyword))}</span>' for keyword in keywords
        )
        with st.container(border=True):
            st.markdown(
                f"""
                <div class="suggestion-head">
                    <div>
                        <div class="suggestion-index">SUGGESTION {index + 1:02d}</div>
                        <div class="suggestion-title">{escape(str(item.get('resume_section', item['suggestion_type'])))}</div>
                    </div>
                    <span class="status-chip {status_class[status]}">{status_label[status]}</span>
                </div>
                <div class="keyword-row">{keyword_html}</div>
                <div class="section-heading">问题定位</div>
                <div class="card-copy">{escape(str(item['current_problem']))}</div>
                <div class="compare-grid">
                    <div class="compare-box before">
                        <div class="compare-label">原文片段</div>
                        <div class="compare-copy">{escape(str(item.get('original_expression', '')))}</div>
                    </div>
                    <div class="compare-box after">
                        <div class="compare-label">优化后表达</div>
                        <div class="compare-copy">{escape(str(item.get('revised_expression', item.get('revised_example', ''))))}</div>
                    </div>
                </div>
                <div class="card-kicker">为什么这样修改</div>
                <div class="card-copy">{escape(str(item.get('modification_reason', '')))}</div>
                """,
                unsafe_allow_html=True,
            )

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

            with st.expander("查看 AI 输出质量评分"):
                score_cols = st.columns(4)
                score_cols[0].metric("具体性", item["specificity_score"])
                score_cols[1].metric("JD 匹配度", item["jd_match_score"])
                score_cols[2].metric("可执行性", item["actionability_score"])
                score_cols[3].metric("可信度/可解释性", item["jd_match_score"])


def render_ai_capability_design() -> None:
    render_page_intro(
        "03",
        "AI CAPABILITY DESIGN",
        "AI 能力设计：把生成过程拆成可解释链路",
        "本页结论：AI 能力需要同时考虑输入理解、输出结构、质量评估和安全边界，而不是只关注能否生成文本。",
    )
    render_section_heading("建议生成流程")
    flow_steps = ["JD 输入", "关键词识别", "覆盖判断", "缺口分析", "建议生成", "质量评分", "用户反馈"]
    flow_html = "".join(
        f'<div class="flow-step"><div class="flow-no">STEP {index:02d}</div><div class="flow-name">{escape(step)}</div></div>'
        for index, step in enumerate(flow_steps, start=1)
    )
    st.markdown(f'<div class="flow-strip">{flow_html}</div>', unsafe_allow_html=True)
    render_insight(
        "当前实现",
        "使用规则引擎保证演示稳定和输出可控；后续接入真实大模型接口时，继续保留结构约束、事实边界和质量评估。",
    )

    keywords = extract_jd_keywords(st.session_state.pm_jd_text)
    categories = categorize_keywords(keywords)
    render_section_heading("JD 能力结构化识别")
    category_cards = []
    for category, values in categories.items():
        chips = "".join(f'<span class="keyword-chip">{escape(str(value))}</span>' for value in values)
        category_cards.append(
            f'<div class="info-card"><div class="card-kicker">ABILITY GROUP</div>'
            f'<div class="card-title">{escape(str(category))}</div><div class="keyword-row">{chips}</div></div>'
        )
    st.markdown(f'<div class="scope-grid">{"".join(category_cards)}</div>', unsafe_allow_html=True)

    render_section_heading("简历缺口分析")
    st.dataframe(pd.DataFrame(analyze_resume_gaps(st.session_state.pm_resume_text, st.session_state.pm_jd_text)), use_container_width=True, hide_index=True)

    render_section_heading("AI 输出质量评估体系")
    quality_rows = [
        ("具体性", "能否定位到具体模块、能力点或项目表达", "明确关键词、模块和问题定位"),
        ("JD 匹配度", "是否真正对应目标岗位要求", "绑定 JD 关键词并解释岗位关系"),
        ("可执行性", "用户能否直接照着建议修改", "提供原文、改写和修改理由"),
        ("可信度/可解释性", "是否说明为什么这样修改", "展示依据并限制虚构经历"),
    ]
    quality_html = "".join(
        f'<div class="quality-card"><div class="card-kicker">QUALITY DIMENSION</div>'
        f'<div class="card-title">{escape(name)}</div><div class="card-copy">{escape(meaning)}</div>'
        f'<div class="finding-step">当前实现</div><div class="card-copy">{escape(current)}</div></div>'
        for name, meaning, current in quality_rows
    )
    st.markdown(f'<div class="quality-grid">{quality_html}</div>', unsafe_allow_html=True)

    render_section_heading("生成能力扩展设计")
    provider_rows = [
        ("生成引擎", "规则引擎保证稳定和可控", "接入真实大模型接口，提升灵活性与表达质量"),
        ("策略管理", "内置通用建议型与 JD 匹配型", "支持模板管理、版本对比与效果追踪"),
        ("输出安全", "固定规则避免虚构经历", "增加隐私脱敏、事实校验与安全提示"),
    ]
    provider_html = "".join(
        f'<div class="info-card"><div class="card-kicker">{escape(layer)}</div>'
        f'<div class="card-title">当前实现</div><div class="card-copy">{escape(current)}</div>'
        f'<div class="finding-step">后续扩展</div><div class="card-copy">{escape(future)}</div></div>'
        for layer, current, future in provider_rows
    )
    st.markdown(f'<div class="provider-grid">{provider_html}</div>', unsafe_allow_html=True)


def render_prompt_strategy(tables: Dict[str, pd.DataFrame]) -> None:
    render_page_intro(
        "04",
        "GENERATION STRATEGY",
        "生成策略：把 Prompt 选择转化为产品决策",
        "本页结论：生成策略可以通过建议采纳率、质量评分和导出转化进行评估，而不是停留在主观判断。",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            """
            <div class="strategy-card">
                <div class="card-kicker">STRATEGY A</div>
                <div class="card-title">通用建议型</div>
                <div class="strategy-list">
                    <div class="strategy-item"><strong>策略目标：</strong>指出简历问题并给出通用修改建议。</div>
                    <div class="strategy-item"><strong>预期优势：</strong>覆盖广、实现简单，适合冷启动。</div>
                    <div class="strategy-item"><strong>潜在问题：</strong>建议可能偏泛，与目标 JD 绑定不强。</div>
                    <div class="strategy-item"><strong>适用场景：</strong>没有明确岗位方向，或只需要基础优化。</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            """
            <div class="strategy-card recommended">
                <div class="card-kicker">STRATEGY B · RECOMMENDED</div>
                <div class="card-title">JD 匹配型</div>
                <div class="strategy-list">
                    <div class="strategy-item"><strong>策略目标：</strong>结合目标 JD 输出问题定位、修改建议和示例改写。</div>
                    <div class="strategy-item"><strong>预期优势：</strong>更贴合岗位要求，用户更容易理解和采纳。</div>
                    <div class="strategy-item"><strong>潜在问题：</strong>对 JD 解析质量更敏感。</div>
                    <div class="strategy-item"><strong>适用场景：</strong>用户已有明确目标岗位，希望提升岗位匹配度。</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
    fig_ab.update_traces(
        marker_color=["#D28A32", "#176B5B"],
        hovertemplate="生成策略=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>",
    )
    style_chart(fig_ab, height=370)
    st.plotly_chart(fig_ab, use_container_width=True, config=PLOT_CONFIG)
    render_insight(
        "产品决策",
        "演示样本数据显示，JD 匹配型策略的建议采纳率更高。后续默认采用该策略，并固定展示绑定关键词、原文片段、优化后表达和修改理由。",
    )


def render_core_findings() -> None:
    render_section_heading("核心发现与产品动作")
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
    cards = "".join(
        f'<div class="finding-card">'
        f'<div class="card-kicker">DATA FINDING {index:02d}</div>'
        f'<div class="card-title">{escape(row["标题"])}</div>'
        f'<div class="finding-step">产品解释</div>'
        f'<div class="card-copy">{escape(row["说明"])}</div>'
        f'<div class="finding-step">迭代动作</div>'
        f'<div class="card-copy">{escape(row["动作"])}</div>'
        f'</div>'
        for index, row in enumerate(rows, start=1)
    )
    st.markdown(f'<div class="finding-grid">{cards}</div>', unsafe_allow_html=True)


def render_segment_personas() -> None:
    render_section_heading("用户分群诊断与适配策略")
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
    cards = "".join(
        f'<div class="persona-card">'
        f'<div class="card-kicker">USER SEGMENT {index:02d}</div>'
        f'<div class="card-title">{escape(persona["title"])}</div>'
        f'<div class="finding-step">用户特点</div>'
        f'<div class="card-copy">{escape(persona["特点"])}</div>'
        f'<div class="finding-step">主要问题</div>'
        f'<div class="card-copy">{escape(persona["主要问题"])}</div>'
        f'<div class="finding-step">产品策略</div>'
        f'<div class="card-copy">{escape(persona["产品策略"])}</div>'
        f'<div class="finding-step">推荐功能</div>'
        f'<div class="card-copy">{escape(persona["推荐功能"])}</div>'
        f'</div>'
        for index, persona in enumerate(personas, start=1)
    )
    st.markdown(f'<div class="persona-grid">{cards}</div>', unsafe_allow_html=True)


def render_directional_observations(tables: Dict[str, pd.DataFrame]) -> None:
    tasks = tables["resume_tasks"].copy()
    if "current_match_score" not in tasks.columns:
        tasks["current_match_score"] = tasks.get("optimized_match_score", tasks["original_match_score"])
    tasks["match_score_lift"] = tasks["current_match_score"] - tasks["original_match_score"]
    observations = [
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
    rows = "".join(
        f'<div class="roadmap-item">'
        f'<div><div class="roadmap-label">影响因素</div><div class="roadmap-value"><strong>{escape(row["影响因素"])}</strong></div></div>'
        f'<div><div class="roadmap-label">方向性观察</div><div class="roadmap-value">{escape(row["方向性观察"])}</div></div>'
        f'<div><div class="roadmap-label">产品含义</div><div class="roadmap-value">{escape(row["产品含义"])}</div></div>'
        f'<div><div class="roadmap-label">后续动作</div><div class="roadmap-value">{escape(row["后续动作"])}</div></div>'
        f'</div>'
        for row in observations
    )
    st.markdown(f'<div class="roadmap-list">{rows}</div>', unsafe_allow_html=True)


def render_product_evaluation(tables: Dict[str, pd.DataFrame]) -> None:
    render_page_intro(
        "05",
        "PRODUCT EVALUATION",
        "产品效果评估：从生成结果走向任务完成",
        "本页结论：用户不是只需要生成建议，更需要可解释的修改理由、明确的下一步引导和可感知的任务完成感。",
    )
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

    render_section_heading("核心任务路径漏斗")
    funnel = build_funnel_chart_data(calculate_funnel(events))
    fig_funnel = px.funnel(
        funnel,
        x="用户数",
        y="用户路径",
        title="核心任务路径漏斗",
        labels={"用户数": "用户数", "用户路径": "用户路径"},
    )
    fig_funnel.update_traces(
        marker={"color": ["#176B5B", "#2E7B6D", "#4C8B80", "#73A095", "#D28A32", "#C65D4B"]},
        hovertemplate="用户路径=%{y}<br>用户数=%{x}<extra></extra>",
    )
    style_chart(fig_funnel, height=410)
    st.plotly_chart(fig_funnel, use_container_width=True, config=PLOT_CONFIG)
    st.markdown(
        '<div class="chart-note"><strong>业务解读：</strong>演示样本数据中，主要流失发生在采纳建议之后。'
        '用户对建议有兴趣，但导出动作尚未形成明确的完成感。<strong>可落地动作：</strong>采纳 1 条建议后前置展示导出入口，并说明报告价值。</div>',
        unsafe_allow_html=True,
    )

    drivers = adoption_driver_tables(users, suggestions)
    render_section_heading("建议采纳驱动因素")
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
    fig_quality.update_traces(
        marker_color=["#C65D4B", "#D28A32", "#176B5B"],
        hovertemplate="建议质量=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>",
    )
    style_chart(fig_quality, height=350)
    cols[0].plotly_chart(fig_quality, use_container_width=True, config=PLOT_CONFIG)
    low_quality_note = "低质量建议样本量不足，当前主要比较中质量与高质量建议的采纳差异。" if (quality_chart["suggestions"] == 0).any() else ""
    cols[0].markdown(
        f'<div class="chart-note"><strong>业务解读：</strong>建议越具体、越可执行，用户越容易采纳。{escape(low_quality_note)} '
        '<strong>动作：</strong>固定输出原文、改写、理由与关键词。</div>',
        unsafe_allow_html=True,
    )
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
    fig_prompt.update_traces(
        marker_color=["#D28A32", "#176B5B"],
        hovertemplate="生成策略=%{x}<br>建议采纳率=%{y:.1%}<extra></extra>",
    )
    style_chart(fig_prompt, height=350)
    cols[1].plotly_chart(fig_prompt, use_container_width=True, config=PLOT_CONFIG)
    cols[1].markdown(
        '<div class="chart-note"><strong>业务解读：</strong>JD 匹配型策略更容易让用户理解建议价值。'
        '<strong>动作：</strong>默认采用 JD 匹配型策略，并展示关键词绑定解释。</div>',
        unsafe_allow_html=True,
    )

    render_section_heading("导出优化报告转化的方向性观察")
    render_directional_observations(tables)
    render_segment_personas()


def render_iteration_roadmap() -> None:
    render_page_intro(
        "06",
        "ITERATION ROADMAP",
        "迭代路线图：从核心体验到模型能力",
        "本页结论：每个产品优化方向都需要对应优先级依据和验收指标，避免迭代停留在功能堆叠。",
    )
    roadmap = [
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
    roadmap_html = "".join(
        f'<div class="roadmap-item">'
        f'<div><span class="priority-chip priority-{row["阶段"].lower()}">{escape(row["阶段"])}</span></div>'
        f'<div><div class="roadmap-label">优化方向</div><div class="roadmap-value"><strong>{escape(row["优化方向"])}</strong></div></div>'
        f'<div><div class="roadmap-label">功能方案 / 优先级依据</div><div class="roadmap-value">{escape(row["功能方案"])}<br>{escape(row["优先级依据"])}</div></div>'
        f'<div><div class="roadmap-label">验收指标</div><div class="roadmap-value">{escape(row["验收指标"])}</div></div>'
        f'</div>'
        for row in roadmap
    )
    st.markdown(f'<div class="roadmap-list">{roadmap_html}</div>', unsafe_allow_html=True)

    render_section_heading("风险与产品边界")
    risks = [
        ("建议不准确", "规则或模型可能给出不符合用户经历的建议", "增加用户反馈、人工标注和安全提示"),
        ("过度包装简历", "生成建议可能让表达超过真实经历", "强调基于真实经历改写，不生成虚假经历"),
        ("隐私问题", "真实简历可能包含个人信息", "当前不持久化输入；真实接入时增加脱敏与权限控制"),
        ("样本代表性不足", "当前结论基于演示样本数据", "接入真实行为数据后重新验证分析结论"),
    ]
    risk_html = "".join(
        f'<div class="risk-card">'
        f'<div class="card-kicker">RISK {index:02d}</div>'
        f'<div class="card-title">{escape(title)}</div>'
        f'<div class="card-copy">{escape(description)}</div>'
        f'<div class="finding-step">控制思路</div>'
        f'<div class="card-copy">{escape(control)}</div>'
        f'</div>'
        for index, (title, description, control) in enumerate(risks, start=1)
    )
    st.markdown(f'<div class="risk-grid">{risk_html}</div>', unsafe_allow_html=True)


def main() -> None:
    inject_portfolio_styles()
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
