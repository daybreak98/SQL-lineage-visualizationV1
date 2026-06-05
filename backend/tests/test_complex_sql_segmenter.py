from app.complex_sql_guard.segmenter import SqlSegmenter


def test_segmenter_cte_join():
    sql = (
        "with a as (select id from t1), "
        "b as (select id from t2) "
        "select a.id from a join b on a.id = b.id where a.id > 1"
    )
    segments = SqlSegmenter().segment(sql, original_sql=sql)
    segment_types = [segment.segment_type for segment in segments]

    assert "cte_block" in segment_types
    assert segment_types.count("cte_item") == 2
    assert "from_join" in segment_types
    assert "join_block" in segment_types
    assert "join_condition" in segment_types


def test_segmenter_lateral_view():
    sql = (
        "select order_id from t "
        "lateral view explode(arr) e as item "
        "where dt = '20260101'"
    )
    segments = SqlSegmenter().segment(sql, original_sql=sql)
    segment_types = [segment.segment_type for segment in segments]

    assert "main_select" in segment_types
    assert "from_join" in segment_types
    assert "lateral_view" in segment_types
    assert "where" in segment_types

