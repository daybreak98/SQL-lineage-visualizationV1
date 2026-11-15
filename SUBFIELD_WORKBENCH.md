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
