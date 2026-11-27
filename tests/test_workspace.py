import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class WorkspaceTests(unittest.TestCase):
    def test_review_follows_inputs_and_does_not_award_points_for_clicks(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
        app.run()
        app.radio(key="view_nav").set_value("简历工作台").run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        original = app.metric[0].value
        review = app.session_state["review"]
        button_id = "adopted_" + review["suggestions"][0]["suggestion_id"]
        app.button(key=button_id).click().run()
        self.assertEqual(app.metric[0].value, original)
        self.assertEqual(app.metric[1].value, "1 条")
        self.assertEqual(app.session_state["event_log"][-1]["event_name"], "adopt_suggestion")

        app.radio(key="view_nav").set_value("数据口径").run()
        app.radio(key="view_nav").set_value("简历工作台").run()
        self.assertEqual(app.session_state["review"]["id"], review["id"])
        app.text_area(key="edit_draft_jd").set_value("负责绘制建筑手稿。").run()
        self.assertFalse(app.get("download_button"))
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state["review"]["suggestions"])
        self.assertEqual(app.session_state["event_log"][-1]["event_name"], "unsupported_jd")
        self.assertEqual(
            sum(e["event_name"] == "generate_suggestion" for e in app.session_state["event_log"]), 1
        )


if __name__ == "__main__":
    unittest.main()
