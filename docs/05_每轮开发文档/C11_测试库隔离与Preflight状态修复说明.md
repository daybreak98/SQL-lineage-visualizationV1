# C11 测试库隔离与 Preflight 状态修复说明

## 本轮目标

修复两个高优先级问题：

1. 后端测试不能清空真实的 `data/metadata.db`。
2. complex SQL preflight 出现 error 时，API 不能继续返回 `success + high`。

## 修复路径

### 1. 测试元数据库隔离

修改 `backend/tests/conftest.py`：

- 将测试用 SQLite 路径固定到 `backend/.pytest_cache/metadata_test.db`。
- 在 pytest 收集测试模块前重定向 `app.db.sqlite.DB_PATH`，避免 FastAPI app import 时写入真实库。
- 每个测试前删除并重建测试库，保证测试之间互不污染。

这样运行 `pytest backend/tests` 时，只会重建测试库，不会删除用户在页面中导入的真实元数据。

### 2. Preflight error 状态降级

修改 `backend/app/complex_sql_guard/analyzer.py`：

- 收集 preflight 阶段是否存在 `Severity.ERROR`。
- 如果 SQL 后续能被 sqlglot 解析，但 preflight 已报告 blocking risk，则最终状态降为 `partial`。
- 同时补充 `LOW_CONFIDENCE_LINEAGE` 诊断，并将 parse/lineage 置信度压低。

这样超限 SQL 不会再显示为高置信成功结果。

## 回归测试

新增或补充测试：

- `backend/tests/test_metadata_repository.py`
  - 验证 pytest 使用 `metadata_test.db`，不是生产 `data/metadata.db`。
- `backend/tests/test_complex_sql_analyzer.py`
  - 验证 preflight error 会把成功 parse 降为 `partial`。
- `backend/tests/integration/test_analyze_api_complex_sql_guard.py`
  - 验证 `/api/sql/analyze` 不再返回 `high success`。

## 验证结果

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

结果：

```text
118 passed, 1 warning
```

