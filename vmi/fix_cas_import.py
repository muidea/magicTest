#!/usr/bin/env python3
"""修复cas模块的导入问题"""

import os
import sys

# 读取cas.py文件
cas_file = '/home/rangh/codespace/magicTest/cas/cas/cas.py'
with open(cas_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 修复导入语句
# 将 'from session import session' 改为 'from session import MagicSession'
# 并将代码中的 'session' 改为 'MagicSession' 或保持原样
if 'from session import session' in content:
    print("发现需要修复的导入语句")
    
    # 方案1：直接修改导入语句
    new_content = content.replace('from session import session', 'from session import MagicSession')
    
    # 方案2：或者添加别名
    # new_content = content.replace('from session import session', 'from session import MagicSession as session')
    
    # 保存修改
    with open(cas_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"已修复 {cas_file}")
    
    # 验证修复
    print("\n验证修复...")
    try:
        sys.path.insert(0, '/home/rangh/codespace/magicTest/session')
        sys.path.insert(0, '/home/rangh/codespace/magicTest/cas/cas')
        from session import MagicSession
        from cas.cas import Cas
        print("✓ 导入成功")
    except Exception as e:
        print(f"✗ 导入失败: {e}")
else:
    print("导入语句已正确")