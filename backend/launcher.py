from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
import threading
import webbrowser
from pathlib import Path

_PORT = 8000

# ── Windows tray icon via ctypes (zero external dependencies) ──

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32

WM_TRAY = 0x0400 + 1
WM_COMMAND = 0x0111
ID_OPEN = 1001
ID_QUIT = 1002
NIM_ADD = 0
NIM_DELETE = 2
NIF_MESSAGE = 1
NIF_ICON = 2
NIF_TIP = 4
WM_RBUTTONUP = 0x0205
TPM_RIGHTBUTTON = 2
TPM_LEFTALIGN = 0
TPM_BOTTOMALIGN = 0
IDI_APPLICATION = 32512


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.DWORD),
        ("hWnd", ctypes.wintypes.HWND),
        ("uID", ctypes.wintypes.UINT),
        ("uFlags", ctypes.wintypes.UINT),
        ("uCallbackMessage", ctypes.wintypes.UINT),
        ("hIcon", ctypes.wintypes.HICON),
        ("szTip", ctypes.c_wchar * 128),
    ]


WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.wintypes.HWND, ctypes.wintypes.UINT,
    ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
)


# Fix argtypes for 64-bit Windows (LPARAM is 64-bit)
user32.DefWindowProcW.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.GetMessageW.argtypes = [ctypes.POINTER(ctypes.wintypes.MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
user32.GetMessageW.restype = ctypes.c_int


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("style", ctypes.wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.wintypes.HINSTANCE),
        ("hIcon", ctypes.wintypes.HICON),
        ("hCursor", ctypes.wintypes.HCURSOR),
        ("hbrBackground", ctypes.wintypes.HBRUSH),
        ("lpszMenuName", ctypes.wintypes.LPCWSTR),
        ("lpszClassName", ctypes.wintypes.LPCWSTR),
        ("hIconSm", ctypes.wintypes.HICON),
    ]


def _popup_menu(hwnd):
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, 0x0000, ID_OPEN, "Open Browser")
    user32.AppendMenuW(menu, 0x0800, 0, "")
    user32.AppendMenuW(menu, 0x0000, ID_QUIT, "Quit")

    class PT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    pt = PT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_LEFTALIGN | TPM_BOTTOMALIGN, pt.x, pt.y, 0, hwnd, None)
    user32.DestroyMenu(menu)


def run_tray():
    hinst = ctypes.windll.kernel32.GetModuleHandleW(None)

    wcx = WNDCLASSEXW()
    wcx.cbSize = ctypes.sizeof(wcx)
    wcx.lpszClassName = "SQLLineageTray"

    icon = user32.LoadIconW(0, ctypes.c_void_p(IDI_APPLICATION))

    @WNDPROC
    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_TRAY and lparam == WM_RBUTTONUP:
            _popup_menu(hwnd)
            return 0
        if msg == WM_COMMAND:
            if wparam == ID_OPEN:
                webbrowser.open(f"http://127.0.0.1:{_PORT}")
                return 0
            if wparam == ID_QUIT:
                user32.PostQuitMessage(0)
                return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    wcx.lpfnWndProc = wndproc
    wcx.hInstance = hinst
    user32.RegisterClassExW(ctypes.byref(wcx))

    hwnd = user32.CreateWindowExW(0, "SQLLineageTray", "", 0, 0, 0, 0, 0, 0, 0, hinst, 0)

    nid = NOTIFYICONDATA()
    nid.cbSize = ctypes.sizeof(nid)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAY
    nid.hIcon = icon
    nid.szTip = "SQL Lineage"
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    msg = ctypes.wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))

    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))


# ── Launcher logic ──

def _exe_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _static_dir() -> Path | None:
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "static" / "index.html"
    if bundled.exists():
        return bundled.parent
    dev = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if dev.exists():
        return dev.parent
    return None


def _ensure_data(exe_dir: Path) -> None:
    data_dir = exe_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "metadata.db"
    os.environ["SQL_LINEAGE_DB"] = str(db_path)
    if not db_path.exists():
        from app.db.sqlite import run_migrations
        run_migrations()


def _start_uvicorn():
    import uvicorn

    from app.main import app

    static_dir = _static_dir()
    if static_dir is not None:
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    uvicorn.run(app, host="127.0.0.1", port=_PORT, log_config=None)


def main():
    try:
        _ensure_data(_exe_dir())
    except Exception as exc:
        ctypes.windll.user32.MessageBoxW(0, f"Failed to initialize data directory:\n{exc}", "SQL Lineage", 0x10)
        sys.exit(1)

    server = threading.Thread(target=_start_uvicorn, daemon=True)
    server.start()

    webbrowser.open(f"http://127.0.0.1:{_PORT}")

    run_tray()


if __name__ == "__main__":
    main()
