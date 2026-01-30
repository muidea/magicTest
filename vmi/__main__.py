#!/usr/bin/env python3
"""
VMI测试系统主入口

已弃用：请使用 run_all_tests.py 作为主入口
"""

import sys

print("="*60)
print("VMI测试系统")
print("="*60)
print("注意：此入口已弃用")
print("")
print("请使用以下命令运行测试：")
print("  python3 run_all_tests.py --quick    # 快速测试")
print("  python3 run_all_tests.py --all      # 所有测试")
print("  python3 run_all_tests.py --help     # 查看帮助")
print("")
print("="*60)

# 自动重定向到 run_all_tests.py --help
if len(sys.argv) == 1:
    print("自动显示帮助信息...")
    import subprocess
    subprocess.run([sys.executable, "run_all_tests.py", "--help"])
