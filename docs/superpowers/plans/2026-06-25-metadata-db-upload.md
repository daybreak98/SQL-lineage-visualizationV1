# Metadata DB 文件上传 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MetadataDialog 加 Tab，让用户选择或拖拽上传 .db 文件覆盖 `data/metadata.db`，后端校验表结构后备份替换。

**Architecture:** 新增一个 multipart 端点 `POST /api/metadata/upload-db`，收文件→临时文件→sqlite 校验三张元数据表→备份旧 db→覆盖。前端在 MetadataDialog 加 Tab 切换，复用现有 `request<T>` 封装和 `onImported` 回调。

**Tech Stack:** FastAPI UploadFile · sqlite3 · shutil · React + TypeScript + FormData

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/app/api/metadata_controller.py` | 修改 | 新增 `POST /metadata/upload-db` 端点（追加，不动现有 4 个） |
| `backend/app/middleware/local_delivery.py` | 修改 | upload-db 路径豁免 2MB body 限制（改 1 处条件） |
| `backend/tests/integration/test_metadata_upload_api.py` | 新建 | 上传端点集成测试 |
| `frontend/src/types/lineage.ts` | 修改 | 追加 `MetadataUploadResponse` 类型 |
| `frontend/src/api/client.ts` | 修改 | 追加 `uploadMetadataDb` 函数 |
| `frontend/src/components/MetadataDialog.tsx` | 修改 | 加 Tab state + 文件上传 Tab UI |

---

### Task 1: 后端上传端点 — 临时文件 + 校验 + 备份替换

**Files:**
- Modify: `backend/app/api/metadata_controller.py`
- Test: `backend/tests/integration/test_metadata_upload_api.py`

- [ ] **Step 1: 写失败测试 — 合法 db 上传成功**

新建 `backend/tests/integration/test_metadata_upload_api.py`：

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.sqlite import DB_PATH

client = TestClient(app)


def _make_valid_metadata_db(tmp_path: Path) -> Path:
    """Create a sqlite db with the 3 required tables + sample data."""
    db_path = tmp_path / "valid.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE metadata_imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metadata_version TEXT NOT NULL,
            source_name TEXT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            table_count INTEGER DEFAULT 0,
            column_count INTEGER DEFAULT 0
        );
        CREATE TABLE table_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            catalog TEXT DEFAULT 'default',
            schema_name TEXT DEFAULT 'default',
            table_name TEXT NOT NULL,
            comment TEXT,
            table_type TEXT DEFAULT 'table',
            import_id INTEGER,
            UNIQUE(catalog, schema_name, table_name)
        );
        CREATE TABLE column_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            data_type TEXT,
            comment TEXT,
            ordinal INTEGER,
            is_partition BOOLEAN DEFAULT 0,
            nullable BOOLEAN DEFAULT 1,
            UNIQUE(table_id, name)
        );
        INSERT INTO metadata_imports (metadata_version, table_count, column_count)
            VALUES ('upload-test', 1, 2);
        INSERT INTO table_metadata (id, catalog, schema_name, table_name, comment, import_id)
            VALUES (1, 'default', 'default', 'upload_table', 'from upload', 1);
        INSERT INTO column_metadata (table_id, name, data_type, comment, ordinal)
            VALUES (1, 'col_a', 'string', 'a', 1), (1, 'col_b', 'int', 'b', 2);
    """)
    conn.commit()
    conn.close()
    return db_path


def test_upload_valid_db_returns_success(tmp_path, monkeypatch):
    # Redirect DB_PATH to tmp_path so we don't clobber the real metadata.db
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)

    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("valid.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["table_count"] == 1
    assert data["column_count"] == 2
    assert real_db.exists()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_valid_db_returns_success -v`
Expected: FAIL with 404 (endpoint not found) 或类似

- [ ] **Step 3: 实现端点**

在 `backend/app/api/metadata_controller.py` 顶部追加 import，在文件末尾追加端点：

顶部 import 区追加（保持现有 import 不动，在最后追加）：
```python
import shutil
import sqlite3
import tempfile
from pathlib import Path

from fastapi import File, UploadFile
from pydantic import BaseModel

from app.db.sqlite import DB_PATH
```

