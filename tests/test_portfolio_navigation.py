import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app_ai_pm.py")


class PortfolioNavigationTests(unittest.TestCase):
    def test_overview_link_and_back_keep_the_correct_page(self):
        app = AppTest.from_file(APP, default_timeout=25).run()
        self.assertFalse(app.exception)
        app.button[0].click().run()
        self.assertEqual(app.radio(key="portfolio_page").value, "conversion")
        parameter = app.query_params["view"]
        self.assertEqual(parameter[-1] if isinstance(parameter, list) else parameter, "conversion")
        app.radio(key="conversion_measure").set_value("按用户").run()
        app.radio(key="portfolio_page").set_value("operations").run()
        app.radio(key="portfolio_page").set_value("conversion").run()
        self.assertEqual(app.radio(key="conversion_measure").value, "按用户")
        self.assertFalse(app.exception)

    def test_direct_tool_link_and_independent_sql_check(self):
        app = AppTest.from_file(APP, default_timeout=25)
        app.query_params["view"] = "tool"
        app.run()
        self.assertEqual(app.radio(key="portfolio_page").value, "tool")
        app.radio(key="tool_panel").set_value("查看数据口径").run()
        app.button(key="run_sql_check").click().run()
        self.assertFalse(app.exception)
        rows = app.dataframe[-1].value
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows["任务表采纳数"].sum(), 774)
        self.assertEqual(rows["事件导出数"].sum(), 371)
        self.assertTrue(rows[["采纳差值", "导出差值"]].eq(0).all().all())


if __name__ == "__main__":
    unittest.main()
