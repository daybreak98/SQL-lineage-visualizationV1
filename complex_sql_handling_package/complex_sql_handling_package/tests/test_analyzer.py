import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from complex_sql_guard import ComplexSqlAnalyzer  # noqa: E402


class TestComplexSqlAnalyzer(unittest.TestCase):
    def test_analyze_dirty_sql_returns_partial_or_success(self):
        sql = """
        with base as (
          select regexp_extract(url, '^[^?]+', 0) as path
          from log_table
          where dt='${DATE}'
        )
        select path from base
        """
        result = ComplexSqlAnalyzer().analyze(sql, dialect="spark")
        self.assertIn(result.status.value, ["success", "partial"])
        self.assertGreater(result.capabilities["placeholder_count"], 0)
        self.assertGreater(result.capabilities["segment_count"], 0)


if __name__ == "__main__":
    unittest.main()
