"""Conversion metrics for the portfolio's fixed, simulated event logs."""

import pandas as pd

from logic.metrics import FUNNEL_STEPS


def filter_cohort(tables, user_type=None):
    """Apply the same user cohort to each of the five source tables."""
    if user_type in (None, "全部人群"):
        return tables
    users = tables["users"]
    ids = users.loc[users["user_type"].eq(user_type), "user_id"]
    return {name: table.loc[table["user_id"].isin(ids)] for name, table in tables.items()}


def _task_progress(events):
    """Largest prefix of FUNNEL_STEPS completed in order by each (user, task)."""
    columns = ["user_id", "task_id", "stage_count"]
    if events.empty:
        return pd.DataFrame(columns=columns)
    step_number = {name: index for index, (name, _) in enumerate(FUNNEL_STEPS)}
    logs = events.loc[events["event_name"].isin(step_number)].dropna(subset=["user_id", "task_id"])
    logs = logs.assign(
        event_time=pd.to_datetime(logs["event_time"], format="mixed", utc=True, errors="coerce")
    )
    # Tied timestamps in the supplied logs retain order through their sequential event IDs.
    order = ["event_time", "event_id"] if "event_id" in logs else ["event_time"]
    logs = logs.dropna(subset=["event_time"]).sort_values(order, kind="stable")
    progress = {}
    for user, task, name in logs[["user_id", "task_id", "event_name"]].itertuples(
        index=False, name=None
    ):
        key = (user, task)
        current = progress.get(key, 0)
        if step_number[name] == current:
            progress[key] = current + 1
    rows = [(user, task, stages) for (user, task), stages in progress.items()]
    return pd.DataFrame.from_records(rows, columns=columns)


def _observation_units(events, unit):
    paths = _task_progress(events)
    if unit == "tasks":
        return paths
    if unit == "users":
        # Each user reaches a step when at least one of their tasks completes that prefix.
        return paths.groupby("user_id", as_index=False)["stage_count"].max()
    raise ValueError("unit must be 'tasks' or 'users'")


def funnel_counts(events, unit="tasks"):
    paths = _observation_units(events, unit)
    result = pd.DataFrame(FUNNEL_STEPS, columns=["event_name", "step"])
    result["reached"] = [int(paths["stage_count"].ge(i).sum()) for i in range(1, len(result) + 1)]
    result["previous"] = result["reached"].shift().astype("Int64")
    result["lost"] = result["previous"] - result["reached"]
    denominator = result["previous"].astype(float).where(result["previous"].gt(0))
    result["conversion_rate"] = result["reached"] / denominator
    result["loss_rate"] = result["lost"].astype(float) / denominator
    return result


def segment_export(tables, unit="tasks"):
    """Adoption-to-export conversion and share of the total loss by user type."""
    users = tables["users"][["user_id", "user_type"]].drop_duplicates("user_id")
    paths = _observation_units(tables["events"], unit).merge(users, on="user_id", how="left")
    paths["user_type"] = paths["user_type"].fillna("未标注")
    groups = pd.Index(users["user_type"].dropna().unique(), name="user_type").union(
        paths["user_type"].unique()
    )
    adoption = next(
        index for index, (name, _) in enumerate(FUNNEL_STEPS, 1) if name == "adopt_suggestion"
    )
    export = next(index for index, (name, _) in enumerate(FUNNEL_STEPS, 1) if name == "export_report")
    paths["adopted"] = paths["stage_count"].ge(adoption)
    paths["exported"] = paths["stage_count"].ge(export)
    grouped = (
        paths.groupby("user_type")[["adopted", "exported"]]
        .sum()
        .reindex(groups, fill_value=0)
        .astype(int)
    )
    grouped["lost"] = grouped["adopted"] - grouped["exported"]
    grouped["export_rate"] = grouped["exported"] / grouped["adopted"].where(grouped["adopted"] > 0)
    total_lost = grouped["lost"].sum()
    grouped["loss_share"] = grouped["lost"] / total_lost if total_lost else float("nan")
    return (
        grouped.rename_axis("user_type")
        .reset_index()
        .sort_values(["lost", "user_type"], ascending=[False, True], ignore_index=True)
    )
