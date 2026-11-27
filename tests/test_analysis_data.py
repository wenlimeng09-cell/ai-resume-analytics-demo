import unittest
from pathlib import Path

import pandas as pd

from analysis_data import filter_cohort, funnel_counts, segment_export
from logic.metrics import FUNNEL_STEPS


class ConversionTests(unittest.TestCase):
    def test_order_and_units(self):
        rows = []

        def event(user, task, index, minute):
            rows.append((user, task, FUNNEL_STEPS[index][0], f"2026-06-01T10:{minute:02d}"))

        for index in range(6):
            event("u1", "finished", index, index)
        event("u1", "finished", 5, 8)
        for index in range(5):
            event("u1", "abandoned", index, index)
        event("u2", "separate", 0, 1)
        event("u2", "separate", 1, 2)
        event("u2", "wrong-task", 2, 3)
        event("u3", "late", 1, 1)
        event("u3", "late", 0, 2)
        sample = pd.DataFrame(rows[::-1], columns=["user_id", "task_id", "event_name", "event_time"])

        tasks = funnel_counts(sample)
        users = funnel_counts(sample, "users")
        self.assertEqual(tasks.reached.tolist(), [4, 3, 2, 2, 2, 1])
        self.assertEqual(users.reached.tolist(), [3, 2, 1, 1, 1, 1])
        self.assertEqual(tasks.iloc[-1].loss_rate, 0.5)
        self.assertEqual(users.iloc[-1].loss_rate, 0)
        self.assertTrue(pd.isna(tasks.iloc[0].previous))
        self.assertTrue(funnel_counts(sample.iloc[:0]).conversion_rate.isna().all())

    def test_zero_denominators_and_no_activity_in_segment(self):
        events = pd.DataFrame(
            [("u", "t", "visit_product", "2026-06-01")],
            columns=["user_id", "task_id", "event_name", "event_time"],
        )
        users = pd.DataFrame({"user_id": ["u", "v"], "user_type": ["x", "y"]})
        sample = {"users": users, "events": events}
        funnel = funnel_counts(events)
        self.assertEqual(funnel.iloc[1].conversion_rate, 0)
        self.assertTrue(pd.isna(funnel.iloc[2].conversion_rate))
        segments = segment_export(sample).set_index("user_type")
        self.assertEqual(set(segments.index), {"x", "y"})
        self.assertTrue(segments.export_rate.isna().all())
        self.assertTrue(segments.loss_share.isna().all())
        filtered = filter_cohort(sample, "y")
        self.assertTrue(filtered["events"].empty)
        self.assertEqual(segment_export(filtered).adopted.tolist(), [0])

    def test_fixed_sample_reconciles_with_task_table_for_every_cohort(self):
        base = Path(__file__).resolve().parents[1] / "data"
        tables = {
            name: pd.read_csv(base / f"{name}.csv")
            for name in ("users", "events", "resume_tasks", "suggestions", "feedback")
        }
        for unit in ["tasks", "users"]:
            segments = segment_export(tables, unit).set_index("user_type")
            for name, group in segments.iterrows():
                subset = filter_cohort(tables, name)
                steps = funnel_counts(subset["events"], unit).set_index("event_name")
                tasks = subset["resume_tasks"]
                key = "task_id" if unit == "tasks" else "user_id"
                adopted = tasks.loc[tasks["adopted_count"].gt(0), key].nunique()
                exported = tasks.loc[tasks["exported"] & tasks["adopted_count"].gt(0), key].nunique()
                self.assertEqual(steps.at["adopt_suggestion", "reached"], adopted)
                self.assertEqual(steps.at["export_report", "reached"], exported)
                self.assertEqual(group.lost, adopted - exported)
            total = funnel_counts(tables["events"], unit)
            self.assertEqual(segments.lost.sum(), total.iloc[-1].lost)
        final = funnel_counts(tables["events"]).iloc[-1]
        self.assertEqual((final.previous, final.reached, final.lost), (774, 371, 403))


if __name__ == "__main__":
    unittest.main()
