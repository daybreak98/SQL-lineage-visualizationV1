# 亚字段血缘解析

在主工作台左侧打开「亚字段血缘解析」。也可直接访问 [`/?view=subfield`](http://127.0.0.1:5173/?view=subfield)；旧 `/subfield.html` 仍会跳转到该模块。

## 本地运行

在仓库根运行（Windows，首次安装需要 Python 3.11、Node.js 和 npm）：

```powershell
./tools/Start-SubfieldWorkbench.ps1 -Install
```

依赖已安装时可省略 `-Install`，也可通过 `-Python` 使用现有虚拟环境。启动器检查 SQLGlot 30.31.0，启动回环地址上的前后端，并为本次运行创建独立 SQLite 文件。可以用 `-ApiPort`、`-FrontendPort` 调整端口；使用 `-SmokeTest` 时，启动器做一次页面与 API 冒烟后自动退出。

事实缓存默认关闭。可通过 `-EnableSubfieldFactCache` 仅为本次 API 进程启用，用于复用相同分析输入的事实。每次评审仍按当前保护输出重算，缓存不保存评审结果。

## 分析与评审

1. 点「试用示例」分析同表双 JSON 合成查询，或点「编辑 SQL 原文」，输入 SQL、选择 Hive 或 Spark，再点「分析 SQL」。
2. 从「表血缘」或「JSON 排查」选路径。点节点、连线、窗口、生成器或其他报告条目查看原文证据；「在编辑器定位」仅指向本次提交的 SQL。
3. 在「剪枝评审」勾选保护输出并提交。例如双 JSON 示例可选 `item_id`，查看该根的已观察路径需求。未列出的路径不能据此判定可删。
4. 点「下载证据（JSON）」在本地保存当前分析或评审的请求和响应。更换保护输出后，旧评审不再作为当前结果下载；下载本身不会发送请求。

内置窗口、文本 Map、单根双分支、双 JSON 和单列示例均为合成 SQL。文本 Map 的键不等同于 JSON 子路径；COALESCE 值路径也不能证明行集等价。页面不执行用户提交的 SQL，不产生生产改写或删键指令。

## API

前端使用同源 `POST /api/sql/subfield-lineage` 静态分析 SQL。Vite 可通过 `BACKEND_PROXY_TARGET` 配置开发代理（默认 `http://localhost:8000`）。

```powershell
$body = @{
  dialect = 'spark'
  sql = "SELECT get_json_object(payload, '$.id') AS id FROM events"
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/sql/subfield-lineage -Method Post -ContentType 'application/json' -Body $body
```

`uses` 记录使用证据，`mappings` 记录输出映射，`unknowns` 与 `coverage` 记录未决和解析范围。部分恢复不算完整解析；完整解析也不表示血缘或行集已验证。可选 `source_schemas` 是调用方声明，并不认证实际生产目录。
### 两跳证据复用（独立候选，默认缓存关闭）

`SUBFIELD_FACT_CACHE=1` 下，本地、无凭据且使用标准 30 秒请求保护的路由复用同进程事实。分析函数身份、sqlglot 版本、规则命名空间 `facts-v2:two-step-v1`、精确 SQL、方言和 schema 描述组成键；更改规则后重启进程。根和候选键不进入缓存键。普通分析可以预热事实，也可以直接从冷评审开始。首次合格评审为最多八个候选根共建一张图，按完整端口保存核验过的证据。空字典表示本次核验无根出证。仅保留 JSON 字节，不保存 AST、全图或请求的 review。每次仍按所选根与候选键计算原评审。

负筛先查看现役事实中的 `parse/json` 分界，不用扁平路径作为正证。额外上限为 16,384 SQL 字符、64 项映射、8 个候选根，映射可见作用域须为同一语句的 2–8 个；融合、位置、绑定和未知项仍须通过原门槛。可选层故障只去掉附加块。复用沿用原缓存：30 秒 TTL、最多 2 项、每项 128 KiB、总共 256 KiB，描述符最多 16 KiB，仅在成功且请求用时不超过 250 ms 时发布。250 ms 是写缓存门槛，不是性能承诺。禁用、过期、驱逐、超限或多进程时不保证跨请求复用；同时到达的冷请求没有合并。在冷请求上仍有一次额外的结构解析。

针对性复跑：从 backend 目录运行 `python -B -m pytest -q -s tests/test_static_extraction_evidence.py tests/test_subfield_fact_cache.py`。首次运行若 `.pytest_cache` 尚不存在，先创建该目录供仓库测试 SQLite 数据库使用。打印值分别为累计基础分析、结构分析和快照构建调用次数，以及本机单次 HTTP 耗时。

### ALG-P3 · 本机前端接入合同

沿用 `POST /api/sql/subfield-lineage`（analyze）。客户端本机试用配置默认关闭；关闭时不发详情请求。开启后，用户点击某一输出时才在该次请求体设置 `include_two_step_evidence: true`。省略或 false 均不计算或返回附加块。此字段控制取证，不是权限凭据。服务仍依赖原有本地访问保护；`SUBFIELD_FACT_CACHE=1` / `-EnableSubfieldFactCache` 只控制跨请求复用，关缓存也能出证。P3 未实现 UI 设置或新增服务能力发现接口；使用已确认版本的后端，不能用 HTTP 200 推断支持该功能。

**双输出示例：原查键请求（原样保存供展示/下载）**

```json
{"sql":"WITH c AS (SELECT get_json_object(s.j,'$.a') AS x FROM src s) SELECT get_json_object(c.x,'$.b') AS hit, get_json_object(c.x,'$.z') AS alt FROM c","dialect":"spark","protected_outputs":[{"statement":1,"scope":"1:2","slot":1},{"statement":1,"scope":"1:2","slot":2}],"candidate_keys":[{"source":"src","column":"j","keys":["a"]}]}
```

原响应中的 `review.candidate_assessment` 为 `{"status":"UNKNOWN","reason":"PROTECTED_PATH_UNVERIFIED","entries":[]}`，无两跳块。查看 alt 时复制原请求，仅把 `protected_outputs` 改为 `[{"statement":1,"scope":"1:2","slot":2}]` 并增加 `"include_two_step_evidence":true`。保留 SQL 原文、显式方言及来源声明；不得为了出证忽略 `source_schemas`。当前有非 null 声明（包括 `{}`）不出证。多根即使传 true，仍原样返回原评审。

alt 详情响应片段（`review.static_extraction_evidence` 的字段节选）：

```json
{"status":"REVIEW_ONLY","rowset_verified":false,"pruning_authorized":false,"protected_output":{"snapshot":"local:1303366d1891925183124786adb2567a62ce227ad4049b8f4021a3f5bed298e3","sql_sha256":"1303366d1891925183124786adb2567a62ce227ad4049b8f4021a3f5bed298e3","statement":1,"scope":"1:2","slot":2},"projection_position":{"start":134,"end":137,"line":1,"column_end":137}}
```

接收时先检查详情请求仍是当前一次，SQL 原字节、显式方言、schema 状态和完整槽一致；核对 coverage 的 SQL 摘要/方言、protected_output 的 `local:<摘要>`/摘要/槽、首条 witness 的 consumer 及投影位置。witness 从根向源排列，显示先后顺序则从源向根读取 EXTRACT 操作：alt 为 a→z，hit 为 a→b，而非源 JSON 的 `$.a.z` 或 `$.a.b`。`projection_position` 指别名；各边 `evidence.position` 指原文列引用标记，不代表整段表达式范围。位置为零基起点、右端不含，基于 Python Unicode 码点；对接使用 UTF-16 的编辑器时应换算。只更新当前输出详情，不能覆盖原多根回包或下载快照。

HTTP 200 可能没有 `review.static_extraction_evidence`；只表达“本次未提供该输出的两步读取证据，这不表示未读取”，不推断缺块原因。身份不匹配、请求过时则丢弃；不能回退上一根，缺可信坐标不提供定位。来源为 SQL 中声明的列，物理存在、行集和修改影响未验证。

定向验证：在候选 backend 目录先创建 `.pytest_cache`，执行 `python -B -m pytest -q tests/test_static_extraction_evidence.py -k two_output_detail_contract`；仅使用进程内 HTTP TestClient，不启动服务。
