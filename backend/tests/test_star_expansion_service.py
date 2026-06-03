import sqlglot

from app.domain import diagnostics_model as diag_codes
from app.services.star_expansion_service import expand_star_items, _detect_star


def test_star_detection_plain():
    tree = sqlglot.parse_one("select * from t")
    is_star, qual = _detect_star(tree.selects[0])
    assert is_star is True
    assert qual is None


def test_star_detection_qualified():
    tree = sqlglot.parse_one("select o.* from t o")
    is_star, qual = _detect_star(tree.selects[0])
    assert is_star is True
    assert qual == "o"


def test_star_detection_not_star():
    tree = sqlglot.parse_one("select a from t")
    is_star, _q = _detect_star(tree.selects[0])
    assert is_star is False


def test_expand_with_metadata():
    columns = {"dwd_order_di": [{"name": "order_no"}, {"name": "user_id"}, {"name": "amount"}]}
    tree = sqlglot.parse_one("select * from dwd_order_di")
    result = expand_star_items(tree.selects, ["dwd_order_di"], {}, columns)
    assert len(result.lineages) == 3
    assert [l.output_column for l in result.lineages] == ["order_no", "user_id", "amount"]


def test_expand_without_metadata():
    tree = sqlglot.parse_one("select * from unknown_table")
    result = expand_star_items(tree.selects, ["unknown_table"], {}, {})
    assert len(result.lineages) == 0
    assert any(d.code == diag_codes.SELECT_STAR_METADATA_REQUIRED for d in result.diagnostics)


def test_expand_qualified_star():
    columns = {"dwd_order_di": [{"name": "order_no"}, {"name": "user_id"}]}
    tree = sqlglot.parse_one("select o.* from dwd_order_di o")
    result = expand_star_items(tree.selects, ["dwd_order_di"], {"o": "dwd_order_di"}, columns)
    assert len(result.lineages) == 2


def test_expand_mixed_star_and_regular():
    columns = {"dwd_order_di": [{"name": "a"}, {"name": "b"}]}
    tree = sqlglot.parse_one("select *, count(x) as cnt from dwd_order_di")
    result = expand_star_items(tree.selects, ["dwd_order_di"], {}, columns)
    assert len(result.lineages) == 2  # only star expanded, count(x) ignored


def test_expand_multiple_tables_star():
    columns = {
        "t1": [{"name": "a"}],
        "t2": [{"name": "b"}],
    }
    tree = sqlglot.parse_one("select * from t1 join t2 on t1.id = t2.id")
    result = expand_star_items(tree.selects, ["t1", "t2"], {}, columns)
    assert len(result.lineages) == 2
