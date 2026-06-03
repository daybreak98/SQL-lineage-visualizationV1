# C06｜元数据 JSON 导入 SQLite 与字段补全

## 1. 本轮目标

引入 SQLite 元数据，让后端能知道表有哪些字段、字段类型和注释。

```text
后端能力：metadata preview / commit / query
前端效果：Metadata 导入按钮可用，字段 hover / detail 能看到注释
学习重点：SQLite、Repository、元数据不是血缘本身，而是补全依据
```

---

## 2. API

```http
POST /api/metadata/import/preview
POST /api/metadata/import/commit
GET  /api/metadata/tables
GET  /api/metadata/columns?table_name=xxx
```

---

## 3. 元数据 JSON 格式

```json
{
  "metadata_version": "local-demo-001",
  "tables": [
    {
      "catalog": "default",
      "schema": "default",
      "table_name": "dwd_order_di",
      "comment": "订单明细表",
      "columns": [
        { "name": "order_no", "data_type": "string", "comment": "订单号" },
        { "name": "user_id", "data_type": "string", "comment": "用户ID" },
        { "name": "order_amount", "data_type": "double", "comment": "订单金额" }
      ]
    }
  ]
}
```

---

## 4. 允许创建

```text
backend/app/db/sqlite.py
backend/app/db/migrations/001_metadata.sql
backend/app/domain/metadata_model.py
backend/app/repositories/metadata_repository.py
backend/app/services/metadata_import_service.py
backend/app/api/metadata_controller.py
backend/tests/test_metadata_repository.py
backend/tests/integration/test_metadata_api_c06.py
```

---

## 5. Analyze 如何使用元数据

C06 后，Analyze 可以利用元数据：

```text
1. 判断未限定字段属于哪张表
2. 展开 select *
3. 补充字段注释
4. 标记 metadata_context
```

但本轮不强制完成 select *，select * 放到 C07。

---

## 6. 前端对接文档

前端效果：

```text
1. Metadata Preview 显示将导入多少张表、多少字段
2. Commit 成功后显示 metadata_version
3. 表/字段查询接口可返回字段注释
4. Analyze 结果中的节点 data 可展示 comment / data_type
```

---

## 7. 测试验收

```text
preview 不写库
commit 写入 SQLite
重复 commit 同版本不产生脏数据
GET tables 能查到 dwd_order_di
GET columns 能查到 order_no / user_id / order_amount
Analyze 可在 metadata_context 中返回 metadata_version
```

---

## 8. 禁止越界

不要把元数据导入和血缘解析强耦合。元数据服务应该可单独测试。

---

## 9. 给 OpenCode 的单轮提示词

```text
请只实现 C06：元数据 JSON 导入 SQLite 与查询接口。
实现 preview、commit、tables、columns 四类接口。
元数据服务必须独立于 SQL 解析服务，可单测。
Analyze 可以开始读取 metadata_context，但不要在本轮强制完成 select * 展开。
前端验收是 Metadata Preview / Commit 可见，字段注释能被查询。
```
