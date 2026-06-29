from __future__ import annotations

import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.resume_analyzer import calculate_match_score, generate_suggestions


DATA_DIR = ROOT / "data"
RANDOM_SEED = 42

USER_TYPES = ["应届生", "实习生", "转行用户"]
TARGET_ROLES = ["数据分析师", "产品运营", "AI 产品助理", "增长分析师"]
JD_TEMPLATES = {
    "数据分析师": "负责业务数据分析、指标体系建设、SQL 取数、Python 数据处理、BI 看板搭建，支持 A/B 实验和产品优化。",
    "产品运营": "负责用户增长、转化漏斗分析、活动效果评估、指标监控，能结合数据分析提出运营优化建议。",
    "AI 产品助理": "参与 AI 产品需求分析、Prompt 设计、用户反馈分析、建议质量评估，了解 RAG 和大模型应用场景。",
    "增长分析师": "围绕用户增长、留存、转化和商业化目标开展分析，熟悉 SQL、A/B 实验、指标体系和可视化看板。",
}
RESUME_SNIPPETS = [
    "参与校园数据分析项目，使用 Excel 进行数据整理，完成基础图表展示。",
    "负责社群运营数据统计，跟踪活动参与人数和转化情况，输出周报。",
    "完成用户行为分析项目，使用 SQL 和 Python 清洗数据，搭建漏斗看板。",
    "参与 AI 简历优化助手项目，设计 Prompt 分组和建议质量评分体系。",
    "从市场岗位转向数据方向，熟悉用户研究、需求分析和业务沟通。",
]


def random_time(start: datetime, day_span: int = 60) -> datetime:
    return start + timedelta(days=random.randint(0, day_span), hours=random.randint(0, 23), minutes=random.randint(0, 59))


def make_users(n_users: int = 900) -> pd.DataFrame:
    start = datetime(2026, 4, 1)
    rows = []
    for idx in range(1, n_users + 1):
        user_type = random.choices(USER_TYPES, weights=[0.42, 0.30, 0.28], k=1)[0]
        role = random.choice(TARGET_ROLES)
        experience = 0 if user_type in ("应届生", "实习生") else random.choice([1, 2, 3])
        rows.append(
            {
                "user_id": f"u_{idx:04d}",
                "register_date": (start + timedelta(days=random.randint(0, 45))).date().isoformat(),
                "user_type": user_type,
                "target_role": role,
                "experience_years": experience,
            }
        )
    return pd.DataFrame(rows)


def add_event(
    events: List[Dict[str, object]],
    user_id: str,
    task_id: str,
    session_id: str,
    event_time: datetime,
    event_name: str,
    suggestion_id: str | None = None,
    prompt_group: str | None = None,
) -> None:
    events.append(
        {
            "event_id": f"e_{len(events) + 1:06d}",
            "user_id": user_id,
            "task_id": task_id,
            "session_id": session_id,
            "event_time": event_time.isoformat(timespec="minutes"),
            "event_name": event_name,
            "suggestion_id": suggestion_id,
            "prompt_group": prompt_group,
        }
    )


def probability_for_task(user_type: str, prompt_group: str) -> Dict[str, float]:
    base = {
        "upload_resume": 0.88,
        "upload_jd": 0.82,
        "generate_suggestion": 0.90,
        "adopt_suggestion": 0.58,
        "export_report": 0.46,
    }
    if prompt_group == "B":
        base["adopt_suggestion"] += 0.10
        base["export_report"] += 0.08
    if user_type == "转行用户":
        base["adopt_suggestion"] -= 0.06
        base["export_report"] -= 0.04
    if user_type == "实习生":
        base["adopt_suggestion"] += 0.03
    return base


