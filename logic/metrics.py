from __future__ import annotations

import math
from typing import Dict, List

import pandas as pd


FUNNEL_STEPS = [
    ("visit_product", "访问产品"),
    ("upload_resume", "上传简历"),
    ("upload_jd", "上传 JD"),
    ("generate_suggestion", "生成建议"),
    ("adopt_suggestion", "采纳建议"),
    ("export_report", "导出报告"),
]


def calculate_funnel(events: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    previous_users = None
    for event_name, label in FUNNEL_STEPS:
        if events.empty:
            user_count = 0
        else:
            user_count = events.loc[events["event_name"] == event_name, "user_id"].nunique()
        conversion_rate = 1.0 if previous_users is None or previous_users == 0 else user_count / previous_users
        dropoff_rate = 0.0 if previous_users is None or previous_users == 0 else 1 - conversion_rate
        rows.append(
            {
                "event_name": event_name,
                "step": label,
                "users": int(user_count),
                "conversion_rate": conversion_rate,
                "dropoff_rate": dropoff_rate,
            }
        )
        previous_users = user_count
    return pd.DataFrame(rows)


def suggestion_summary(suggestions: pd.DataFrame) -> Dict[str, float]:
    if suggestions.empty:
        return {
            "exposed": 0,
            "adopted": 0,
            "adoption_rate": 0.0,
            "avg_adopted_per_user": 0.0,
        }
    exposed = len(suggestions)
    adopted = int(suggestions["adopted"].fillna(False).sum())
    user_count = max(suggestions["user_id"].nunique(), 1)
    return {
        "exposed": exposed,
        "adopted": adopted,
        "adoption_rate": adopted / exposed if exposed else 0.0,
        "avg_adopted_per_user": adopted / user_count,
    }


def north_star_metrics(tasks: pd.DataFrame, events: pd.DataFrame, suggestions: pd.DataFrame) -> Dict[str, float]:
    generated_tasks = len(tasks)
    effective_tasks = int(((tasks["exported"].fillna(False).astype(bool)) & (tasks["adopted_count"] >= 1)).sum()) if generated_tasks else 0
    visit_users = events.loc[events["event_name"] == "visit_product", "user_id"].nunique() if not events.empty else 0
    generated_users = events.loc[events["event_name"] == "generate_suggestion", "user_id"].nunique() if not events.empty else 0
    exported_tasks = int(tasks["exported"].fillna(False).astype(bool).sum()) if generated_tasks else 0
    adopted = int(suggestions["adopted"].fillna(False).sum()) if not suggestions.empty else 0
    return {
        "resume_task_count": generated_tasks,
        "suggestion_generation_rate": generated_users / visit_users if visit_users else 0.0,
        "suggestion_adoption_rate": adopted / len(suggestions) if len(suggestions) else 0.0,
        "report_export_rate": exported_tasks / generated_tasks if generated_tasks else 0.0,
        "effective_completion_rate": effective_tasks / generated_tasks if generated_tasks else 0.0,
        "effective_tasks": effective_tasks,
    }


def indicator_tree() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"层级": "北极星指标", "指标/维度": "有效优化任务完成率", "定义": "完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数"},
            {"层级": "一级指标", "指标/维度": "简历优化任务数", "定义": "生成建议的简历优化任务数量"},
            {"层级": "一级指标", "指标/维度": "建议生成率", "定义": "生成建议用户数 / 访问产品用户数"},
            {"层级": "一级指标", "指标/维度": "建议采纳率", "定义": "被采纳建议数 / 建议曝光数"},
            {"层级": "一级指标", "指标/维度": "报告导出率", "定义": "导出报告任务数 / 生成建议任务数"},
            {"层级": "一级指标", "指标/维度": "有效优化任务完成率", "定义": "有效任务数 / 生成建议任务数"},
            {"层级": "二级拆解", "指标/维度": "用户维度", "定义": "用户类型、目标岗位、经验年限"},
            {"层级": "二级拆解", "指标/维度": "JD 维度", "定义": "JD 关键词数量、JD 难度、岗位类型"},
            {"层级": "二级拆解", "指标/维度": "建议维度", "定义": "建议类型、质量评分、关键词匹配数"},
            {"层级": "二级拆解", "指标/维度": "Prompt 维度", "定义": "A 组 / B 组"},
            {"层级": "二级拆解", "指标/维度": "行为维度", "定义": "建议查看数、采纳数、拒绝数、导出行为"},
        ]
    )


