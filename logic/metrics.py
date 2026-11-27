from __future__ import annotations

import math
from typing import Dict

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
    """Count tasks and unique users that reached each step in the required order."""
    step_index = {name: index for index, (name, _) in enumerate(FUNNEL_STEPS)}
    reached = [set() for _ in FUNNEL_STEPS]
    task_counts = [0 for _ in FUNNEL_STEPS]
    if not events.empty:
        keys = ["user_id"]
        # Legacy logs can contain just user and event names, in arrival order.
        if "task_id" in events:
            keys.append("task_id")
        elif "session_id" in events:
            keys.append("session_id")
        ordered = events.loc[events["event_name"].isin(step_index)].dropna(subset=keys)
        if "event_time" in ordered:
            ordered = ordered.assign(event_time=pd.to_datetime(ordered["event_time"], errors="coerce", utc=True))
            sort_keys = ["event_time", "event_id"] if "event_id" in ordered else ["event_time"]
            ordered = ordered.dropna(subset=["event_time"]).sort_values(sort_keys, kind="stable")
        progress = {}
        for *path, name in ordered[[*keys, "event_name"]].itertuples(index=False, name=None):
            key = tuple(path)
            index = step_index[name]
            if index == progress.get(key, 0):
                reached[index].add(path[0])
                task_counts[index] += 1
                progress[key] = index + 1

    funnel = pd.DataFrame(FUNNEL_STEPS, columns=["event_name", "step"])
    funnel["users"] = [len(users) for users in reached]
    funnel["tasks"] = task_counts
    for count, prefix in [("users", ""), ("tasks", "task_")]:
        previous = funnel[count].shift()
        rate = funnel[count] / previous.where(previous > 0)
        if funnel.at[0, count]:
            rate.at[0] = 1.0
        funnel[f"{prefix}conversion_rate"] = rate
        funnel[f"{prefix}dropoff_rate"] = 1 - rate
    return funnel


def suggestion_summary(suggestions: pd.DataFrame) -> Dict[str, float]:
    if suggestions.empty:
        return {
            "exposed": 0,
            "adopted": 0,
            "adoption_rate": math.nan,
            "avg_adopted_per_user": math.nan,
        }
    exposed = len(suggestions)
    adopted = int(suggestions["adopted"].fillna(False).sum())
    user_count = suggestions["user_id"].nunique()
    return {
        "exposed": exposed,
        "adopted": adopted,
        "adoption_rate": adopted / exposed,
        "avg_adopted_per_user": adopted / user_count if user_count else math.nan,
    }


def north_star_metrics(tasks: pd.DataFrame, events: pd.DataFrame, suggestions: pd.DataFrame) -> Dict[str, float]:
    generated_tasks = len(tasks)
    effective_tasks = int(((tasks["exported"].fillna(False).astype(bool)) & (tasks["adopted_count"] >= 1)).sum()) if generated_tasks else 0
    funnel = calculate_funnel(events).set_index("event_name")
    visit_users = int(funnel.at["visit_product", "users"])
    generated_users = int(funnel.at["generate_suggestion", "users"])
    exported_tasks = int(tasks["exported"].fillna(False).astype(bool).sum()) if generated_tasks else 0
    return {
        "resume_task_count": generated_tasks,
        "suggestion_generation_rate": generated_users / visit_users if visit_users else math.nan,
        "suggestion_adoption_rate": suggestion_summary(suggestions)["adoption_rate"],
        "report_export_rate": exported_tasks / generated_tasks if generated_tasks else math.nan,
        "effective_completion_rate": effective_tasks / generated_tasks if generated_tasks else math.nan,
        "effective_tasks": effective_tasks,
    }