文件末尾追加：
```python
class MetadataUploadResponse(BaseModel):
    status: str  # success | failed
    message: str | None = None
    table_count: int = 0
    column_count: int = 0


_REQUIRED_TABLES = {"table_metadata", "column_metadata", "metadata_imports"}


def _validate_metadata_db(db_path: Path) -> tuple[bool, str, int, int]:
    """Open db, check required tables exist. Returns (ok, message, table_count, column_count)."""
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.DatabaseError as exc:
        return False, f"Not a valid SQLite file: {exc}", 0, 0
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row[0] for row in rows}
        missing = _REQUIRED_TABLES - table_names
        if missing:
            return False, f"Missing required tables: {', '.join(sorted(missing))}", 0, 0
        table_count = conn.execute("SELECT COUNT(*) FROM table_metadata").fetchone()[0]
        column_count = conn.execute("SELECT COUNT(*) FROM column_metadata").fetchone()[0]
        return True, "ok", table_count, column_count
    finally:
        conn.close()


@router.post("/metadata/upload-db", response_model=MetadataUploadResponse)
async def upload_metadata_db(file: UploadFile = File(...)) -> MetadataUploadResponse:
    tmp_path = Path(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name)
    try:
        with open(tmp_path, "wb") as out:
            shutil.copyfileobj(file.file, out)

        ok, message, table_count, column_count = _validate_metadata_db(tmp_path)
        if not ok:
            return MetadataUploadResponse(status="failed", message=message)

        # Backup old db if it exists, then replace
        if DB_PATH.exists():
            backup = DB_PATH.with_suffix(".db.bak")
            shutil.move(str(DB_PATH), str(backup))
        shutil.move(str(tmp_path), str(DB_PATH))

        return MetadataUploadResponse(
            status="success",
            message="Metadata database replaced.",
            table_count=table_count,
            column_count=column_count,
        )
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_valid_db_returns_success -v`
Expected: PASS

- [ ] **Step 5: 写失败测试 — 非 sqlite 文件被拒绝**

在 `test_metadata_upload_api.py` 追加：

```python
def test_upload_non_sqlite_file_returns_failed(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    bad_file = tmp_path / "fake.db"
    bad_file.write_text("this is not a sqlite file")

    with open(bad_file, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("fake.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "valid SQLite" in data["message"] or "file is not a database" in data["message"]
    assert not real_db.exists()
```

