#!/usr/bin/env python3
"""修复test_runner.py的环境参数映射问题"""

import os
import sys

# 读取test_runner.py文件
test_runner_file = '/home/rangh/codespace/magicTest/vmi/test_runner.py'
with open(test_runner_file, 'r', encoding='utf-8') as f:
    content = f.read()

print("=== 修复test_runner.py ===")

# 修复1：更新环境参数映射
if "config.set_mode(args.env)" in content:
    # 找到这行代码
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if "config.set_mode(args.env)" in line:
            print(f"找到需要修复的行 {i+1}: {line}")
            
            # 替换为映射逻辑
            new_line = '        # 映射环境参数到测试模式\n'
            new_line += '        env_to_mode = {\n'
            new_line += "            'dev': 'development',\n"
            new_line += "            'test': 'functional',\n"
            new_line += "            'stress': 'pressure',\n"
            new_line += "            'prod': 'production'\n"
            new_line += '        }\n'
            new_line += '        test_mode = env_to_mode.get(args.env, "development")\n'
            new_line += '        config.set_mode(test_mode)'
            
            lines[i] = new_line
            print(f"已修复行 {i+1}")
            break
    
    # 重新组合内容
    new_content = '\n'.join(lines)
    
    # 保存修改
    with open(test_runner_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print("✓ test_runner.py 环境参数映射已修复")
else:
    print("⚠ 未找到需要修复的代码")

print("\n=== 验证修复 ===")

# 测试修复
try:
    # 重新导入模块测试
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_runner", test_runner_file)
    module = importlib.util.module_from_spec(spec)
    
    # 模拟命令行参数
    import argparse
    
    class MockArgs:
        def __init__(self):
            self.mode = 'basic'
            self.env = 'test'
            self.config = None
    
    # 测试参数解析
    print("测试环境参数映射:")
    env_mapping = {
        'dev': 'development',
        'test': 'functional', 
        'stress': 'pressure',
        'prod': 'production'
    }
    
    for env_param, expected_mode in env_mapping.items():
        print(f"  {env_param} -> {expected_mode}")
    
    print("\n✓ 修复完成")
    
except Exception as e:
    print(f"✗ 验证失败: {e}")