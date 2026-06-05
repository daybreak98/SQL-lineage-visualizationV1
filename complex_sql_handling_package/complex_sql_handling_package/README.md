# Complex SQL Handling Kit for SQL Lineage Workbench

> 目标：让现有 SQL 血缘项目在面对 1000 行级 Hive/Spark 生产 SQL 时，不因为复杂正则、模板变量、单双引号、lateral view/explode、UDF、超长 CTE 链路而整体崩溃。

本包是一个**复杂 SQL 处理增强包**，适合并入你当前的 `sqlglot + Python + SQLite + 前端血缘图谱` 项目。

## 交付内容

```text
complex_sql_handling_package/
├── docs/
│   ├── 01_complex_sql_architecture.md        # 复杂 SQL 处理总架构
│   ├── 02_development_plan.md                # 分阶段开发计划与验收标准
│   ├── 03_api_contract.md                    # API / 数据模型契约
│   ├── 04_golden_case_strategy.md            # Golden Case 与回归测试方案
│   └── 05_agent_implementation_prompt.md     # 给 opencode/agent 的实施提示词
├── src/complex_sql_guard/
│   ├── models.py                             # 核心数据模型
│   ├── preflight.py                          # SQL 预检
│   ├── shields.py                            # 字面量/注释/模板屏蔽
│   ├── segmenter.py                          # 顶层结构分段
│   ├── dialect.py                            # Hive/Spark 方言 profile
│   ├── parser_adapter.py                     # sqlglot 适配与 fallback
│   └── analyzer.py                           # ComplexSqlAnalyzer 编排器
├── golden_cases/                             # 样例复杂 SQL 用例
├── tests/                                    # Python unittest 测试
├── scripts/run_demo.py                       # 演示入口
└── pyproject.toml
```

## 快速运行

```bash
cd complex_sql_handling_package
python -m unittest discover -s tests -v
python scripts/run_demo.py
```

说明：

- 本包对 `sqlglot` 是**可选依赖**。如果环境未安装 sqlglot，`parser_adapter` 会返回 `SQLGLOT_NOT_INSTALLED` 诊断，并继续执行预处理、分段、partial 结果构建。
- 这不是完整字段血缘引擎，而是复杂 SQL 的**容错预处理、分段解析和降级诊断骨架**。它应该接到你现有的 `SqlParseService / ScopeResolver / NameResolver / LineageEngine` 之前。

## 推荐接入位置

```text
AnalyzeController
  ↓
ComplexSqlAnalyzer                 # 本包新增
  ├─ PreflightChecker
  ├─ DirtySqlPreprocessor
  ├─ SqlSegmenter
  └─ ParserAdapter
  ↓
ScopeResolver                      # 现有/下一步模块
  ↓
NameResolver
  ↓
LineageEngine
  ↓
GraphBuilder
```

## 核心原则

```text
1. original_sql 永远不改。
2. normalized_sql / analysis_sql 可用于解析，但必须保留 placeholder mapping。
3. 正则、JSONPath、URL、模板变量先屏蔽，再解析。
4. 1000 行 SQL 不追求一次 parse 全成功，要支持局部成功。
5. 失败结果必须结构化诊断，不允许只有 failed。
```
