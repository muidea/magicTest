#!/usr/bin/env python3
"""
环境设置脚本
设置正确的Python路径以使用真实模块

要求：用户必须预先创建并激活Python虚拟环境
"""

import sys
import os

def check_virtualenv():
    """检查是否在虚拟环境中运行"""
    # 检查是否在虚拟环境中
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if not in_venv:
        print("❌ 错误：未在虚拟环境中运行")
        print("")
        print("要求：必须在激活的Python虚拟环境中运行")
        print("")
        print("解决方案：")
        print("1. 如果已有虚拟环境，请先激活:")
        print("   source venv/bin/activate  # Linux/Mac")
        print("   venv\\Scripts\\activate    # Windows")
        print("")
        print("2. 如果没有虚拟环境，请先创建:")
        print("   python -m venv venv")
        print("")
        print("3. 然后激活虚拟环境并重新运行")
        return False
    
    print("✅ 虚拟环境检测通过")
    print(f"   虚拟环境路径: {sys.prefix}")
    return True

def setup_environment():
    """设置测试环境"""
    
    # 1. 检查虚拟环境
    if not check_virtualenv():
        return False
    
    # 2. 获取当前脚本所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 3. 计算项目根目录（假设vmi目录在magicTest目录下）
    project_root = os.path.dirname(current_dir)  # magicTest目录
    
    # 4. 验证项目目录结构
    required_dirs = [
        project_root,
        os.path.join(project_root, 'cas'),
        os.path.join(project_root, 'session'),
    ]
    
    missing_dirs = []
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            missing_dirs.append(dir_path)
    
    if missing_dirs:
        print("❌ 项目目录结构不完整:")
        for dir_path in missing_dirs:
            print(f"   - {dir_path}")
        print("")
        print("请确保项目已正确克隆，包含以下目录:")
        print("  - magicTest/ (项目根目录)")
        print("  - magicTest/cas/ (CAS模块)")
        print("  - magicTest/session/ (会话模块)")
        print("  - magicTest/vmi/ (VMI测试框架)")
        return False
    
    # 5. 添加真实模块路径（使用相对路径）
    paths_to_add = [
        project_root,                    # magicTest目录
        os.path.join(project_root, 'cas'),  # cas目录
        current_dir,                     # 当前vmi目录
    ]
    
    for path in paths_to_add:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
    
    print("✅ 环境设置完成")
    print(f"   项目根目录: {project_root}")
    print(f"   添加的路径: {paths_to_add[:2]}")
    
    # 6. 验证模块导入
    try:
        import session
        import cas.cas
        print("✅ 真实模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        print("")
        print("可能的原因:")
        print("1. 模块路径未正确添加")
        print("2. 模块文件缺失或损坏")
        print("3. Python路径配置问题")
        print("")
        print("当前Python路径:")
        for i, path in enumerate(sys.path[:5]):
            print(f"   [{i}] {path}")
        return False

if __name__ == '__main__':
    success = setup_environment()
    sys.exit(0 if success else 1)