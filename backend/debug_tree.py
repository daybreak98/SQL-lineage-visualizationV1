import sqlglot

# 示例1: 简单字段
tree = sqlglot.parse_one("select a from t", dialect="spark")
print("=== 示例1: select a from t ===")
print("tree 类型:", type(tree).__name__)
print("tree.selects:", tree.selects)
print()

# 示例2: 别名
tree2 = sqlglot.parse_one("select a as aa from t", dialect="spark")
print("=== 示例2: select a as aa from t ===")
col = tree2.selects[0]
print("类型:", type(col).__name__)
print("col.alias:", col.alias)
print("col.alias_or_name:", col.alias_or_name)
print("col.this:", repr(col.this))
print()

# 示例3: 函数
tree3 = sqlglot.parse_one("select count(*) as cnt from t", dialect="spark")
print("=== 示例3: select count(*) as cnt from t ===")
col3 = tree3.selects[0]
print("类型:", type(col3).__name__)
print("col3.alias:", col3.alias)
print("col3.this:", repr(col3.this))
print("col3.this.sql():", col3.this.sql(dialect="spark"))
print()

# 示例4: 多字段
tree4 = sqlglot.parse_one("select a, b as bb, count(*) as cnt from t", dialect="spark")
print("=== 示例4: 多字段 + from 表名 ===")
for i, c in enumerate(tree4.selects):
    print(f"  [{i}] type={type(c).__name__}, alias={c.alias!r}, alias_or_name={c.alias_or_name!r}, is Column={isinstance(c, sqlglot.exp.Column)}")
table = tree4.find(sqlglot.exp.Table)
print("FROM 表名:", table.name)