# SQL 血缘解析可视化｜Python 初学者迭代开发总文档


# SQL 血缘解析可视化｜Python 初学者友好型迭代开发文档包

> 版本：Beginner Iterative v1.0  
> 日期：2026-06-02  
> 适用对象：Python 初学者 + OpenCode / Agent 辅助开发  
> 项目目标：以 SQLGlot + Python + SQLite 为后端核心，逐步接入 React 前端，使每一轮开发都有可运行后端能力、可见前端效果和可回归测试。

---

## 1. 这版文档解决什么问题

原文档体系已经比较完整，但它默认读者具备较强工程经验，适合 Agent 或有经验开发者直接按模块重写后端。当前你的实际需求是：

```text
先从最小后端能力开始
→ 让前端按钮真的能触发后端
→ 每一轮只增加一个后端能力点
→ 每一轮都能在前端看到效果
→ 每一轮都能测试验证
→ 最后自然长成完整 SQL 血缘工作台
```

因此，本包将原来的“大模块拆解”调整为“纵向小闭环迭代”：

```text
C00 健康检查
C01 Analyze 占位响应
C02 SQLGlot 解析
C03 单表字段血缘
C04 Join 与别名
C05 CTE / 子查询结构依赖
C06 元数据 JSON + SQLite
C07 select * 与 unknown / ambiguous 诊断
C08 SourceLocation 定位 SQL
C09 表达式依赖与口径详情
C10 Golden Case 回归冻结
```

---

## 2. 推荐阅读顺序

```text
00_调整说明与变更记录.md
  ↓
01_总路线图_Python初学者版.md
  ↓
02_迭代总表_后端能力与前端效果.md
  ↓
03_后端最小契约_AnalysisResult稳定版.md
  ↓
04_前端对接总规范.md
  ↓
05_每轮开发文档/C00...
  ↓
06_给OpenCode的分阶段提示词.md
  ↓
07_验收用SQL_Golden_Cases.md
```

---

## 3. 当前主线判断

后续开发时，不再把 `01_Agent模块拆解文档/M01-M28` 作为第一阅读入口。它们保留为后置能力池。

当前主线入口改为：

```text
05_每轮开发文档/
```

每轮遵循同一模式：

```text
后端最小能力
→ API 契约
→ 前端触发效果
→ 测试验收
→ 禁止越界
→ 给 OpenCode 的单轮提示词
```

---

## 4. 执行原则

1. **每轮只解决一个核心能力，不跨轮偷做功能。**
2. **每轮结束必须能启动后端、点击前端、看到效果。**
3. **前端不推断血缘，血缘结论必须来自后端。**
4. **后端不返回 SQLGlot AST，只返回稳定契约。**
5. **无法确定的字段、表、表达式必须进入 diagnostics，不伪装成功。**
6. **每轮必须保留测试，不能靠删除测试过关。**

---

## 5. 给你的使用建议

你可以把某一轮文档单独交给 OpenCode，例如：

```text
请严格按照 05_每轮开发文档/C03_单表字段血缘与画布首图.md 实现。
只能做 C03，不允许提前做 C04-C10。
实现后运行本文档中的后端测试和前端联调验收。
```

如果某一轮失败，不要继续下一轮，先修到该轮验收通过。


---


# 01｜总路线图：Python 初学者版

---

## 1. 一句话目标

把 SQL 血缘项目拆成一组能连续跑通的小台阶：

```text
每一轮 = 一个最小后端能力 + 一个前端可见效果 + 一组测试验收
```

最终形成：

```text
SQL 输入
→ 后端静态解析
→ 字段 / 表 / CTE / 子查询血缘
→ GraphViewModel
→ React 前端画布展示
→ 搜索、定位、详情、诊断
```

---

## 2. 初学者不要一开始做什么

第一阶段不要一上来做这些：

```text
完整 SQL 解析器
完整字段级血缘
复杂 CTE / 子查询递归
SQLite 元数据系统
Monaco 智能提示
复杂 SourceLocation
历史快照
SQL diff
AI 解释
```

这些功能不是不做，而是后置。初学者路线最怕“第一轮就把所有技术点叠在一起”。

---

## 3. 技术学习顺序