def indicator_tree() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"层级": "北极星指标", "指标/维度": "有效优化任务完成率", "定义": "完成导出报告且至少采纳 1 条建议的任务数 / 生成建议的任务数"},
            {"层级": "一级指标", "指标/维度": "简历优化任务数", "定义": "生成建议的简历优化任务数量"},
            {"层级": "一级指标", "指标/维度": "建议生成率", "定义": "至少有一个任务从访问依次走到生成建议的用户数 / 访问产品用户数"},
            {"层级": "一级指标", "指标/维度": "建议采纳率", "定义": "被采纳建议数 / 建议曝光数"},
            {"层级": "一级指标", "指标/维度": "报告导出率", "定义": "导出报告任务数 / 生成建议任务数"},
            {"层级": "二级拆解", "指标/维度": "用户维度", "定义": "用户类型、目标岗位、经验年限"},
            {"层级": "二级拆解", "指标/维度": "任务维度", "定义": "已采纳建议数、待处理建议数、匹配分变化"},
            {"层级": "二级拆解", "指标/维度": "建议维度", "定义": "建议类型、质量评分、关键词匹配数"},
            {"层级": "二级拆解", "指标/维度": "Prompt 维度", "定义": "A 组 / B 组"},
            {"层级": "二级拆解", "指标/维度": "行为维度", "定义": "访问、上传、生成、采纳、拒绝和导出事件"},
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
        task_features["avg_quality_score"] = math.nan
    if not users.empty:
        task_features = task_features.merge(users[["user_id", "user_type", "target_role", "experience_years"]], on="user_id", how="left")
    return task_features


