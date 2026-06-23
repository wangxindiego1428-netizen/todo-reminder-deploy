import sys
from pathlib import Path

# 让测试能 import server 包下的模块
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
