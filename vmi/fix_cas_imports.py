#!/usr/bin/env python3
"""修复所有测试文件中的cas导入语句"""

import os
import sys
import re

def fix_cas_imports_in_file(filepath):
    """修复单个文件中的cas导入"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否需要修复
    if 'from cas.cas import Cas' in content:
        print(f"修复 {filepath}")
        
        # 修复导入语句
        new_content = content.replace('from cas.cas import Cas', 'from cas.cas import Cas')
        
        # 修复代码中的使用（cas -> Cas）
        # 但要注意，有些地方可能使用 cas 作为变量名，所以需要小心
        # 先修复明显的模式：Cas -> Cas.Cas（但这是错误的）
        # 实际上，我们需要将 'cas.' 替换为 'Cas.'，但只在某些情况下
        
        # 更安全的方法：只修复导入，让代码中的使用保持原样
        # 因为代码可能使用 'cas' 作为变量名引用导入的类
        
        # 保存修改
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        return True
    return False

def main():
    print("=== 修复cas导入语句 ===")
    
    # 查找所有Python文件
    python_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    fixed_count = 0
    for filepath in python_files:
        if fix_cas_imports_in_file(filepath):
            fixed_count += 1
    
    print(f"\n✓ 修复了 {fixed_count} 个文件")
    
    # 验证修复
    print("\n=== 验证修复 ===")
    
    # 测试导入
    try:
        # 添加路径
        sys.path.insert(0, '/home/rangh/codespace/magicTest/cas/cas')
        sys.path.insert(0, '/home/rangh/codespace/magicTest/session')
        
        from cas.cas import Cas
        from session import MagicSession
        
        print("✓ Cas 类导入成功")
        print("✓ MagicSession 类导入成功")
        
        # 测试创建实例
        work_session = MagicSession('https://autotest.local.vpc', '')
        cas_instance = Cas(work_session)
        print("✓ 成功创建 Cas 实例")
        
    except Exception as e:
        print(f"✗ 导入测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()