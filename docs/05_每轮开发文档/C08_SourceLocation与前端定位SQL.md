# C08｜SourceLocation 与前端定位 SQL

## 1. 本轮目标

让用户点击节点或字段后，前端能定位到原 SQL 中的大致位置。

```text
后端能力：返回 source_locations
前端效果：点击字段 → Locate SQL → Monaco 高亮 SQL 片段
学习重点：位置模型、1-based line/column、近似定位也要标记 confidence
```

---

## 2. SourceLocation 契约

```json
"source_locations": {
  "output_column:order_cnt": {
    "line": 3,
    "column": 12,
    "end_line": 3,
    "end_column": 39,
    "text": "count(order_no) as order_cnt",
    "confidence": "medium"
  }
}
```

规则：

```text
line / column 使用 Monaco 兼容的 1-based 坐标
无法精确定位时返回 approximate，并给 info 诊断
不要因为定位不准影响血缘主结果
```

---

## 3. 支持范围

优先支持：

```text
最终 SELECT 输出字段
简单字段引用
简单 alias
简单表达式整段定位
```

暂不支持：

```text
复杂格式化后位置映射
中文别名 UTF-16 精确 offset
嵌套子查询所有字段位置
```

---

## 4. 前端对接文档

前端点击节点：

```text
1. 获取 node.id
2. 查 result.source_locations[node.id]
3. 如果存在，调用 Monaco revealRange / setSelection
4. 如果不存在，按钮置灰或提示 No source location
```

---

## 5. 测试验收

```text
select a as aa from t → output_column:aa 有 source location
多行 SQL 中 line / column 大致正确
无法定位时不报错，返回诊断 SOURCE_LOCATION_APPROXIMATE 或缺省
```

前端验收：

```text
点击 output 节点
点击 Locate SQL
编辑器跳转并高亮对应片段
```

---

## 6. 禁止越界

不要在本轮重写 SQL formatter。SourceLocation 基于 original_sql 做定位。

---

## 7. 给 OpenCode 的单轮提示词

```text
请只实现 C08：SourceLocation 基础定位。
返回 source_locations 字典，key 使用 graph node id 或 output field id。
坐标使用 Monaco 兼容 1-based line/column。
定位不准时标记 approximate，不允许影响 Analyze 主流程成功。
前端验收是点击字段后 Locate SQL 能高亮 SQL 片段。
```
