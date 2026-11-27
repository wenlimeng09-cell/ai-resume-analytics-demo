import unittest

import pandas as pd

from operations_view import percent, suggestion_outcomes


class SuggestionOutcomeTests(unittest.TestCase):
    def test_latest_state_is_counted_once_and_pending_is_separate(self):
        fields = ["suggestion_id", "suggestion_type", "status"]
        rows = [
            ("s1", "项目表达", "rejected"),
            ("s1", "项目表达", "adopted"),
            ("s2", "项目表达", "pending"),
            ("s3", "项目表达", "rejected"),
            ("s4", "技能补强", "adopted"),
        ]
        metrics = suggestion_outcomes(pd.DataFrame(rows, columns=fields), "suggestion_type")
        self.assertEqual(
            metrics.loc["项目表达"].to_dict(),
            {
                "generated": 3,
                "adopted": 1,
                "rejected": 1,
                "pending": 1,
            },
        )
        self.assertEqual(percent(1, 3), "33.3%")
        self.assertEqual(percent(0, 0), "—")


if __name__ == "__main__":
    unittest.main()
