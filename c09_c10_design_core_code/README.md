# C09-C10 设计方案与核心代码参考包

本压缩包用于给 opencode / OpenCode / Codex 参考实现 C09-C10。它不是直接覆盖当前项目的完整补丁，而是按当前文档给出：

1. C09 表达式依赖与口径详情面板设计方案。
2. C10 Golden Case 回归冻结设计方案。
3. 后端核心代码参考：表达式分析器、GraphBuilder 补丁思路、Golden Case 测试框架。
4. 前端核心代码参考：AnalysisResult 类型、DetailPanel 展示逻辑、graphPipeline 映射建议。
5. 可直接复制给 opencode 的开发提示词。

## 使用方式

建议把本包解压到项目外部，作为开发参考，不要直接整包复制覆盖当前工程。

推荐执行顺序：

```text
1. 先阅读 docs/C09_设计方案.md
2. 再参考 backend/app/services/expression_analyzer.py 新增表达式分析能力
3. 按 backend/app/services/graph_builder_c09_patch.py 的思路合并到现有 graph_builder.py
4. 更新后端响应模型，补充 semantics_report.metrics
5. 更新前端类型和 DetailPanel
6. 按 docs/C10_设计方案.md 建立 golden_cases 与 pytest 测试
7. 运行后端 pytest 和前端测试
```

## 交付范围

```text
c09_c10_design_core_code/
├── docs/
├── backend/
│   ├── app/models/
│   ├── app/services/
│   └── tests/
├── frontend/
│   └── src/
├── golden_cases/
├── scripts/
└── opencode_prompt.md
```

## 核心边界

C09 只做基于 SQL 结构的确定性解释，不接 AI，不生成脱离 SQL 证据的自然语言解释。
C10 只冻结 C00-C09 的核心能力，不在 C10 扩展新解析特性。
