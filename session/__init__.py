import os
import sys

dir_path = os.path.dirname(os.path.abspath(__file__))
sys.path.append(dir_path)

# 导入 session 模块
from .session import MagicSession
