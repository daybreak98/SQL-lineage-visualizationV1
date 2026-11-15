# 零依赖桌面打包设计（PyInstaller + pystray 托盘）

> 日期：2026-06-25
> 状态：已批准，待制定实现计划
> 方案：P3 — PyInstaller 单 exe + pystray 托盘退出

## 目标

把后端（FastAPI + sqlglot + SQLite）+ 前端静态产物打包成单个 Windows exe。用户双击 → 后台起服务 + 系统托盘出现图标，浏览器自动打开。右键托盘 → "打开浏览器" / "退出"。元数据走 MetadataDialog 上传（刚做的功能）落 exe 同目录 `./data/metadata.db` 持久化。不携带任何 data 文件，不影响开发流。

## 用户画像

数分 / 产品岗位。拿到 exe + 自己传 metadata.db 即可用，机器无需装 Python / Node。

## 用户流程

1. 用户收到 `sql-lineage.exe`，双击
2. 无控制台窗口弹出；系统托盘出现小图标
3. 几秒后默认浏览器自动打开 `http://127.0.0.1:8000`
4. 进 Metadata 弹窗 → 文件上传 Tab → 拖入 .db → 成功 → 数据落 `./data/metadata.db`
5. 用完：右键托盘 → "退出"；或再点"打开浏览器"找回页面
6. 下次双击 exe → 元数据仍在（exe 旁 `./data/metadata.db` 持久）

## 架构

```
sql-lineage.exe  (PyInstaller 单文件 onefile, --noconsole, ~100MB)
  ├─ 内嵌: Python 3.14 运行时
  ├─ 内嵌: backend/app/ 全部源码
  ├─ 内嵌: frontend/dist/ 作为 static 资源 (sys._MEIPASS/static)
  ├─ 内嵌: pystray (含 native .pyd) + 默认托盘图标
  └─ 双击启动
       │
       ▼
  launcher.py  (PyInstaller entrypoint)
   1. 算 exe 旁持久目录: exe_dir = Path(sys.executable).parent (frozen) / cwd (dev)
   2. (exe_dir / "data").mkdir(parents=True, exist_ok=True)
   3. os.environ["SQL_LINEAGE_DB"] = str(exe_dir / "data" / "metadata.db")
   4. 若该 db 不存在 → run_migrations() 建空库 (含3张表)
   5. 运行时挂载前端: from app.main import app; app.mount("/", StaticFiles(directory=_bundled_static_dir(), html=True))
   6. 启动 uvicorn 在子线程: uvicorn.run(app, host=127.0.0.1, port=8000, log_config=None)
   7. 启动托盘 in 主线程: pystray.Icon("sql-lineage", image, menu=Menu("打开浏览器","退出"))
   8. 托盘"退出" → icon.stop() → 主线程结束 → daemon 子线程的 uvicorn 随进程退出
   9. 启动瞬间 webbrowser.open("http://127.0.0.1:8000") 一次
```

## 改动清单（最小集，不影响开发流）

### 1. `backend/app/db/sqlite.py` — DB_PATH 支持环境变量（1 行）

现状：
```python
DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "metadata.db"
```
改为：
```python
DB_PATH = Path(os.environ.get("SQL_LINEAGE_DB", Path(__file__).parent.parent.parent.parent / "data" / "metadata.db"))
```
顶部加 `import os`。

**影响开发流?** 否。开发不设 `SQL_LINEAGE_DB` 环境变量，走原相对路径。exe 由 launcher 注入环境变量，走到 exe 旁。

### 2. `backend/launcher.py` — 新建（PyInstaller entrypoint）

职责：
- 判断 frozen（`getattr(sys, 'frozen', False)`）：取 `Path(sys.executable).parent`；否则取 cwd
- 建持久 `data/` 目录
- 设 `SQL_LINEAGE_DB` 环境变量
- 确保 db 存在（不存在则建空库）
- 导入 `app.main:app`，运行时挂 `StaticFiles` 到 `/`（用 `sys._MEIPASS/static` 当 dist 目录；不存在则 skip——开发时不挂）
- 子线程启动 `uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)`
- 启动后开一次浏览器
- 主线程跑 `pystray.Icon`，菜单：打开浏览器 / 退出
- `icon.stop()` → 主线程结束 → 进程退出（daemon 子线程随之）

错误处理：
- 启动异常写 `%TEMP%/sql-lineage-error.log`，弹 MessageBox（`ctypes.windll.user32.MessageBoxW`）提示用户，退出
- 端口占用 → 弹 MessageBox "8000 被占用，请检查并关闭" 后退出

