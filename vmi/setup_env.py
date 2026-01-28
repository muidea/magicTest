#!/usr/bin/env python3
"""
环境设置脚本
设置正确的Python路径以使用真实模块
"""

import sys
import os

def setup_environment():
    """设置测试环境"""
    
    # 添加真实模块路径
    paths_to_add = [
        '/home/rangh/codespace/magicTest',
        '/home/rangh/codespace/magicTest/cas',
        '/home/rangh/codespace/magicTest/vmi',  # 当前目录
    ]
    
    for path in paths_to_add:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
    
    print("环境设置完成")
    print(f"Python路径: {sys.path[:3]}...")
    
    # 验证模块导入
    try:
        import session
        import cas.cas
        print("✅ 真实模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False

if __name__ == '__main__':
    setup_environment()