from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
from tools.validate_production_dirty_sql_corpus import validate_corpus


CORPUS_DIR = REPOSITORY_ROOT / "测试用例" / "血缘压测_生产脏SQL_20260719"


def test_production_dirty_sql_corpus_meets_static_contract():
    report = validate_corpus(CORPUS_DIR)

    assert len(report) == 10
    assert all(item["line_count"] >= 300 for item in report)
    assert all(item["named_relation_count"] >= 26 for item in report)
    assert all(item["has_dirty_sql_markers"] for item in report)