def adoption_by_dimension(suggestions: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if suggestions.empty or dimension not in suggestions.columns:
        return pd.DataFrame(columns=[dimension, "suggestions", "adopted", "adoption_rate"])
    grouped = (
        suggestions.assign(adopted=suggestions["adopted"].fillna(False).astype(bool))
        .groupby(dimension, as_index=False)
        .agg(suggestions=("suggestion_id", "count"), adopted=("adopted", "sum"))
    )
    grouped["adoption_rate"] = grouped["adopted"] / grouped["suggestions"]
    return grouped.sort_values("adoption_rate", ascending=False)


def build_task_feature_table(users: pd.DataFrame, tasks: pd.DataFrame, suggestions: pd.DataFrame) -> pd.DataFrame:
    if tasks.empty:
        return pd.DataFrame()
    task_features = tasks.copy()
    if "current_match_score" not in task_features.columns:
        if "optimized_match_score" in task_features.columns:
            task_features["current_match_score"] = task_features["optimized_match_score"]
        else:
            task_features["current_match_score"] = task_features["original_match_score"]
    for column, default in [("rejected_count", 0), ("pending_count", 0), ("adopted_count", 0)]:
        if column not in task_features.columns:
            task_features[column] = default
    task_features["exported"] = task_features["exported"].fillna(False).astype(bool)
    task_features["match_score_lift"] = task_features["current_match_score"] - task_features["original_match_score"]
    if not suggestions.empty:
        suggestion_quality = suggestions.copy()
        suggestion_quality["quality_score"] = suggestion_quality[["specificity_score", "jd_match_score", "actionability_score"]].mean(axis=1)
        quality_by_task = suggestion_quality.groupby("task_id", as_index=False).agg(avg_quality_score=("quality_score", "mean"))
        task_features = task_features.merge(quality_by_task, on="task_id", how="left")
    else:
        task_features["avg_quality_score"] = 0.0
    task_features["avg_quality_score"] = task_features["avg_quality_score"].fillna(0.0)
    if not users.empty:
        task_features = task_features.merge(users[["user_id", "user_type", "target_role", "experience_years"]], on="user_id", how="left")
    return task_features


def export_rate_by_adopted_count(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["adopted_count_group", "tasks", "export_rate"])
    data = task_features.copy()
    data["adopted_count_group"] = data["adopted_count"].clip(upper=4).astype(str)
    data.loc[data["adopted_count"] >= 4, "adopted_count_group"] = "4+"
    grouped = data.groupby("adopted_count_group", as_index=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"]
    return grouped


def export_rate_by_lift(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["match_score_lift_group", "tasks", "export_rate"])
    data = task_features.copy()
    data["match_score_lift_group"] = pd.cut(
        data["match_score_lift"],
        bins=[-1, 0, 10, 20, 100],
        labels=["0", "1-10", "11-20", "20+"],
        include_lowest=True,
    )
    grouped = data.groupby("match_score_lift_group", as_index=False, observed=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"].replace(0, pd.NA)
    grouped["export_rate"] = pd.to_numeric(grouped["export_rate"], errors="coerce").fillna(0.0)
    return grouped


def export_rate_by_pending_count(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["pending_count_group", "tasks", "export_rate"])
    data = task_features.copy()
    data["pending_count_group"] = data["pending_count"].clip(upper=4).astype(str)
    data.loc[data["pending_count"] >= 4, "pending_count_group"] = "4+"
    grouped = data.groupby("pending_count_group", as_index=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"]
    return grouped


def export_factor_table(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["影响因素", "分析方法", "影响方向", "参考值", "业务解释"])
    data = task_features.copy()
    target = data["exported"].astype(int)
    rows = []
    numeric_factors = [
        ("adopted_count", "已采纳建议数", "采纳越多越可能形成完整优化成果"),
        ("rejected_count", "已拒绝建议数", "拒绝较多可能表示建议不匹配或信任不足"),
        ("pending_count", "待处理建议数", "待处理较多可能增加决策负担"),
        ("current_match_score", "当前 JD 匹配分", "匹配分越高越可能导出报告"),
        ("match_score_lift", "匹配分提升", "提升越明显越能感知优化价值"),
        ("avg_quality_score", "平均建议质量分", "建议越具体、匹配、可执行越可能促进导出"),
    ]
    for column, label, explanation in numeric_factors:
        corr = data[column].corr(target) if data[column].nunique() > 1 else 0.0
        corr = 0.0 if pd.isna(corr) else float(corr)
        direction = "正向" if corr > 0.03 else "负向" if corr < -0.03 else "弱相关"
        rows.append({"影响因素": label, "分析方法": "与是否导出的相关系数", "影响方向": direction, "参考值": round(corr, 3), "业务解释": explanation})

    for column, label in [("prompt_group", "Prompt 组别"), ("user_type", "用户类型")]:
        if column in data.columns:
            rates = data.groupby(column)["exported"].mean()
            spread = float(rates.max() - rates.min()) if len(rates) else 0.0
            best = str(rates.idxmax()) if len(rates) else "-"
            rows.append(
                {
                    "影响因素": label,
                    "分析方法": "分组导出率差异",
                    "影响方向": f"{best} 更高" if len(rates) else "样本不足",
                    "参考值": round(spread, 3),
                    "业务解释": "不同分组导出率差异用于定位需要专项优化的人群或 Prompt 策略。",
                }
            )
    return pd.DataFrame(rows)


def prompt_ab_metrics(tasks: pd.DataFrame, suggestions: pd.DataFrame) -> pd.DataFrame:
    if tasks.empty or suggestions.empty:
        return pd.DataFrame(
            columns=[
                "prompt_group",
                "suggestions",
                "adopted",
                "adoption_rate",
                "tasks",
                "exported_tasks",
                "export_rate",
                "avg_quality_score",
            ]
        )

    suggestion_stats = (
        suggestions.assign(
            adopted=suggestions["adopted"].fillna(False).astype(bool),
            quality_score=suggestions[["specificity_score", "jd_match_score", "actionability_score"]].mean(axis=1),
        )
        .groupby("prompt_group", as_index=False)
        .agg(
            suggestions=("suggestion_id", "count"),
            adopted=("adopted", "sum"),
            avg_quality_score=("quality_score", "mean"),
        )
    )
    task_stats = (
        tasks.assign(exported=tasks["exported"].fillna(False).astype(bool))
        .groupby("prompt_group", as_index=False)
        .agg(tasks=("task_id", "count"), exported_tasks=("exported", "sum"))
    )
    merged = suggestion_stats.merge(task_stats, on="prompt_group", how="outer").fillna(0)
    merged["adoption_rate"] = merged["adopted"] / merged["suggestions"].replace(0, pd.NA)
    merged["export_rate"] = merged["exported_tasks"] / merged["tasks"].replace(0, pd.NA)
    return merged.fillna(0).sort_values("prompt_group")


def chi_square_for_prompt_adoption(suggestions: pd.DataFrame) -> Dict[str, float]:
    if suggestions.empty or set(suggestions["prompt_group"].unique()) < {"A", "B"}:
        return {"chi_square": 0.0, "p_value": 1.0}

    table = []
    for group in ("A", "B"):
        group_df = suggestions[suggestions["prompt_group"] == group]
        adopted = int(group_df["adopted"].fillna(False).sum())
        rejected = int(len(group_df) - adopted)
        table.append([adopted, rejected])

    total = sum(sum(row) for row in table)
    row_totals = [sum(row) for row in table]
    col_totals = [sum(table[row][col] for row in range(2)) for col in range(2)]
    if total == 0 or 0 in row_totals or 0 in col_totals:
        return {"chi_square": 0.0, "p_value": 1.0}

    chi_square = 0.0
    for row in range(2):
        for col in range(2):
            expected = row_totals[row] * col_totals[col] / total
            chi_square += (table[row][col] - expected) ** 2 / expected

    p_value = math.erfc(math.sqrt(chi_square / 2))
    return {"chi_square": chi_square, "p_value": p_value}


def quality_adoption_relation(suggestions: pd.DataFrame) -> pd.DataFrame:
    if suggestions.empty:
        return pd.DataFrame(columns=["quality_bucket", "suggestions", "adopted", "adoption_rate"])
    scored = suggestions.copy()
    scored["adopted"] = scored["adopted"].fillna(False).astype(bool)
    scored["quality_score"] = scored[["specificity_score", "jd_match_score", "actionability_score"]].mean(axis=1)
    scored["quality_bucket"] = pd.cut(
        scored["quality_score"],
        bins=[0, 3, 4, 5],
        labels=["低质量(≤3)", "中质量(3-4)", "高质量(>4)"],
        include_lowest=True,
    )
    grouped = (
        scored.groupby("quality_bucket", observed=False)
        .agg(suggestions=("suggestion_id", "count"), adopted=("adopted", "sum"))
        .reset_index()
    )
    grouped["adoption_rate"] = grouped["adopted"] / grouped["suggestions"].replace(0, pd.NA)
    grouped["suggestions"] = grouped["suggestions"].fillna(0).astype(int)
    grouped["adopted"] = grouped["adopted"].fillna(0).astype(int)
    grouped["adoption_rate"] = pd.to_numeric(grouped["adoption_rate"], errors="coerce").fillna(0.0)
    return grouped


def adoption_driver_tables(users: pd.DataFrame, suggestions: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if suggestions.empty:
        empty = pd.DataFrame()
        return {"quality": empty, "type": empty, "prompt": empty, "impact": empty}
    data = suggestions.copy()
    data["adopted"] = data["adopted"].fillna(False).astype(bool)
    data["matched_keyword_count"] = data["matched_keyword"].fillna("").apply(lambda value: len([item for item in str(value).split(",") if item.strip()]))
    if not users.empty:
        data = data.merge(users[["user_id", "user_type"]], on="user_id", how="left")
    quality = quality_adoption_relation(data)
    type_rate = adoption_by_dimension(data, "suggestion_type")
    prompt_rate = adoption_by_dimension(data, "prompt_group")
    rows = []
    for column, label in [
        ("specificity_score", "具体性"),
        ("jd_match_score", "JD 匹配度"),
        ("actionability_score", "可执行性"),
        ("matched_keyword_count", "关键词匹配数"),
    ]:
        corr = data[column].astype(float).corr(data["adopted"].astype(int)) if data[column].nunique() > 1 else 0.0
        corr = 0.0 if pd.isna(corr) else float(corr)
        rows.append({"影响因素": label, "影响方向": "正向" if corr > 0.03 else "负向" if corr < -0.03 else "弱相关", "impact": round(corr, 3)})
    return {"quality": quality, "type": type_rate, "prompt": prompt_rate, "impact": pd.DataFrame(rows)}


def quality_dimension_impact(suggestions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in [
        ("specificity_score", "具体性"),
        ("jd_match_score", "JD 匹配度"),
        ("actionability_score", "可执行性"),
    ]:
        if suggestions.empty:
            corr = 0.0
        else:
            series = suggestions[column].astype(float)
            adopted = suggestions["adopted"].fillna(False).astype(int)
            corr = float(series.corr(adopted)) if series.nunique() > 1 else 0.0
            if math.isnan(corr):
                corr = 0.0
        rows.append({"dimension": label, "impact": corr})
    return pd.DataFrame(rows)


def user_segment_metrics(users: pd.DataFrame, tasks: pd.DataFrame, suggestions: pd.DataFrame) -> pd.DataFrame:
    if users.empty:
        return pd.DataFrame(columns=["user_type", "adoption_rate", "export_rate", "avg_tasks_per_user"])

    task_user = tasks.merge(users[["user_id", "user_type"]], on="user_id", how="left") if not tasks.empty else pd.DataFrame()
    suggestion_user = (
        suggestions.merge(users[["user_id", "user_type"]], on="user_id", how="left") if not suggestions.empty else pd.DataFrame()
    )

    if suggestion_user.empty:
        adoption = pd.DataFrame({"user_type": users["user_type"].unique(), "adoption_rate": 0.0})
    else:
        adoption = (
            suggestion_user.assign(adopted=suggestion_user["adopted"].fillna(False).astype(bool))
            .groupby("user_type", as_index=False)
            .agg(suggestions=("suggestion_id", "count"), adopted=("adopted", "sum"))
        )
        adoption["adoption_rate"] = adoption["adopted"] / adoption["suggestions"]

    if task_user.empty:
        task_stats = pd.DataFrame({"user_type": users["user_type"].unique(), "export_rate": 0.0, "avg_tasks_per_user": 0.0})
    else:
        task_stats = (
            task_user.assign(exported=task_user["exported"].fillna(False).astype(bool))
            .groupby("user_type", as_index=False)
            .agg(tasks=("task_id", "count"), users=("user_id", "nunique"), exported=("exported", "sum"))
        )
        task_stats["export_rate"] = task_stats["exported"] / task_stats["tasks"]
        task_stats["avg_tasks_per_user"] = task_stats["tasks"] / task_stats["users"]

    merged = adoption[["user_type", "adoption_rate"]].merge(
        task_stats[["user_type", "export_rate", "avg_tasks_per_user"]],
        on="user_type",
        how="outer",
    )
    return merged.fillna(0).sort_values("user_type")


def segment_strategy_table(segment_metrics: pd.DataFrame) -> pd.DataFrame:
    lookup = {row["user_type"]: row for _, row in segment_metrics.iterrows()}
    rows = []
    templates = {
        "实习生": {
            "可能原因": "目标岗位较明确，经历相对简单，简历内容更容易被结构化改写。",
            "产品策略": "强化 JD 匹配型建议和一键改写，帮助快速形成可投递版本。",
        },
        "应届生": {
            "可能原因": "项目经历不足或表达不够量化，对技能补强和项目模板依赖更高。",
            "产品策略": "提供项目经历模板、技能补强建议和量化表达示例。",
        },
        "转行用户": {
            "可能原因": "原经历与目标 JD 的能力映射难度更高，用户可能采纳建议但不确定能否形成完整报告。",
            "产品策略": "增加可迁移能力识别、岗位差距分析和转行经历改写模板。",
        },
    }
    for user_type in ["实习生", "应届生", "转行用户"]:
        metrics = lookup.get(user_type)
        if metrics is None:
            performance = "样本不足"
        else:
            performance = f"建议采纳率 {metrics['adoption_rate']:.1%}，报告导出率 {metrics['export_rate']:.1%}，人均任务数 {metrics['avg_tasks_per_user']:.2f}"
        rows.append(
            {
                "用户类型": user_type,
                "数据表现": performance,
                "可能原因": templates[user_type]["可能原因"],
                "产品策略": templates[user_type]["产品策略"],
            }
        )
    return pd.DataFrame(rows)


def optimization_priority_matrix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "优化方案": "导出按钮前置",
                "影响指标": "报告导出率、有效优化任务完成率",
                "预期收益": "高",
                "实现成本": "低",
                "优先级": "P0",
                "数据依据": "基于模拟产品日志，“采纳建议 -> 导出报告”是主要流失环节。",
            },
            {
                "优化方案": "用户采纳建议后增加下一步引导",
                "影响指标": "报告导出率",
                "预期收益": "高",
                "实现成本": "低",
                "优先级": "P0",
                "数据依据": "采纳行为已经发生，但用户未必知道下一步应该导出或继续处理建议。",
            },
            {
                "优化方案": "增加 JD 关键词绑定解释",
                "影响指标": "建议采纳率、平均建议质量感知",
                "预期收益": "中高",
                "实现成本": "中",
                "优先级": "P1",
                "数据依据": "基于模拟产品日志，B 组 JD 匹配型 Prompt 采纳率更高。",
            },
            {
                "优化方案": "针对转行用户增加可迁移能力识别",
                "影响指标": "转行用户导出率、有效完成率",
                "预期收益": "中高",
                "实现成本": "中高",
                "优先级": "P1",
                "数据依据": "分群分析显示转行用户路径更长、能力映射成本更高。",
            },
            {
                "优化方案": "增加有用 / 无用反馈按钮",
                "影响指标": "建议质量评分、后续采纳率",
                "预期收益": "中",
                "实现成本": "低",
                "优先级": "P1",
                "数据依据": "质量评分与采纳行为存在模拟相关性，需要收集更细反馈优化规则。",
            },
            {
                "优化方案": "后续接入真实 API",
                "影响指标": "建议质量、用户信任、采纳率",
                "预期收益": "中",
                "实现成本": "高",
                "优先级": "P2",
                "数据依据": "当前 mock 用于验证流程和分析框架，真实 API 可在框架稳定后接入验证。",
            },
        ]
    )