def export_rate_by_adopted_count(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["adopted_count_group", "tasks", "exported", "export_rate"])
    data = task_features.copy()
    data["adopted_count_group"] = data["adopted_count"].clip(upper=4).astype(str)
    data.loc[data["adopted_count"] >= 4, "adopted_count_group"] = "4+"
    grouped = data.groupby("adopted_count_group", as_index=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"]
    return grouped


def export_rate_by_lift(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["match_score_lift_group", "tasks", "exported", "export_rate"])
    data = task_features.copy()
    data["match_score_lift_group"] = pd.cut(
        data["match_score_lift"],
        bins=[-math.inf, 0, 10, 20, math.inf],
        labels=["≤0", "1-10", "11-20", ">20"],
        include_lowest=True,
    )
    grouped = data.groupby("match_score_lift_group", as_index=False, observed=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"].where(grouped["tasks"] > 0)
    return grouped


def export_rate_by_pending_count(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["pending_count_group", "tasks", "exported", "export_rate"])
    data = task_features.copy()
    data["pending_count_group"] = data["pending_count"].clip(upper=4).astype(str)
    data.loc[data["pending_count"] >= 4, "pending_count_group"] = "4+"
    grouped = data.groupby("pending_count_group", as_index=False).agg(tasks=("task_id", "count"), exported=("exported", "sum"))
    grouped["export_rate"] = grouped["exported"] / grouped["tasks"]
    return grouped


def _correlation(x: pd.Series, y: pd.Series) -> float:
    pairs = pd.DataFrame({"x": x, "y": y}).dropna()
    if pairs["x"].nunique() < 2 or pairs["y"].nunique() < 2:
        return math.nan
    return float(pairs["x"].corr(pairs["y"]))


def _correlation_label(correlation: float) -> str:
    if pd.isna(correlation):
        return "无法估计"
    if abs(correlation) <= 0.03:
        return "弱相关"
    return "正向" if correlation > 0 else "负向"


def export_factor_table(task_features: pd.DataFrame) -> pd.DataFrame:
    if task_features.empty:
        return pd.DataFrame(columns=["影响因素", "分析方法", "影响方向", "参考值", "业务解释"])
    data = task_features.copy()
    target = data["exported"].astype(int)
    rows = []
    numeric_factors = [
        ("adopted_count", "已采纳建议数", "模拟器只允许采纳至少一条建议的任务导出，解读时需考虑这条生成规则。"),
        ("rejected_count", "已拒绝建议数", "记录每个任务被明确拒绝的建议数量。"),
        ("pending_count", "待处理建议数", "记录每个任务尚未被采纳或拒绝的建议数量。"),
        ("current_match_score", "当前 JD 匹配分", "模拟器依据初始分数与采纳情况计算当前分。"),
        ("match_score_lift", "匹配分提升", "当前分减去初始分，结果受模拟器的采纳加分规则影响。"),
        ("avg_quality_score", "平均建议质量分", "按任务汇总建议的具体性、JD 匹配度和可执行性评分。"),
    ]
    for column, label, explanation in numeric_factors:
        corr = _correlation(data[column], target)
        direction = _correlation_label(corr)
        if pd.isna(corr):
            explanation = "样本中缺少可比较的取值，无法计算相关系数。"
        rows.append({"影响因素": label, "分析方法": "与是否导出的相关系数", "影响方向": direction, "参考值": round(corr, 3), "业务解释": explanation})

    for column, label in [("prompt_group", "Prompt 组别"), ("user_type", "用户类型")]:
        if column in data.columns:
            rates = data.groupby(column)["exported"].mean()
            spread = float(rates.max() - rates.min()) if len(rates) > 1 else math.nan
            if pd.isna(spread):
                direction = "样本不足"
            elif spread == 0:
                direction = "各组相同"
            else:
                direction = "、".join(rates.index[rates == rates.max()].astype(str)) + " 更高"
            rows.append(
                {
                    "影响因素": label,
                    "分析方法": "分组导出率差异",
                    "影响方向": direction,
                    "参考值": round(spread, 3),
                    "业务解释": "不同分组导出率差异用于定位需要专项优化的人群或 Prompt 策略。",
                }
            )
    return pd.DataFrame(rows)


def prompt_ab_metrics(tasks: pd.DataFrame, suggestions: pd.DataFrame) -> pd.DataFrame:
    suggestion_stats = pd.DataFrame(columns=["prompt_group", "suggestions", "adopted", "avg_quality_score"])
    if not suggestions.empty:
        suggestion_stats = (
            suggestions.assign(
                adopted=suggestions["adopted"].fillna(False).astype(bool),
                quality_score=suggestions[["specificity_score", "jd_match_score", "actionability_score"]].mean(axis=1),
            )
            .groupby("prompt_group", as_index=False)
            .agg(suggestions=("suggestion_id", "count"), adopted=("adopted", "sum"), avg_quality_score=("quality_score", "mean"))
        )
    task_stats = pd.DataFrame(columns=["prompt_group", "tasks", "exported_tasks"])
    if not tasks.empty:
        task_stats = (
            tasks.assign(exported=tasks["exported"].fillna(False).astype(bool))
            .groupby("prompt_group", as_index=False)
            .agg(tasks=("task_id", "count"), exported_tasks=("exported", "sum"))
        )
    merged = suggestion_stats.merge(task_stats, on="prompt_group", how="outer")
    for key in ["suggestions", "adopted", "tasks", "exported_tasks"]:
        merged[key] = pd.to_numeric(merged[key]).fillna(0).astype(int)
    merged["adoption_rate"] = merged["adopted"] / merged["suggestions"].where(merged["suggestions"] > 0)
    merged["export_rate"] = merged["exported_tasks"] / merged["tasks"].where(merged["tasks"] > 0)
    return merged.sort_values("prompt_group")


def prompt_adoption_contrast(suggestions: pd.DataFrame) -> Dict[str, float]:
    """B minus A exposure-weighted adoption, with a user-clustered delta-method CI."""
    result = {"difference": math.nan, "ci_low": math.nan, "ci_high": math.nan, "users": 0}
    if suggestions.empty:
        return result
    sample = suggestions.loc[suggestions["prompt_group"].isin(["A", "B"])]
    result["users"] = sample["user_id"].nunique()
    totals = sample.groupby("prompt_group")["adopted"].agg(exposed="size", adopted="sum")
    if not {"A", "B"}.issubset(totals.index):
        return result
    rates = totals["adopted"] / totals["exposed"]
    result["difference"] = rates["B"] - rates["A"]
    if sample["user_id"].isna().any() or sample.groupby("prompt_group")["user_id"].nunique().min() < 2:
        return result

    # Each user's influence on the difference includes all their tasks in both arms.
    group = sample["prompt_group"]
    residual = sample["adopted"].fillna(False).astype(int) - group.map(rates)
    contribution = residual / group.map(totals["exposed"]) * group.map({"A": -1, "B": 1})
    by_user = contribution.groupby(sample["user_id"]).sum()
    variance = (by_user ** 2).sum() * len(by_user) / (len(by_user) - 1)
    if variance > 0:
        margin = 1.959963984540054 * math.sqrt(variance)
        result["ci_low"] = max(-1.0, result["difference"] - margin)
        result["ci_high"] = min(1.0, result["difference"] + margin)
    return result


def chi_square_for_prompt_adoption(suggestions: pd.DataFrame) -> Dict[str, float]:
    if suggestions.empty or not {"A", "B"}.issubset(suggestions["prompt_group"].unique()):
        return {"chi_square": math.nan, "p_value": math.nan}

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
        return {"chi_square": math.nan, "p_value": math.nan}

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
    grouped["adoption_rate"] = grouped["adopted"] / grouped["suggestions"].where(grouped["suggestions"] > 0)
    return grouped


def adoption_driver_tables(users: pd.DataFrame, suggestions: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    if suggestions.empty:
        return {
            "quality": quality_adoption_relation(suggestions),
            "type": adoption_by_dimension(suggestions, "suggestion_type"),
            "prompt": adoption_by_dimension(suggestions, "prompt_group"),
            "impact": pd.DataFrame(columns=["影响因素", "影响方向", "impact"]),
        }
    data = suggestions.copy()
    data["adopted"] = data["adopted"].fillna(False).astype(bool)
    data["matched_keyword_count"] = data["matched_keyword"].fillna("").apply(lambda value: len([item for item in str(value).split(",") if item.strip()]))
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
        corr = _correlation(data[column].astype(float), data["adopted"].astype(int))
        rows.append({"影响因素": label, "影响方向": _correlation_label(corr), "impact": round(corr, 3)})
    return {"quality": quality, "type": type_rate, "prompt": prompt_rate, "impact": pd.DataFrame(rows)}


def quality_dimension_impact(suggestions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column, label in [
        ("specificity_score", "具体性"),
        ("jd_match_score", "JD 匹配度"),
        ("actionability_score", "可执行性"),
    ]:
        corr = math.nan if suggestions.empty else _correlation(
            suggestions[column].astype(float), suggestions["adopted"].fillna(False).astype(int)
        )
        rows.append({"dimension": label, "impact": corr})
    return pd.DataFrame(rows)


def user_segment_metrics(users: pd.DataFrame, tasks: pd.DataFrame, suggestions: pd.DataFrame) -> pd.DataFrame:
    columns = ["user_type", "users", "tasks", "suggestions", "adopted", "exported", "adoption_rate", "export_rate", "avg_tasks_per_user"]
    if users.empty:
        return pd.DataFrame(columns=columns)
    profiles = users[["user_id", "user_type"]].dropna(subset=["user_id"]).drop_duplicates("user_id")
    segments = profiles.groupby("user_type").agg(users=("user_id", "size"))
    if not tasks.empty:
        task_groups = tasks.merge(profiles, on="user_id").groupby("user_type")
        segments = segments.join(task_groups.agg(tasks=("task_id", "count"), exported=("exported", "sum")))
    if not suggestions.empty:
        suggestion_groups = suggestions.merge(profiles, on="user_id").groupby("user_type")
        segments = segments.join(suggestion_groups.agg(suggestions=("suggestion_id", "count"), adopted=("adopted", "sum")))
    for count in ["tasks", "exported", "suggestions", "adopted"]:
        segments[count] = segments[count].fillna(0).astype(int) if count in segments else 0
    segments["adoption_rate"] = segments["adopted"] / segments["suggestions"].where(segments["suggestions"] > 0)
    segments["export_rate"] = segments["exported"] / segments["tasks"].where(segments["tasks"] > 0)
    segments["avg_tasks_per_user"] = segments["tasks"] / segments["users"]
    return segments.reset_index()[columns]


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
            adoption = f"{metrics['adoption_rate']:.1%}" if pd.notna(metrics["adoption_rate"]) else "无建议样本"
            export = f"{metrics['export_rate']:.1%}" if pd.notna(metrics["export_rate"]) else "无任务样本"
            performance = f"建议采纳率 {adoption}，报告导出率 {export}，人均任务数 {metrics['avg_tasks_per_user']:.2f}"
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
                "数据依据": "可从转行用户的导出率差异提出能力映射假设，再用访谈验证原因。",
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
