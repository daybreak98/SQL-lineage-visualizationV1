# 复杂 SQL 容错能力评审包

本压缩包用于评审本次“复杂 SQL 解析容错能力”后端改造，不包含与本任务无关的前端改动。

## 目录说明
- `docs/01_开发记录.md`
  详细开发过程、设计决策、改动范围、交付结果。
- `docs/02_API与诊断说明.md`
  `/api/sql/analyze` 的新增字段、兼容策略、diagnostics 说明。
- `docs/03_测试与GoldenCases说明.md`
  单元测试、API 回归、golden case 说明与执行结果。
- `docs/04_核心文件清单.md`
  本次评审建议重点阅读的代码文件列表。
- `artifacts/test_result.txt`
  后端执行 `pytest -q` 的测试结果快照。
- `source/`
  本次任务涉及的核心代码、测试和 golden cases 快照。

## 评审建议顺序
1. 先读 `docs/01_开发记录.md` 了解目标、边界和落地方式。
2. 再读 `docs/02_API与诊断说明.md` 核对后端契约是否满足要求。
3. 再看 `source/backend/app/complex_sql_guard/` 与 `source/backend/app/services/sql_parse_service.py`。
4. 最后结合 `docs/03_测试与GoldenCases说明.md` 和 `artifacts/test_result.txt` 复核回归结果。

## 本包聚焦范围
- Complex SQL Guard 前置防御链路
- shield / segment / parser fallback / diagnostics
- `/api/sql/analyze` 契约扩展与兼容
- 新增测试与 golden cases

