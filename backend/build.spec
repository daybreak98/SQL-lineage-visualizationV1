# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[(r'..\frontend\dist', 'static')],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'app.main',
        'app.api.analyze_controller',
        'app.api.format_controller',
        'app.api.health_controller',
        'app.api.metadata_controller',
        'app.db.migrations.001_metadata',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        'pytest',
        'httpx',
        'pip',
        'setuptools',
        'wheel',
        'pystray',
        'PIL',
        'pillow',
        'six',
    ],
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='sql-lineage',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)
