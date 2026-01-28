#!/usr/bin/env python3
"""修复代码中cas的使用（Cas -> Cas）"""

import os
import re

def fix_cas_usage_in_file(filepath):
    """修复单个文件中cas的使用"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    changes_made = False
    
    # 修复模式：Cas( -> Cas(
    if 'Cas(' in content:
        print(f"修复 {filepath}: Cas( -> Cas(")
        content = content.replace('Cas(', 'Cas(')
        changes_made = True
    
    # 修复模式：Cas -> Cas
    if 'Cas' in content and 'Cas(' not in content:
        print(f"修复 {filepath}: Cas -> Cas")
        content = content.replace('Cas', 'Cas')
        changes_made = True
    
    if changes_made:
        # 保存修改
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return changes_made

def main():
    print("=== 修复cas使用 ===")
    
    # 查找所有Python文件
    python_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    fixed_count = 0
    for filepath in python_files:
        if fix_cas_usage_in_file(filepath):
            fixed_count += 1
    
    print(f"\n✓ 修复了 {fixed_count} 个文件")
    
    # 验证修复
    print("\n=== 验证修复 ===")
    
    # 检查示例文件
    test_files = [
        './warehouse/shelf_test.py',
        './warehouse/warehouse_test.py',
        './store/store_test.py'
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'Cas' in content:
                    print(f"⚠ {test_file} 中仍有 Cas")
                else:
                    print(f"✓ {test_file} 已修复")

if __name__ == '__main__':
    main()