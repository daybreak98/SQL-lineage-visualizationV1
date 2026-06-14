# nested_subquery_complex

三层层嵌套子查询 + 4个物理表 + 窗口函数 + 复杂CASE WHEN + map语法。
预期：complex_sql_guard检测为复杂SQL，table_structure_service通过query_structure_service的物理表名提取4张表。
