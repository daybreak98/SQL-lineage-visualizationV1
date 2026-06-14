# lateral_view_explode_001

| 字段 | 值 |
|---|---|
| difficulty | S2 |
| dialect | hive/spark |
| covered_features | lateral view, explode, virtual column |
| allowed_partial | true |

期望：识别 row-expanding function 风险，分段中包含 lateral_view。