| 顺序 | 要学的技术 | 对应轮次 | 学到什么程度即可 |
|---|---|---|---|
| 1 | Python 项目结构 | C00 | 知道 `app/main.py`、包、导入路径 |
| 2 | FastAPI 路由 | C00-C01 | 能写 GET / POST 接口 |
| 3 | Pydantic 模型 | C01 | 能定义请求体和响应体 |
| 4 | pytest 接口测试 | C00-C01 | 能测 200、字段存在、状态正确 |
| 5 | SQLGlot parse | C02 | 能判断 SQL 是否能解析，能拿到 SELECT 输出 |
| 6 | 简单血缘建模 | C03 | 能从 `select a from t` 生成 `t.a -> output.a` |
| 7 | 别名与 Join | C04 | 能处理 `u.name`、`o.order_id` 来源 |
| 8 | CTE / 子查询 | C05 | 能聚合结构依赖，不强行做所有复杂字段 |
| 9 | SQLite | C06 | 能导入表字段、查字段注释 |
| 10 | 诊断系统 | C07 | 能表达 unknown / ambiguous |
| 11 | SourceLocation | C08 | 能定位到 SQL 大概字段位置 |
| 12 | 表达式 / 口径 | C09 | 能解释 `sum(amount)`、`gmv/order_cnt` 依赖 |
| 13 | 回归测试 | C10 | 能防止后续改坏核心能力 |

---

## 4. C00-C10 总体阶段

```text
阶段 A：先让系统活起来
C00 环境启动与 FastAPI 健康检查
C01 Analyze 占位响应与前端按钮打通

阶段 B：开始理解 SQL
C02 SQLGlot 解析与输出字段识别
C03 单表字段血缘与画布首图
C04 Join 别名字段归属与诊断

阶段 C：开始支持真实数仓 SQL 形态
C05 CTE / 子查询结构依赖与默认视图
C06 元数据 JSON 导入 SQLite 与字段补全
C07 select * 展开、unknown、ambiguous 诊断

阶段 D：增强交互体验
C08 SourceLocation 与前端定位 SQL
C09 表达式依赖与口径详情面板

阶段 E：冻结质量
C10 Golden Case 回归与交付冻结
```

---

## 5. 每轮固定产出

每轮必须产出：

```text
1. 后端代码变更
2. API 响应样例
3. 前端可见效果
4. 测试用例
5. 禁止越界清单
6. 下一轮输入
```

任何一轮如果不能在前端看到效果，就不要进入下一轮。

---

## 6. 推荐本地启动方式

后端：

