#!/usr/bin/env python3
"""
运行所有测试套件
"""

import sys
import os
import unittest
import warnings
import logging
import importlib.util
from datetime import datetime

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

# 设置日志
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_test_files():
    """查找所有测试文件"""
    test_files = []
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith("_test.py") and "concurrent" not in file and "scenario" not in file:
                full_path = os.path.join(root, file)
                test_files.append(full_path)
    return sorted(test_files)

def import_test_module(file_path):
    """动态导入测试模块"""
    try:
        module_name = file_path.replace("./", "").replace("/", ".").replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.error(f"导入模块 {file_path} 失败: {e}")
        return None

def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("运行完整测试套件")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # 查找所有测试文件
    test_files = find_test_files()
    print(f"找到 {len(test_files)} 个测试文件:")
    for i, file in enumerate(test_files, 1):
        print(f"  {i:2d}. {file}")
    
    print("\n" + "=" * 80)
    print("开始运行测试...")
    print("=" * 80)
    
    total_tests = 0
    total_failures = 0
    total_errors = 0
    test_results = []
    
    for test_file in test_files:
        print(f"\n{'='*60}")
        print(f"运行测试: {test_file}")
        print(f"{'='*60}")
        
        # 导入测试模块
        module = import_test_module(test_file)
        if module is None:
            print(f"❌ 无法导入测试模块: {test_file}")
            continue
        
        # 查找测试类
        test_classes = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and 
                issubclass(attr, unittest.TestCase) and 
                attr != unittest.TestCase):
                test_classes.append(attr)
        
        if not test_classes:
            print(f"⚠ 未找到测试类: {test_file}")
            continue
        
        # 运行测试
        for test_class in test_classes:
            print(f"\n测试类: {test_class.__name__}")
            
            # 创建测试套件
            loader = unittest.TestLoader()
            suite = loader.loadTestsFromTestCase(test_class)
            
            # 运行测试
            runner = unittest.TextTestRunner(verbosity=1, stream=sys.stdout)
            result = runner.run(suite)
            
            # 记录结果
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
            
            test_results.append({
                'file': test_file,
                'class': test_class.__name__,
                'tests': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors)
            })
            
            # 显示失败和错误详情
            if result.failures:
                print(f"\n失败详情 ({test_class.__name__}):")
                for test, traceback in result.failures:
                    first_line = traceback.split('\n')[0] if traceback else "未知错误"
                    print(f"  {test}: {first_line}")
            
            if result.errors:
                print(f"\n错误详情 ({test_class.__name__}):")
                for test, traceback in result.errors:
                    first_line = traceback.split('\n')[0] if traceback else "未知错误"
                    print(f"  {test}: {first_line}")
    
    print("\n" + "=" * 80)
    print("测试结果汇总")
    print("=" * 80)
    
    # 显示详细结果
    print(f"\n测试文件总数: {len(test_results)}")
    print(f"总测试方法数: {total_tests}")
    print(f"失败数: {total_failures}")
    print(f"错误数: {total_errors}")
    
    success_rate = ((total_tests - total_failures - total_errors) / total_tests * 100) if total_tests > 0 else 0
    print(f"成功率: {success_rate:.2f}%")
    
    print(f"\n详细结果:")
    for i, result in enumerate(test_results, 1):
        status = "✅" if result['failures'] == 0 and result['errors'] == 0 else "❌"
        print(f"  {i:2d}. {status} {result['file']} ({result['class']}): "
              f"{result['tests']}个测试, {result['failures']}失败, {result['errors']}错误")
    
    print(f"\n结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return total_failures == 0 and total_errors == 0

if __name__ == '__main__':
    warnings.simplefilter('ignore', ResourceWarning)
    
    success = run_all_tests()
    
    if success:
        print("\n" + "=" * 80)
        print("✅ 所有测试通过!")
        print("=" * 80)
        sys.exit(0)
    else:
        print("\n" + "=" * 80)
        print("❌ 测试失败，需要进一步修复")
        print("=" * 80)
        sys.exit(1)