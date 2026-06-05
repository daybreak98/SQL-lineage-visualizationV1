import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from complex_sql_guard.segmenter import SqlSegmenter  # noqa: E402


class TestSqlSegmenter(unittest.TestCase):
    def test_segments_top_level_clauses(self):
        sql = "with a as (select x from t) select x from a where x > 1 group by x"
        segments = SqlSegmenter().segment(sql)
        types = [s.segment_type for s in segments]
        self.assertIn("cte_block", types)
        self.assertIn("main_select", types)
        self.assertIn("from_join", types)
        self.assertIn("where", types)
        self.assertIn("group_by", types)

    def test_does_not_split_nested_select(self):
        sql = "select x from (select x from t where y=1) s where x > 0"
        segments = SqlSegmenter().segment(sql)
        types = [s.segment_type for s in segments]
        self.assertEqual(types.count("main_select"), 1)


if __name__ == "__main__":
    unittest.main()