```bash
cd backend
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

浏览器：

```text
http://localhost:5173
```

前端请求：

```text
/api/... → Vite proxy → http://127.0.0.1:8000/api/...
```


---


# 02｜迭代总表：后端能力与前端效果

| 轮次 | 后端最小能力 | API | 前端可见效果 | 测试重点 | 是否进入下一轮 |
|---|---|---|---|---|---|
| C00 | FastAPI 应用启动、健康检查 | GET `/api/health` | 顶部 Health 状态可显示后端在线 | health 返回 200 | 后端能启动且前端不报代理错误 |
| C01 | Analyze 接口占位响应 | POST `/api/sql/analyze` | 点击 Analyze 后出现 partial / info 诊断，不再 404 | analyze 返回稳定空图契约 | 前端按钮能触发后端 |
| C02 | SQLGlot parse + 输出字段识别 | POST `/api/sql/analyze` | 输出字段列表出现，如 `country_name`、`order_cnt` | 简单 SQL 解析成功，错误 SQL failed | 前端能展示后端识别的输出字段 |
| C03 | 单表字段血缘 | POST `/api/sql/analyze` | 画布出现 `table.column -> output.column` | `select a from t` 生成节点和边 | 首张图能渲染 |
| C04 | Join 与表别名归属 | POST `/api/sql/analyze` | 多张表节点、字段节点、unknown 诊断出现 | `u.id = o.user_id` 来源不混乱 | Join SQL 图可读 |
| C05 | CTE / 子查询结构依赖 | POST `/api/sql/analyze` | Analyze 成功后默认进入 `subquery_dependency` | CTE 层级边存在 | 默认不展示字段复杂全图 |
| C06 | 元数据 JSON 导入 SQLite | POST `/api/metadata/import/*`，GET `/api/metadata/*` | Metadata Preview / Commit 可用，字段注释可展示 | 导入、查询、重复导入 | 元数据可被 analyze 使用 |
| C07 | select * 展开与诊断 | POST `/api/sql/analyze` | unknown / ambiguous 以诊断和特殊节点展示 | 星号展开、字段冲突 | 不确定信息不伪装成功 |
| C08 | SourceLocation 基础定位 | POST `/api/sql/analyze` | 点击字段后 Locate SQL 能高亮 SQL 片段 | line / column 粗定位 | 前后端定位闭环可用 |
| C09 | 表达式依赖与口径详情 | POST `/api/sql/analyze` | DetailPanel 展示表达式依赖和口径说明 | `gmv/order_cnt` 依赖完整 | 指标理解能力可用 |
| C10 | Golden Case 回归冻结 | pytest / 前端手工验收 | 核心 SQL 全流程稳定 | golden case 全通过 | 可以进入 P1 扩展 |

---

## 1. 每轮验收标准模板

每轮验收都按下面五项检查：

```text
后端启动：uvicorn 可启动，无 import error
接口调用：curl / 浏览器 / 前端都能调用
前端效果：页面有明确变化，而不是只看控制台
测试通过：pytest 指定测试通过
边界遵守：没有提前实现下一轮大功能
```

---

## 2. 失败处理规则

如果某轮失败，按这个顺序排查：

```text
1. 后端是否启动
2. API 路径是否和前端一致
3. 响应 JSON 是否符合前端类型
4. graph_view_model.nodes / edges 是否结构正确
5. 诊断是否被前端吞掉
6. Vite proxy 是否正确指向 8000
```

不要通过删除测试、注释前端错误、硬编码 fake success 的方式过关。


---


# 03｜后端最小契约：AnalysisResult 稳定版

> 本文定义 C01 起就应稳定下来的最小响应结构。后续功能只往里面填内容，不随意改字段名。

---

## 1. Analyze 请求体

```json
{
  "sql": "select a from t",
  "dialect": "spark",
  "analysis_level": "column",
  "default_catalog": "default",
  "default_schema": "default",
  "metadata_version": "latest",
  "case_sensitive": false,
  "analysis_options": {
    "include_graph": true,
    "include_semantics": false,
    "include_diagnostics": true,
    "include_source_location": true,
    "include_expression_lineage": false
  }
}
```

初学者实现时，C01-C03 可以先只真正使用：

```text
sql
dialect
analysis_options.include_graph
```

其他字段先接收并透传，不强制实现功能。

---

## 2. Analyze 响应体最小结构

```json
{
  "schema_version": "0.3.0-beginner",
  "analysis_id": "analysis:xxx",
  "status": "success | partial | failed",
  "confidence_level": "high | medium | low | unknown",
  "confidence_reasons": [],
  "elapsed_ms": 12,
  "dialect": "spark",
  "normalized_sql": null,
  "stage_statuses": [],
  "unsupported_features": [],
  "diagnostics_report": {
    "diagnostics": [],
    "error_count": 0,
    "warning_count": 0,
    "info_count": 0
  },
  "graph_view_model": {
    "view_mode": "column",
    "nodes": [],
    "edges": []
  },
  "output_fields": [],
  "source_locations": {},
  "metadata_context": {},
  "semantics_report": null
}
```

---

## 3. 状态语义

| status | 语义 | 前端表现 |
|---|---|---|
| success | 本轮能力范围内分析成功 | 可正常展示图、搜索、详情 |
| partial | 接口成功，但有能力未实现或部分字段未知 | 展示图，同时展示 warning / info |
| failed | SQL 解析失败或服务异常 | 画布进入失败态，搜索禁用 |

禁止把未实现功能返回成 `success`。

---

## 4. GraphViewModel 最小节点

```json
{
  "id": "column:t.a",
  "node_type": "column",
  "label": "t.a",
  "title": "t.a",
  "subtitle": "physical column",
  "data": {
    "column_name": "a",
    "table_name": "t"
  }
}
```

推荐 node_type：

```text
table
physical_column
cte
cte_column
subquery
subquery_column
output
output_column
expression
unknown
query_result
```

---

## 5. GraphViewModel 最小边

```json
{
  "id": "edge:column:t.a->output:a",
  "source": "column:t.a",
  "target": "output:a",
  "edge_type": "column_lineage",
  "label": "lineage",
  "data": {
    "confidence": "high"
  }
}
```

要求：

1. `source` 必须指向已存在 node id。
2. `target` 必须指向已存在 node id。
3. 边不能悬空。
4. 不能为了前端好看伪造无证据的强血缘边。

---

## 6. diagnostics 最小结构

```json
{
  "diagnostic_id": "diag:001",
  "code": "UNKNOWN_COLUMN",
  "level": "warning",
  "message": "Column user_name cannot be resolved from known tables.",
  "suggestion": "Import metadata or check table alias."
}
```

推荐 level：

```text
info
warning
error
```

推荐 code：

```text
C01_PLACEHOLDER
SQL_PARSE_ERROR
UNKNOWN_COLUMN
AMBIGUOUS_COLUMN
UNSUPPORTED_SELECT_STAR
UNSUPPORTED_COMPLEX_QUERY
METADATA_MISSING
SOURCE_LOCATION_APPROXIMATE
```

---

## 7. stage_statuses 最小结构

```json
{
  "stage": "sql_parse",
  "status": "success",
  "elapsed_ms": 3,
  "diagnostic_codes": [],
  "message": "SQL parsed by SQLGlot."
}
```

推荐 stage：

```text
request
sql_parse
output_fields
single_table_lineage
join_alias_resolve
cte_subquery_rollup
metadata_lookup
source_location
expression_lineage
graph_build
contract_assemble
```

---

## 8. C01-C10 字段演进原则

| 轮次 | 可以新增/填充的字段 | 不应修改的字段 |
|---|---|---|
| C01 | 空 graph、placeholder diagnostics | status、graph_view_model 基本结构 |
| C02 | output_fields、parse diagnostics | graph node / edge 字段名 |
| C03 | nodes、edges | API 路径 |
| C04 | unknown diagnostics、alias 信息 | 前端交互状态不进后端 |
| C05 | view_mode=subquery_dependency | CTE 不伪装物理表 |
| C06 | metadata_context | Analyze 主契约不重写 |
| C07 | ambiguous / unknown | 不静默忽略错误 |
| C08 | source_locations | Monaco 使用 1-based line / column |
| C09 | semantics_report | 不把解释文字当血缘证据 |
| C10 | golden case snapshots | 不引入破坏性字段改名 |


---


# 04｜前端对接总规范

> 本文把前端从“最终大闭环”拆成每轮可观察的小效果。后端每做完一轮，前端必须有一个清晰反馈。

---

## 1. 前端永远通过相对路径访问后端

前端请求统一使用：

```text
/api/health
/api/sql/analyze
/api/metadata/...
```

不要在组件里硬编码：

```text
http://127.0.0.1:8000
```

由 Vite proxy 转发：

```text
/api → http://127.0.0.1:8000
```

---

## 2. 每轮前端可见效果

| 轮次 | 前端动作 | 预期效果 |
|---|---|---|
| C00 | 打开页面 | Health badge 显示后端在线 |
| C01 | 点击 Analyze | 进入 partial 状态，展示“Analyze endpoint available” |
| C02 | 输入简单 SQL 后 Analyze | 输出字段列表出现 |
| C03 | 输入 `select a from t` 后 Analyze | 画布出现字段血缘边 |
| C04 | 输入 Join SQL 后 Analyze | 多表字段来源正确，未知字段有 warning |
| C05 | 输入 CTE SQL 后 Analyze | 默认展示子查询 / CTE 结构依赖图 |
| C06 | 导入 metadata JSON | Preview / Commit 可见，字段注释可展示 |
| C07 | 输入 `select *` 或冲突字段 | 展示 unknown / ambiguous 诊断 |
| C08 | 点击字段节点后 Locate SQL | SQL 编辑器高亮对应位置 |
| C09 | 点击表达式字段 | 下方面板展示表达式依赖和口径解释 |
| C10 | 跑 Golden Case | 核心路径不回退 |

---

## 3. 前端不做的事

前端禁止：

```text
自己解析 SQL
自己推断字段来源
自己把输出字段和表字段硬连线
自己生成 CTE / 子查询依赖
自己把 unknown 字段改成成功字段
```

前端可以做：

```text
展示 nodes / edges
保存拖拽布局
折叠 / 展开节点
搜索后端返回的 output_fields 或 graph nodes
展示 diagnostics
触发 Locate SQL
```

---

## 4. 前端状态建议

```text
empty：还没有 SQL
ready：SQL 可分析
analyzing：正在请求 /api/sql/analyze
analyzed：后端返回 success 或 partial
failed：后端返回 failed 或请求异常
dirty：SQL 已修改，结果过期
```

状态流：

```text
empty → ready → analyzing → analyzed
analyzed + SQL changed → dirty → analyzing → analyzed
analyzing + error → failed
failed + SQL changed → ready
```

---

## 5. 前端图谱渲染原则

1. 使用后端 `graph_view_model.nodes` 和 `graph_view_model.edges`。
2. 渲染前检查每条边的 `source` / `target` 是否存在。
3. 对 unknown 节点使用特殊样式，但不要前端删除。
4. 默认不要展示过于复杂的字段全图；C05 后默认 `subquery_dependency`。
5. 选中、拖拽、折叠、缩放属于前端状态，不回写 AnalyzeResult。

---

## 6. 每轮前端验收方式

每轮至少手工验证：

```text
1. 页面无白屏
2. Console 无关键报错
3. Network 中接口路径正确
4. 接口响应被页面消费
5. 页面出现该轮规定的可见效果
```

不要只看后端 pytest 通过。这个项目是“后端能力 + 前端可视化”项目，必须看页面结果。
