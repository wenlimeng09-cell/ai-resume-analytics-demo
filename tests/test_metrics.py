import math
import unittest

import pandas as pd

from logic import metrics


class FunnelTests(unittest.TestCase):
    def test_order_deduplication_and_separate_tasks_for_one_user(self):
        rows = []

        def event(task, minute, name):
            rows.append(("u1", task, f"2026-05-01T10:{minute:02d}", name))

        for minute, (name, _) in enumerate(metrics.FUNNEL_STEPS):
            event("complete", minute, name)
        event("complete", 7, "export_report")
        event("incomplete", 1, "upload_resume")
        event("incomplete", 2, "visit_product")
        event("incomplete", 3, "upload_jd")
        event("orphan", 4, "generate_suggestion")
        events = pd.DataFrame(rows[::-1], columns=["user_id", "task_id", "event_time", "event_name"])

        result = metrics.calculate_funnel(events)
        self.assertEqual(result.tasks.tolist(), [2, 1, 1, 1, 1, 1])
        self.assertEqual(result.users.tolist(), [1, 1, 1, 1, 1, 1])
        self.assertEqual(result.at[1, "task_conversion_rate"], 0.5)
        self.assertEqual(result.at[1, "conversion_rate"], 1)

    def test_empty_stage_keeps_true_zero_separate_from_missing_denominator(self):
        events = pd.DataFrame([{"user_id": "u1", "event_name": "visit_product"}])
        result = metrics.calculate_funnel(events)
        self.assertEqual(result.at[1, "task_conversion_rate"], 0)
        self.assertTrue(math.isnan(result.at[2, "task_conversion_rate"]))
        self.assertTrue(metrics.calculate_funnel(events.iloc[:0]).task_conversion_rate.isna().all())


class DenominatorTests(unittest.TestCase):
    def test_user_average_includes_users_without_tasks(self):
        users = pd.DataFrame({"user_id": [1, 2, 3], "user_type": ["x", "x", "y"]})
        tasks = pd.DataFrame({"user_id": [1], "task_id": ["t"], "exported": [False]})
        result = metrics.user_segment_metrics(users, tasks, pd.DataFrame()).set_index("user_type")
        self.assertEqual(result.at["x", "avg_tasks_per_user"], 0.5)
        self.assertEqual(result.at["x", "export_rate"], 0)
        self.assertTrue(math.isnan(result.at["y", "export_rate"]))
        self.assertTrue(result.adoption_rate.isna().all())
        ab = metrics.prompt_ab_metrics(tasks.assign(prompt_group="A"), pd.DataFrame())
        self.assertEqual(ab.at[0, "tasks"], 1)
        self.assertEqual(ab.at[0, "export_rate"], 0)
        self.assertTrue(math.isnan(ab.at[0, "adoption_rate"]))

    def test_quality_bucket_with_no_exposed_suggestions_has_no_rate(self):
        suggestions = pd.DataFrame([{
            "suggestion_id": "s1", "adopted": False,
            "specificity_score": 5, "jd_match_score": 5, "actionability_score": 5,
        }])
        result = metrics.quality_adoption_relation(suggestions)
        self.assertTrue(result.loc[result["suggestions"] == 0, "adoption_rate"].isna().all())
        self.assertEqual(result.loc[result["suggestions"] == 1, "adoption_rate"].item(), 0)

    def test_clustered_interval_uses_users_not_individual_suggestions(self):
        records = []
        for user in range(40):
            records.extend([(user, "A", user < 20), (user, "B", user < 28)])
        sample = pd.DataFrame(records, columns=["user_id", "prompt_group", "adopted"])
        contrast = metrics.prompt_adoption_contrast(sample)
        # Each paired user's B-A outcome is 0 or 1. With equal exposure, this
        # reduces to the standard error of the mean of the 40 paired differences.
        expected_margin = 1.959963984540054 * math.sqrt(0.2 * 0.8 / 39)
        self.assertAlmostEqual(contrast["difference"], 0.2)
        self.assertAlmostEqual(contrast["ci_low"], 0.2 - expected_margin)
        self.assertAlmostEqual(contrast["ci_high"], 0.2 + expected_margin)
        repeated = metrics.prompt_adoption_contrast(pd.concat([sample] * 5, ignore_index=True))
        self.assertAlmostEqual(repeated["ci_low"], contrast["ci_low"])
        self.assertEqual(repeated["users"], 40)
        one_arm = metrics.prompt_adoption_contrast(sample[sample.prompt_group == "A"])
        self.assertTrue(math.isnan(one_arm["difference"]))


if __name__ == "__main__":
    unittest.main()
