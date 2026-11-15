# Metadata DB 文件上传功能设计

> 日期：2026-06-25
> 状态：已批准，待制定实现计划
> 方案：B（临时文件 + 表结构校验 + 备份后替换）

## 目标

在现有 `MetadataDialog` 中新增"文件上传"Tab，让用户通过选择文件或拖拽上传一个 SQLite `.db` 文件，后端校验表结构后覆盖 `data/metadata.db`。一次上传后该电脑持久化，无需重复上传；每次上传覆盖之前的元数据库。

## 背景

- `MetadataDialog`（`frontend/src/components/MetadataDialog.tsx`）当前只有 JSON payload 导入（preview/commit 走 `/api/metadata/import/*`），需手工贴 JSON，对数分/产品岗位不友好。
- 元数据存储在 `data/metadata.db`（SQLite），路径由 `backend/app/db/sqlite.py:6` 硬编码为 `Path(__file__).parent.parent.parent.parent / "data" / "metadata.db"`。
- 后端 `metadata_controller.py` 有 4 个端点：import/preview、import/commit、tables、columns。新功能加第 5 个端点，不改动现有 4 个。

## 用户流程

1. 点击主页面 TopBar 的 Metadata 按钮 → 打开 MetadataDialog
2. Dialog 顶部出现 Tab 切换：「JSON 导入」（现有）/「文件上传」（新增）
3. 在「文件上传」Tab：
   - 点击「选择文件」按钮 → 系统文件选择器（accept=".db"）
   - 或将 .db 文件拖拽到虚线框区域
4. 选中文件后自动上传（或点「上传」按钮，见下方决策）
5. 上传中显示 loading；完成后显示结果（成功/失败 + 表/列数量）
6. 成功 → 触发 `onImported()` 刷新主页面的 `metadataStatus`
7. 失败 → 显示错误原因（如"不是有效的元数据库：缺少 table_metadata 表"）

## 架构

```
[MetadataDialog]
   ├─ Tab: "JSON 导入"（现有代码，不动）
   └─ Tab: "文件上传"（新增）
        ├─ <input type=file accept=".db"> 点击选择
        ├─ 拖拽区（dragover/drop 事件，虚线框样式）
        └─ uploadMetadataDb(file) ──POST multipart/form-data──▶ 后端
                                                                    │
                ┌───────────────────────────────────────────────────┘
                ▼
  POST /api/metadata/upload-db (UploadFile)
   1. 保存 UploadFile 到临时文件（tempfile.NamedTemporaryFile, delete=False）
   2. sqlite3 打开临时文件，校验有 table_metadata、column_metadata、metadata_imports 三张表
   3. 校验失败 → 删临时文件 → 返回 400 + {status:"failed", message}
   4. 校验通过 → 备份旧 data/metadata.db → data/metadata.db.bak（若存在）
   5. shutil.move 临时文件 → 覆盖 data/metadata.db
   6. 返回 200 + {status:"success", table_count, column_count}
                │
                ▼
  前端 onImported() 刷新主页 metadataStatus
```

## 改动清单

### 1. `backend/app/api/metadata_controller.py` — 新增端点（增量）

在现有 4 个端点后追加 `POST /metadata/upload-db`：
- 接收 `UploadFile`（FastAPI `File(...)`）
- 保存到临时文件
- 用 `sqlite3` 打开临时文件，查询 `sqlite_master` 确认三张表存在
- 校验通过：备份旧 db（若存在）→ `shutil.move` 覆盖
- 校验失败：删临时文件 → 返回 400
- 返回 Pydantic 模型 `MetadataUploadResponse`（新增到 `models.py` 或直接在此文件定义 dataclass）

新增 import：`import shutil`、`import sqlite3`、`import tempfile`、`from pathlib import Path`、`from fastapi import File, UploadFile, HTTPException`、`from app.db.sqlite import DB_PATH`。

校验的表名：`table_metadata`、`column_metadata`、`metadata_imports`（与 `db/sqlite.py` migrations 一致）。

### 2. `backend/app/middleware/local_delivery.py` — 豁免 upload-db 路径（增量）

