import sys
from pathlib import Path

# 确保 backend 目录在 Python 路径中
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))