- [ ] **Step 6: 运行测试确认通过**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_non_sqlite_file_returns_failed -v`
Expected: PASS

- [ ] **Step 7: 写失败测试 — 缺表的 db 被拒绝**

在 `test_metadata_upload_api.py` 追加：

```python
def test_upload_db_missing_tables_returns_failed(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    incomplete_db = tmp_path / "incomplete.db"
    conn = sqlite3.connect(str(incomplete_db))
    conn.execute("CREATE TABLE unrelated (id INTEGER)")
    conn.commit()
    conn.close()

    with open(incomplete_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("incomplete.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "table_metadata" in data["message"]
    assert not real_db.exists()
```

- [ ] **Step 8: 运行测试确认通过**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_db_missing_tables_returns_failed -v`
Expected: PASS

- [ ] **Step 9: 写失败测试 — 成功上传后旧 db 被备份**

在 `test_metadata_upload_api.py` 追加：

```python
def test_upload_backs_up_old_db(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    # Pre-create an "old" db so we can verify backup
    old_conn = sqlite3.connect(str(real_db))
    old_conn.execute("CREATE TABLE table_metadata (id INTEGER)")
    old_conn.execute("CREATE TABLE column_metadata (id INTEGER)")
    old_conn.execute("CREATE TABLE metadata_imports (id INTEGER)")
    old_conn.execute("INSERT INTO table_metadata VALUES (99)")
    old_conn.commit()
    old_conn.close()

    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)
    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("valid.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    backup = real_db.with_suffix(".db.bak")
    assert backup.exists()
    # Backup should contain the old row
    bak_conn = sqlite3.connect(str(backup))
    rows = bak_conn.execute("SELECT id FROM table_metadata").fetchall()
    bak_conn.close()
    assert (99,) in rows
```

- [ ] **Step 10: 运行测试确认通过**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_backs_up_old_db -v`
Expected: PASS

- [ ] **Step 11: 跑全部上传测试**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py -v`
Expected: 4 PASS

- [ ] **Step 12: Commit**

```bash
git add backend/app/api/metadata_controller.py backend/tests/integration/test_metadata_upload_api.py
git commit -m "feat: add POST /api/metadata/upload-db endpoint with schema validation and backup"
```

---

### Task 2: 中间件豁免 upload-db 路径的 body 限制

**Files:**
- Modify: `backend/app/middleware/local_delivery.py:54-60`
- Test: `backend/tests/integration/test_metadata_upload_api.py`

- [ ] **Step 1: 写失败测试 — 大于 2MB 的 db 文件能上传**

在 `test_metadata_upload_api.py` 追加：

```python
def test_upload_large_db_not_rejected_by_body_limit(tmp_path, monkeypatch):
    real_db = tmp_path / "metadata.db"
    monkeypatch.setattr("app.db.sqlite.DB_PATH", real_db)
    monkeypatch.setattr("app.api.metadata_controller.DB_PATH", real_db)

    valid_db = _make_valid_metadata_db(tmp_path)
    # Pad the db file to > 2MB to exceed MAX_REQUEST_BODY_BYTES
    with open(valid_db, "ab") as f:
        f.write(b"\0" * (3 * 1024 * 1024))

    with open(valid_db, "rb") as f:
        resp = client.post(
            "/api/metadata/upload-db",
            files={"file": ("big.db", f, "application/octet-stream")},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "success"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_large_db_not_rejected_by_body_limit -v`
Expected: FAIL with 413 (Request body too large)

- [ ] **Step 3: 修改中间件豁免 upload-db**

在 `backend/app/middleware/local_delivery.py` 的 `dispatch` 方法中，把 body size 检查改为跳过 upload-db 路径。

把这段：
```python
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_request_body_bytes:
                    return JSONResponse({"detail": "Request body too large"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
```

改成：
```python
        if request.url.path != "/api/metadata/upload-db":
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > self.max_request_body_bytes:
                        return JSONResponse({"detail": "Request body too large"}, status_code=413)
                except ValueError:
                    return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest backend/tests/integration/test_metadata_upload_api.py::test_upload_large_db_not_rejected_by_body_limit -v`
Expected: PASS

- [ ] **Step 5: 跑现有中间件测试确保没回归**

Run: `pytest backend/tests/test_local_delivery_guards.py -v`
Expected: 所有现有测试 PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/middleware/local_delivery.py backend/tests/integration/test_metadata_upload_api.py
git commit -m "feat: exempt /api/metadata/upload-db from body size limit"
```

---

### Task 3: 前端类型 + API 函数

**Files:**
- Modify: `frontend/src/types/lineage.ts`
- Modify: `frontend/src/api/client.ts`
- Test: `frontend/src/api/__tests__/client.test.ts`

- [ ] **Step 1: 写失败测试 — uploadMetadataDb 发 multipart 请求**

先读现有 `frontend/src/api/__tests__/client.test.ts` 了解测试模式，然后追加测试。

在 `frontend/src/api/__tests__/client.test.ts` 末尾追加：

```typescript
import { uploadMetadataDb } from '../client';

describe('uploadMetadataDb', () => {
  it('posts multipart form data to /api/metadata/upload-db', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'success', table_count: 1, column_count: 2 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    const file = new File(['dummy'], 'test.db', { type: 'application/octet-stream' });
    const result = await uploadMetadataDb(file);

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/api/metadata/upload-db');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBeInstanceOf(FormData);
    const formData = init?.body as FormData;
    expect(formData.get('file')).toBe(file);
    expect(result.status).toBe('success');
    expect(result.table_count).toBe(1);
    fetchSpy.mockRestore();
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/api/__tests__/client.test.ts`
Expected: FAIL — `uploadMetadataDb` 未导出或类型缺失

- [ ] **Step 3: 加类型定义**

在 `frontend/src/types/lineage.ts` 末尾追加：

```typescript
export interface MetadataUploadResponse {
  status: 'success' | 'failed';
  message?: string;
  table_count?: number;
  column_count?: number;
}
```

- [ ] **Step 4: 加 API 函数**

在 `frontend/src/api/client.ts` 顶部 import 行追加 `MetadataUploadResponse`，然后在文件末尾追加：

顶部 import 改为（把 `MetadataUploadResponse` 加入现有 import）：
```typescript
import type { BackendAnalysisResult, ConvertSqlResponse, FormatSqlResponse, MetadataImportResult, MetadataListResponse, MetadataPayload, MetadataUploadResponse } from '../types/lineage';
```

末尾追加：
```typescript
export function uploadMetadataDb(file: File) {
  const formData = new FormData();
  formData.append('file', file);
  return request<MetadataUploadResponse>('/api/metadata/upload-db', {
    method: 'POST',
    body: formData,
  });
}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/api/__tests__/client.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/lineage.ts frontend/src/api/client.ts frontend/src/api/__tests__/client.test.ts
git commit -m "feat: add uploadMetadataDb api function and MetadataUploadResponse type"
```

---

### Task 4: MetadataDialog Tab + 文件上传 UI

**Files:**
- Modify: `frontend/src/components/MetadataDialog.tsx`

- [ ] **Step 1: 读现有 MetadataDialog 与 CSS 确认样式模式**

读 `frontend/src/components/MetadataDialog.tsx`（已在上下文中）和 `frontend/src/styles/index.css` 中 `.metadata-*` 与 `.btn`/`.btn-primary` 相关样式，确认 Tab 和拖拽区要复用的 className。

- [ ] **Step 2: 加 Tab state 与文件上传 state**

在 `MetadataDialog` 函数组件的现有 state 声明后（`const [error, setError] = useState('');` 之后）追加：

```typescript
  const [tab, setTab] = useState<'json' | 'file'>('json');
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<MetadataUploadResponse | null>(null);
  const [uploadError, setUploadError] = useState('');
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
```

同时在顶部 import 区追加：
```typescript
import { useRef } from 'react';
import { uploadMetadataDb } from '../api/client';
import type { MetadataUploadResponse } from '../types/lineage';
```

（注意：现有 import 第一行是 `import { useEffect, useMemo, useState } from 'react';`，把 `useRef` 加进去变成 `import { useEffect, useMemo, useRef, useState } from 'react';`）

- [ ] **Step 3: 加文件上传处理函数**

在 `runCommit` 函数之后追加：

```typescript
  async function handleFileUpload(file: File) {
    setUploadLoading(true);
    setUploadError('');
    setUploadResult(null);
    try {
      const result = await uploadMetadataDb(file);
      setUploadResult(result);
      if (result.status === 'success') {
        await refreshMetadata();
        onImported();
      }
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploadLoading(false);
    }
  }
```

- [ ] **Step 4: 加 Tab 切换 UI**

把现有 `<div className="metadata-grid">` 这一整块（从 `<div className="metadata-grid">` 到对应的 `</div>` 即 footer 之前的 grid 区）用条件渲染包裹。

在 `<div className="metadata-grid">` 之前插入 Tab 切换 UI：

```tsx
        <div className="metadata-tabs">
          <button
            className={cx('btn', tab === 'json' && 'active')}
            onClick={() => setTab('json')}
          >
            JSON 导入
          </button>
          <button
            className={cx('btn', tab === 'file' && 'active')}
            onClick={() => setTab('file')}
          >
            文件上传
          </button>
        </div>
```

然后把现有 `<div className="metadata-grid">` ... `</div>`（JSON 区域）改为：
```tsx
        {tab === 'json' && (
          <div className="metadata-grid">
            {/* 现有 JSON 导入代码全部保留，不动 */}
          </div>
        )}
```

- [ ] **Step 5: 加文件上传 Tab 内容**

在 JSON 区域条件块之后追加：

```tsx
        {tab === 'file' && (
          <div className="metadata-grid">
            <div className="metadata-pane">
              <div className="pane-title">上传元数据库文件</div>
              <div
                className={cx('metadata-dropzone', dragOver && 'drag-over')}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  const file = e.dataTransfer.files[0];
                  if (file) void handleFileUpload(file);
                }}
              >
                <div className="metadata-dropzone-hint">
                  将 .db 文件拖拽到此处，或
                </div>
                <button
                  className="btn"
                  onClick={() => fileInputRef.current?.click()}
                >
                  选择文件
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".db"
                  style={{ display: 'none' }}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) void handleFileUpload(file);
                  }}
                />
              </div>
              {uploadLoading && <div className="card">Uploading...</div>}
              {uploadError && (
                <div className="card diag error">
                  <div className="card-title">Upload failed</div>
                  {uploadError}
                </div>
              )}
              {uploadResult && (
                <div className="metadata-result">
                  <div className={cx('pill', uploadResult.status === 'success' ? 'trusted' : 'failed')}>
                    {uploadResult.status}
                  </div>
                  {uploadResult.message && <div className="card">{uploadResult.message}</div>}
                  {uploadResult.status === 'success' && (
                    <div className="card">
                      Tables: {uploadResult.table_count ?? 0} · Columns: {uploadResult.column_count ?? 0}
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="metadata-pane">
              <div className="pane-title">说明</div>
              <div className="card">
                上传一个 SQLite 元数据库文件（.db），将覆盖当前元数据。
                每次上传都会替换之前的数据库，旧文件会备份为 metadata.db.bak。
                一次上传后本机无需重复上传。
              </div>
            </div>
          </div>
        )}
```

- [ ] **Step 6: 加 CSS 样式（Tab + 拖拽区）**

在 `frontend/src/styles/index.css` 末尾追加：

```css
.metadata-tabs {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}
.metadata-tabs .btn.active {
  background: var(--accent, #2563eb);
  color: white;
}
.metadata-dropzone {
  border: 2px dashed var(--border, #d1d5db);
  border-radius: 8px;
  padding: 32px 16px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.metadata-dropzone.drag-over {
  border-color: var(--accent, #2563eb);
  background: rgba(37, 99, 235, 0.05);
}
.metadata-dropzone-hint {
  color: var(--muted, #6b7280);
  font-size: 13px;
}
```

- [ ] **Step 7: 运行现有 MetadataDialog 测试确认没回归**

Run: `cd frontend && npx vitest run src/components/__tests__/`
Expected: 所有现有测试 PASS（Tab 默认 'json'，现有 JSON 流程不变）

- [ ] **Step 8: 手动验证**

启动前后端，打开 MetadataDialog：
1. 看到 Tab「JSON 导入」/「文件上传」
2. 默认在 JSON Tab，现有功能正常
3. 切到文件上传 Tab，看到拖拽区和选择文件按钮
4. 选一个合法 .db → 显示 success + 表/列数 → 主页 metadataStatus 刷新
5. 选一个假 .db → 显示 failed + 错误信息
6. 拖拽 .db 到拖拽区 → 触发上传

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/MetadataDialog.tsx frontend/src/styles/index.css
git commit -m "feat: add file upload tab to MetadataDialog with drag-drop and click selection"
```

---

### Task 5: 全量回归验证

- [ ] **Step 1: 跑后端全部测试**

Run: `cd backend && python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 2: 跑前端全部测试**

Run: `cd frontend && npx vitest run`
Expected: 全部 PASS

- [ ] **Step 3: 跑前端 typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: 手动端到端验证**

启动后端 (`uvicorn app.main:app`) + 前端 (`npm run dev`)：
1. 打开页面，点 Metadata → dialog 出现 Tab
2. JSON Tab 现有功能正常（preview/commit/list）
3. 文件上传 Tab：选择合法 db → 成功 → 关闭 dialog → 主页 metadata 状态刷新
4. 文件上传 Tab：拖拽合法 db → 成功
5. 文件上传 Tab：上传假 db → 失败显示错误
6. Tab 切换不丢失各自状态
7. 重新打开 dialog → 上传过的 db 仍在生效（`data/metadata.db` 已替换）

---

## Self-Review

**Spec coverage:**
- ✅ Tab 切换两种方式 → Task 4 Step 4
- ✅ 点击选择文件 → Task 4 Step 5 (input + button)
- ✅ 拖拽上传 → Task 4 Step 5 (dropzone)
- ✅ 后端校验表结构 → Task 1 Step 3 (`_validate_metadata_db`)
- ✅ 备份旧 db → Task 1 Step 3 (`shutil.move` to .bak)
- ✅ 覆盖替换 → Task 1 Step 3
- ✅ 中间件豁免 body 限制 → Task 2
- ✅ 持久化（一次上传本机无需再传）→ 覆盖 data/metadata.db 自动满足
- ✅ 错误处理（非 sqlite / 缺表 / 覆盖失败）→ Task 1 测试覆盖
- ✅ 不改动现有代码 → 所有改动均为追加

**Placeholder scan:** 无 TBD/TODO，所有步骤含完整代码。

**Type consistency:** `MetadataUploadResponse`（status/message/table_count/column_count）在 Task 1 后端、Task 3 前端类型、Task 4 组件中一致。`uploadMetadataDb` 在 Task 3 定义、Task 4 调用。`_REQUIRED_TABLES` 与 `001_metadata.sql` 的三张表名一致。