`MAX_REQUEST_BODY_BYTES = 2 * 1024 * 1024`（2MB）对 .db 文件不够。在 `dispatch` 方法中，对 `request.url.path == "/api/metadata/upload-db"` 跳过 body size 检查（或单独放宽到 50MB）。

只改 1 处条件判断，不动其他逻辑。

### 3. `frontend/src/api/client.ts` — 新增 `uploadMetadataDb`（增量）

```ts
export function uploadMetadataDb(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request<MetadataUploadResponse>('/api/metadata/upload-db', {
    method: 'POST',
    body: formData,
  });
}
```

新增 import 类型 `MetadataUploadResponse`（加到 `types/lineage.ts`）。不动现有函数。

### 4. `frontend/src/types/lineage.ts` — 新增类型（增量）

```ts
export interface MetadataUploadResponse {
  status: 'success' | 'failed';
  message?: string;
  table_count?: number;
  column_count?: number;
}
```

### 5. `frontend/src/components/MetadataDialog.tsx` — 加 Tab + 文件上传（增量）

- 新增 state：`tab: 'json' | 'file'`、`uploadStatus`、`uploadError`、`dragOver`
- Tab 切换 UI（两个按钮，active 高亮）
- 「文件上传」Tab 内容：
  - 拖拽区 div：`onDragOver`、`onDragLeave`、`onDrop` 处理
  - 隐藏 `<input type="file" accept=".db">` + 「选择文件」按钮触发 click
  - 上传中 loading、成功/失败结果显示
- 选中文件后立即上传（无需额外「上传」按钮，减少操作步骤）
- 成功 → 调 `onImported()` + `refreshMetadata()`
- 现有 JSON 导入代码全部保留，只在条件渲染中按 `tab` 切换

## 不改动的内容

- `backend/app/db/sqlite.py` — DB_PATH 不动，覆盖文件即持久化
- `backend/app/services/metadata_import_service.py` — JSON 导入逻辑独立，不合并
- 现有 4 个 metadata 端点
- MetadataDialog 现有 JSON payload 区域代码
- 任何其他组件、任何其他后端服务

## 错误处理

| 场景 | 行为 |
|---|---|
| 前端选了非 .db 文件 | `<input accept=".db">` 过滤 + 后端表结构校验拒绝 |
| 上传的 db 缺表 | 后端 400 + `{status:"failed", message:"不是有效的元数据库：缺少 X 表"}` |
| 上传的文件不是 sqlite | sqlite3 打开抛异常 → 捕获 → 400 + 错误信息 |
| 文件过大 | middleware 豁免后无硬限制，sqlite 校验兜底（非 sqlite 会立即失败） |
| 覆盖时旧 db 被锁 | 单机 loopback 并发=1，风险极低；若发生，临时文件已删，旧 db 保留 |
| 覆盖失败 | 旧 db 仍在（.bak 保险），返回 500 |

## 持久化

覆盖 `data/metadata.db` 后，文件落在项目根 `data/` 目录。后端重启时 `run_migrations` 会补缺失的表（空 db 也能用），但上传场景校验已确保 db 有数据。"一次上传后该电脑不需要再传"由文件系统持久化自动满足，无需额外存储上传记录。

## 测试要点

- 上传合法的 `data/metadata.db` 副本 → 成功，主页 metadataStatus 刷新
- 上传一个空 sqlite 文件 → 失败，提示缺表
- 上传一个 txt 文件（改名为 .db）→ 失败，提示非有效 sqlite
- 拖拽 .db 文件到拖拽区 → 触发上传
- Tab 切换不丢失各自状态
- 现有 JSON 导入功能不受影响

## 依现有模式

- 后端端点风格：FastAPI router + Pydantic 响应模型，与 `metadata_controller.py` 现有端点一致
- 前端 API 函数风格：`request<T>` 封装，与 `client.ts` 现有函数一致
- 前端组件风格：React hooks + className，与 `MetadataDialog.tsx` 现有代码一致
- 不引入新依赖（FormData/File API 浏览器原生，UploadFile FastAPI 内置）
