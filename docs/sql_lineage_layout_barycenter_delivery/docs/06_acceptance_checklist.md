# 验收清单

## 功能验收

- [ ] GraphViewModel node 包含 `rank`、`lane`、`semantic_role`、`order_in_rank`、`position`。
- [ ] GraphViewModel 包含 `layout_hint`。
- [ ] `search_result` 和 `order_result` 作为聚合 CTE 被放入 rank=3。
- [ ] 最终输出字段被放入 rank=4。
- [ ] `S2D`、`S2O`、`搜索点击率_pv` 等搜索指标靠近 `search_result`。
- [ ] `订单ADR` 靠近 `order_result`。
- [ ] `单UV收益`、`曝光与订单adr_gap` 处于 mixed 区域。
- [ ] 同分数节点保留 SQL 原始顺序。
- [ ] 端口字段顺序能跟随下游输出字段位置。

## 工程验收

- [ ] Controller 不包含布局算法。
- [ ] GraphBuilder 不直接包含 crossing minimization 细节。
- [ ] GraphLayoutPlanner 可单独单测。
- [ ] 旧 GraphViewModel 没有布局字段时仍可运行。
- [ ] 用户拖拽位置只进入前端 GraphInteractionState，不污染后端 GraphViewModel。

## 性能验收

- [ ] 100 个节点、300 条边在本地毫秒级完成。
- [ ] 1000 个节点、3000 条边可在可接受时间内完成。
- [ ] sweep iterations 可配置，默认 4。

## 回归验收

- [ ] 运行 `python -m unittest discover -s tests -v` 全部通过。
- [ ] `examples/run_demo.py` 可以输出排序后的节点坐标。
