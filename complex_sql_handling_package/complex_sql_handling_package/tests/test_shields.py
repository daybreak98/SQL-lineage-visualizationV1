import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from complex_sql_guard.shields import DirtySqlPreprocessor  # noqa: E402


class TestDirtySqlPreprocessor(unittest.TestCase):
    def test_shields_regex_and_template(self):
        sql = "select regexp_extract(url, '^[^?]+', 0) from t where dt='${DATE}'"
        bundle, diagnostics = DirtySqlPreprocessor().preprocess(sql)
        self.assertIn("__SQLG_STR_", bundle.analysis_sql)
        self.assertIn("__SQLG_TPL_", bundle.analysis_sql)
        self.assertEqual(len(bundle.placeholders), 2)
        kinds = [p.kind for p in bundle.placeholders]
        self.assertIn("template_literal", kinds)
        self.assertIn("string_literal", kinds)

    def test_keeps_original_sql(self):
        sql = "select 'a' as x"
        bundle, _ = DirtySqlPreprocessor().preprocess(sql)
        self.assertEqual(bundle.original_sql, sql)
        self.assertNotEqual(bundle.analysis_sql, sql)


if __name__ == "__main__":
    unittest.main()