### 3. `build.spec` — 新建（PyInstaller 配置）

- `scripts = ['launcher.py']`
- `datas = [('../frontend/dist', 'static')]`
- `hiddenimports = ['uvicorn.logging', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'app.main', 'pystray._backends', 'pystray._backends._win32']`
- `console = False`（--noconsole）
- `onefile = True`
- `name = 'sql-lineage'`

开发时不碰这个 spec，只打包时跑 `pyinstaller build.spec`。

## 不改动的内容

- `backend/app/main.py` — 完全不动，开发流时 routers 注册照旧
- `backend/app/middleware/`、`complex_sql_guard/`、`services/`、`api/` — 全不动
- `frontend/` 源码 — 不动，build 时用现有 `npm run build` 产 dist
- `backend/tests/` — 不动
- MetadataDialog 上传功能 — 不动，按现役 `DB_PATH` 工作，launcher 注入后自然指向 exe 旁

## 新增依赖

- `pyinstaller>=6.0` — 打包工具（dev-only，加入 requirements 或单独 build requirements）
- `pystray>=0.19` — 托盘（runtime，加入 requirements）
- `pillow>=10.0` — pystray 后端创建图标需要（虽然用最简图标，仍需 pillow 生成 Image 对象）

三个加到 `backend/requirements.txt`。

## 不打包的东西

PyInstaller `datas` 只含 `frontend/dist` → `static`。`a.binaries` 自动收集 `app/` + 依赖。
通过 `.spec` 不显式包含下列（也不在 `backend/app/` 内，PyInstaller 只跟踪 import 谁，不会被收）：
- `data/`、`metadata.db`、`metadata.db.bak`
- `backend/tests/`、`backend/debug_tree.py`
- `*_package/`、`docs/`、`review_packages/`、`c09_c10_design_core_code/`、`complex_sql_handling_package/`
- `.venv/`、`node_modules/`、`.codegraph/`、`.git/`
- 日志 `.codex-*`、`.run-*`、`backend-*`、`frontend-*`
- `frontend.7z`、`测试用例.7z`

## 错误处理

| 场景 | 行为 |
|---|---|
| 端口 8000 被占 | 弹 MessageBox → 退出（写错误日志） |
| data 目录无写权限 | 启动前 mkdir 失败 → 弹 MessageBox → 退出 |
| db 损坏（migrations 失败） | 写错误日志 + MessageBox 提示用户删 ./data 重试 → 退出 |
| 双击第二个实例 | 端口占用法被触发 → 上面的逻辑。可选增强：检测到已运行则只打开浏览器不起新进程（YAGNI 第一版不做） |
| PyInstaller 缺 hidden import | 启动报 ModuleNotFoundError → 写日志 + MessageBox |

## 限定

- 本 spec 仅覆盖 Windows（用户当前环境）。pystray 跨平台，但 PyInstaller 要分平台 build。macOS / Linux 需在对应 OS 跑 `pyinstaller build.spec`。
- 端口固定 8000（hard-coded，简化第一版）。若需可配置，扩展环境变量，YAGNI。
- 默认图标：用 pillow 画 16x16 实色方块（最简，无需 PNG 文件）。后续可替换为真实 .ico 加进 `datas`。

## 测试方式

后端单元测试受影响为零（`sqlite.py` 1 行 env 兜底，不传 env 走原路径，现有 196 测试全过）。
前端测试无影响。
新 launcher.py / build.spec 不写自动化测试（I/O 重，且是打包工具配置）。
**手动验证清单**：
1. `pyinstaller build.spec` 成功产出 `dist/sql-lineage.exe`
2. exe 拷到全新空目录双击 → 进程起、托盘出、浏览器开
3. 浏览器跑一遍 analyze + MetadataDialog 上传 metadata.db
4. 托盘右键"退出"→ 进程消失
5. 再双击 → 上传过的 metadata.db 仍在（持久）
6. exe 体积 / 启动时间记录

## 待确认 / 风险

- **pystray native 收集**：PyInstaller 通常自动收集 `pystray._backends._win32` 及其 `.pyd`。若 build 失败需手动加到 `binaries`。第一版试跑后再调。
- **PyInstaller 首次启动 3-5 秒**：onefile 模式解压到 `_MEIPASS` 临时目录。可接受。
- **防病毒误报**：PyInstaller 通病。若分发需代码签名，本版不做。