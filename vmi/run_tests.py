#!/usr/bin/env python3
"""
测试运行包装脚本
确保所有测试在正确的环境中运行
"""

import sys
import os
import subprocess
import argparse

def setup_environment():
    """设置测试环境"""
    
    # 添加真实模块路径
    paths_to_add = [
        '/home/rangh/codespace/magicTest',
        '/home/rangh/codespace/magicTest/cas',
        '/home/rangh/codespace/magicTest/vmi',
    ]
    
    for path in paths_to_add:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
    
    # 设置环境变量
    os.environ['PYTHONPATH'] = ':'.join(paths_to_add + [os.environ.get('PYTHONPATH', '')])
    
    print("✅ 环境设置完成")

def run_test_runner(args):
    """运行测试运行器"""
    setup_environment()
    
    # 导入并运行测试运行器
    import test_runner
    return test_runner.main()

def run_pytest(test_path, verbose=False):
    """使用pytest运行测试"""
    setup_environment()
    
    cmd = ['python', '-m', 'pytest', test_path]
    if verbose:
        cmd.append('-v')
    
    print(f"运行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("错误输出:", result.stderr)
    
    return result.returncode

def run_specific_test(test_file, test_class=None, test_method=None):
    """运行特定测试"""
    setup_environment()
    
    if test_method and test_class:
        test_path = f"{test_file}::{test_class}::{test_method}"
    elif test_class:
        test_path = f"{test_file}::{test_class}"
    else:
        test_path = test_file
    
    return run_pytest(test_path, verbose=True)

def main():
    parser = argparse.ArgumentParser(description='VMI测试运行器')
    parser.add_argument('--mode', choices=['basic', 'concurrent', 'scenario', 'all'], 
                       default='all', help='测试模式')
    parser.add_argument('--env', choices=['dev', 'test', 'stress', 'prod'], 
                       default='test', help='测试环境')
    parser.add_argument('--config', help='配置文件路径')
    parser.add_argument('--test-file', help='运行特定测试文件')
    parser.add_argument('--test-class', help='运行特定测试类')
    parser.add_argument('--test-method', help='运行特定测试方法')
    parser.add_argument('--pytest', action='store_true', help='使用pytest运行')
    
    args = parser.parse_args()
    
    if args.test_file:
        # 运行特定测试
        return run_specific_test(args.test_file, args.test_class, args.test_method)
    elif args.pytest:
        # 使用pytest运行所有测试
        return run_pytest('.', verbose=True)
    else:
        # 使用测试运行器
        return run_test_runner(args)

if __name__ == '__main__':
    sys.exit(main())