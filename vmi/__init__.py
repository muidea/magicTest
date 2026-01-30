import os
import sys

# 获取当前目录
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# 添加必要的路径
sys.path.insert(0, os.path.join(parent_dir, 'session'))  # session模块
sys.path.insert(0, os.path.join(parent_dir, 'cas/cas'))  # cas/cas模块
sys.path.insert(0, os.path.join(parent_dir, 'cas'))  # cas目录
sys.path.insert(0, os.path.join(parent_dir, 'mock'))  # mock目录
sys.path.insert(0, current_dir)  # 当前目录（最后）
