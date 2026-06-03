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
