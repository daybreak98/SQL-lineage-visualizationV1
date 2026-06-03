# C00｜环境启动与 FastAPI 健康检查

## 1. 本轮目标

让后端最小可运行，并让前端能知道后端在线。

```text
后端能力：GET /api/health
前端效果：Health badge 显示 ok / online
学习重点：Python 包结构、FastAPI app、路由注册、pytest 最小接口测试
```

---

## 2. 本轮只允许做什么

允许创建：

```text
backend/app/__init__.py
backend/app/main.py
backend/app/api/__init__.py
backend/app/api/health_controller.py
backend/tests/test_health.py
```

不允许做：

```text
/api/sql/analyze
SQLGlot
GraphViewModel
SQLite
元数据导入
前端大改版
```

---

## 3. API 契约

请求：

```http
GET /api/health
```

响应：

```json
{
  "status": "ok",
  "service": "sql-lineage-workbench-backend",
  "version": "0.3.0-c00"
}
```

---

## 4. 后端实现提示

`main.py` 只做应用创建和路由注册：

```text
创建 FastAPI app
开启 CORS
include_router(health_router)
```

`health_controller.py` 只做健康检查，不写业务逻辑。

---

## 5. 前端对接文档

前端启动后应调用：

```text
GET /api/health
```

页面效果：

```text
Health badge / 顶部状态显示：Backend: ok
```

如果请求失败：

```text
显示 Backend: offline
不要让页面白屏
```

---

## 6. 测试验收

pytest 验收：

```text
GET /api/health 返回 200
status == ok
service 字段存在
version 字段存在
```

手工验收：

```bash
curl http://127.0.0.1:8000/api/health
```

前端验收：

```text
打开 http://localhost:5173
顶部后端状态不再是 unknown / offline
```

---

## 7. 给 OpenCode 的单轮提示词

```text
请只实现 C00：FastAPI 最小健康检查。
读取本文档后，只允许创建或修改 backend/app/main.py、backend/app/api/health_controller.py、backend/app/__init__.py、backend/app/api/__init__.py、backend/tests/test_health.py。
不要实现 /api/sql/analyze，不要引入 SQLGlot，不要创建业务 service。
实现后运行 pytest backend/tests/test_health.py，并说明前端如何验证 Health badge。
```