def make_tasks_events_suggestions(users: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = datetime(2026, 5, 1)
    tasks: List[Dict[str, object]] = []
    events: List[Dict[str, object]] = []
    suggestion_rows: List[Dict[str, object]] = []
    feedback_rows: List[Dict[str, object]] = []
    task_index = 1

    for _, user in users.iterrows():
        task_count = random.choices([1, 2, 3], weights=[0.72, 0.22, 0.06], k=1)[0]
        if user["user_type"] == "转行用户" and random.random() < 0.22:
            task_count += 1

        for _ in range(task_count):
            role = random.choice(TARGET_ROLES)
            jd_text = JD_TEMPLATES[role]
            resume_text = random.choice(RESUME_SNIPPETS)
            prompt_group = random.choice(["A", "B"])
            task_id = f"t_{task_index:05d}"
            jd_id = f"jd_{role}_{random.randint(1, 12):02d}"
            session_id = f"s_{task_index:05d}"
            created_time = random_time(start)
            probs = probability_for_task(user["user_type"], prompt_group)

            add_event(events, user["user_id"], task_id, session_id, created_time, "visit_product", prompt_group=prompt_group)
            if random.random() > probs["upload_resume"]:
                task_index += 1
                continue
            add_event(events, user["user_id"], task_id, session_id, created_time + timedelta(minutes=1), "upload_resume", prompt_group=prompt_group)
            if random.random() > probs["upload_jd"]:
                task_index += 1
                continue
            add_event(events, user["user_id"], task_id, session_id, created_time + timedelta(minutes=2), "upload_jd", prompt_group=prompt_group)
            if random.random() > probs["generate_suggestion"]:
                task_index += 1
                continue
            add_event(events, user["user_id"], task_id, session_id, created_time + timedelta(minutes=3), "generate_suggestion", prompt_group=prompt_group)

            generated = generate_suggestions(
                resume_text=resume_text,
                jd_text=jd_text,
                task_id=task_id,
                user_id=user["user_id"],
                prompt_group=prompt_group,
            )

            adopted_count = 0
            rejected_count = 0
            for item in generated:
                quality = np.mean([item["specificity_score"], item["jd_match_score"], item["actionability_score"]])
                adoption_probability = probs["adopt_suggestion"] + (quality - 4) * 0.12
                item["adopted"] = random.random() < min(max(adoption_probability, 0.15), 0.92)
                item["status"] = "adopted" if item["adopted"] else "rejected"
                if item["adopted"]:
                    adopted_count += 1
                    add_event(
                        events,
                        user["user_id"],
                        task_id,
                        session_id,
                        created_time + timedelta(minutes=4 + adopted_count),
                        "adopt_suggestion",
                        suggestion_id=item["suggestion_id"],
                        prompt_group=prompt_group,
                    )
                else:
                    rejected_count += 1
                    add_event(
                        events,
                        user["user_id"],
                        task_id,
                        session_id,
                        created_time + timedelta(minutes=4 + rejected_count),
                        "reject_suggestion",
                        suggestion_id=item["suggestion_id"],
                        prompt_group=prompt_group,
                    )
                suggestion_rows.append(
                    {
                        "suggestion_id": item["suggestion_id"],
                        "task_id": task_id,
                        "user_id": user["user_id"],
                        "prompt_group": prompt_group,
                        "suggestion_type": item["suggestion_type"],
                        "resume_section": item["resume_section"],
                        "matched_keyword": item["matched_keyword"],
                        "original_expression": item["original_expression"],
                        "revised_expression": item["revised_expression"],
                        "specificity_score": item["specificity_score"],
                        "jd_match_score": item["jd_match_score"],
                        "actionability_score": item["actionability_score"],
                        "adopted": item["adopted"],
                        "status": item["status"],
                    }
                )

            exported = adopted_count > 0 and random.random() < probs["export_report"]
            if exported:
                add_event(events, user["user_id"], task_id, session_id, created_time + timedelta(minutes=10), "export_report", prompt_group=prompt_group)

            original_match_score = calculate_match_score(resume_text, jd_text)
            current_match_score = min(100, original_match_score + adopted_count * random.randint(5, 9))
            pending_count = len(generated) - adopted_count - rejected_count
            tasks.append(
                {
                    "task_id": task_id,
                    "user_id": user["user_id"],
                    "jd_id": jd_id,
                    "prompt_group": prompt_group,
                    "original_match_score": original_match_score,
                    "current_match_score": current_match_score,
                    "optimized_match_score": current_match_score,
                    "suggestion_count": len(generated),
                    "adopted_count": adopted_count,
                    "rejected_count": rejected_count,
                    "pending_count": pending_count,
                    "exported": exported,
                    "created_time": created_time.isoformat(timespec="minutes"),
                }
            )

            if random.random() < 0.16:
                feedback_rows.append(
                    {
                        "feedback_id": f"fb_{len(feedback_rows) + 1:05d}",
                        "user_id": user["user_id"],
                        "task_id": task_id,
                        "usefulness_score": random.randint(3, 5) if adopted_count else random.randint(1, 4),
                        "trust_score": random.randint(3, 5) if prompt_group == "B" else random.randint(2, 5),
                        "ease_of_use_score": random.randint(3, 5),
                        "comment": "建议更具体时更愿意采纳" if adopted_count else "希望看到更多修改前后对比",
                    }
                )

            task_index += 1

    return pd.DataFrame(tasks), pd.DataFrame(events), pd.DataFrame(suggestion_rows), pd.DataFrame(feedback_rows)


def save_outputs(tables: Dict[str, pd.DataFrame]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for name, df in tables.items():
        df.to_csv(DATA_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")

    db_path = DATA_DIR / "demo.sqlite"
    with sqlite3.connect(db_path) as conn:
        for name, df in tables.items():
            df.to_sql(name, conn, if_exists="replace", index=False)


def main() -> None:
    random.seed(RANDOM_SEED)
    np.random.seed(RANDOM_SEED)
    users = make_users()
    tasks, events, suggestions, feedback = make_tasks_events_suggestions(users)
    save_outputs(
        {
            "users": users,
            "resume_tasks": tasks,
            "events": events,
            "suggestions": suggestions,
            "feedback": feedback,
        }
    )
    print(f"Generated {len(users)} users, {len(tasks)} tasks, {len(events)} events, {len(suggestions)} suggestions.")


if __name__ == "__main__":
    main()
