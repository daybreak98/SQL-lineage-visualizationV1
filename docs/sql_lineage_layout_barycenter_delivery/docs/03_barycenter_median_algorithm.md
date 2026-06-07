# Barycenter / Median 同层排序算法说明

## 1. 它解决什么问题

分层布局只决定节点在哪一列，例如：

```text
L0 物理表
L1 基础 CTE
L2 明细增强 CTE
L3 聚合 CTE
L4 最终输出字段
```

但真正影响边交叉的是：

```text
同一层内部节点上下顺序怎么排？
```

Barycenter / Median 排序就是用来解决同层节点排序问题。

## 2. Barycenter

核心思想：

```text
一个节点应该放在它所连接的邻居节点的平均位置附近。
```

公式：

```text
score(node) = avg(position(neighbor))
```

加权版本：

```text
score(node) = sum(position(neighbor) * edge_weight) / sum(edge_weight)
```

## 3. Median

核心思想：

```text
一个节点应该放在它所连接的邻居节点的中位数附近。
```

公式：

```text
score(node) = median(position(neighbor))
```

Median 对极端公共依赖更稳，不容易被少数远距离节点拉偏。

## 4. 推荐策略

| 场景 | 推荐 |
|---|---|
| 小图 / 常规图 | Weighted Barycenter |
| 大图 / 公共依赖多 | Median |
| 字段端口排序 | Barycenter |
| 公共节点定位 | Median 或下游中位数 |

## 5. 多轮 Sweep

只从左到右排序不够，因为上游也应该被下游输出结构反向校正。

推荐：

```text
left -> right
right -> left
left -> right
right -> left
```

执行 2~4 轮。

## 6. 保留 SQL 顺序

不能完全破坏 SQL 顺序，否则用户会觉得图与 SQL 不一致。

推荐排序 key：

```text
rank
lane_priority
rounded_barycenter_score
sql_order
node_id
```

或者：

```text
先按 barycenter 分组，组内按 SQL 原始顺序。
```

## 7. 边权重建议

| edge_type | weight |
|---|---:|
| value_lineage | 5 |
| aggregate_input | 4 |
| join_key | 3 |
| group_by | 2 |
| filter | 1 |
| diagnostic | 0.5 |

这样可以优先减少主血缘路径的交叉，不被大量过滤条件边打乱。
