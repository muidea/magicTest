import os
import sys

dir_path = os.path.dirname(os.path.abspath(__file__))
# 添加 magicTest 目录到路径
magic_test_path = os.path.dirname(os.path.dirname(dir_path))
if magic_test_path not in sys.path:
    sys.path.insert(0, magic_test_path)

# 添加 cas 目录到路径
if dir_path not in sys.path:
    sys.path.append(dir_path)

# 添加 cas/cas 目录到路径
cas_sub_path = os.path.join(dir_path, 'cas')
if cas_sub_path not in sys.path:
    sys.path.append(cas_sub_path)
