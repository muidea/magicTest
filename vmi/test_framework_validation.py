#!/usr/bin/env python3
"""
测试框架验证脚本
用于验证新创建的测试框架是否正常工作
"""

import unittest
import sys
import os

def test_imports():
    """测试所有模块导入"""
    print("测试模块导入...")
    
    modules_to_test = [
        'test_config',
        'test_base', 
        'concurrent_test',
        'performance_report',
        'test_runner',
        'test_adapter'
    ]
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"  ✓ {module_name}")
        except Exception as e:
            print(f"  ✗ {module_name}: {e}")
            return False
    
    return True

def test_config_system():
    """测试配置系统"""
    print("\n测试配置系统...")
    
    from test_config import TestConfig
    
    try:
        # 测试配置类
        config = TestConfig()
        print(f"  ✓ 创建配置实例")
        
        # 测试获取配置
        test_mode = config.get('test_mode')
        print(f"  ✓ 获取测试模式: {test_mode}")
        
        # 测试获取服务器配置
        server_config = config.get_server_config()
        print(f"  ✓ 获取服务器配置: {server_config.get('server_url')}")
        
        # 测试设置模式
        config.set_mode('pressure')
        new_mode = config.get('test_mode')
        print(f"  ✓ 设置测试模式: {new_mode}")
        
        # 测试获取模式参数
        mode_params = config.get_mode_params()
        print(f"  ✓ 获取模式参数: warehouse_count={mode_params.get('warehouse_count')}")
        
        return True
    except Exception as e:
        print(f"  ✗ 配置系统测试失败: {e}")
        return False

def test_base_class():
    """测试基类功能"""
    print("\n测试基类功能...")
    
    from test_base import TestBase
    
    class SimpleTest(TestBase):
        def test_simple(self):
            self.assertTrue(True)
            return "测试通过"
    
    try:
        test = SimpleTest()
        test.setUp()
        result = test.test_simple()
        test.tearDown()
        print(f"  ✓ 基类测试: {result}")
        return True
    except Exception as e:
        print(f"  ✗ 基类测试失败: {e}")
        return False

def test_concurrent_framework():
    """测试并发框架"""
    print("\n测试并发框架...")
    
    from concurrent_test import ConcurrentTestRunner, DataIntegrityValidator
    
    try:
        # 测试数据完整性验证器
        validator = DataIntegrityValidator()
        print(f"  ✓ 创建数据完整性验证器")
        
        # 测试并发测试运行器
        runner = ConcurrentTestRunner(max_workers=5)
        print(f"  ✓ 创建并发测试运行器: {runner.max_workers} workers")
        
        return True
    except Exception as e:
        print(f"  ✗ 并发框架测试失败: {e}")
        return False

def test_performance_report():
    """测试性能报告"""
    print("\n测试性能报告...")
    
    from performance_report import PerformanceReport
    
    try:
        report = PerformanceReport()
        
        # 记录测试结果
        report.record_test("test1", "functional", 1.5, True)
        report.record_test("test2", "concurrent", 2.3, False)
        report.record_metric("response_time", 0.15, "seconds")
        
        summary = report.generate_summary()
        print(f"  ✓ 生成性能报告: {summary['total_tests']}个测试")
        
        return True
    except Exception as e:
        print(f"  ✗ 性能报告测试失败: {e}")
        return False

def test_runner():
    """测试运行器"""
    print("\n测试运行器...")
    
    from test_runner import TestRunner
    
    try:
        runner = TestRunner()
        print(f"  ✓ 创建测试运行器")
        
        # 测试运行器方法
        print(f"  ✓ 运行器方法: {dir(runner)[:5]}...")
        
        return True
    except Exception as e:
        print(f"  ✗ 运行器测试失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("测试框架验证")
    print("="*60)
    
    tests = [
        ("模块导入", test_imports),
        ("配置系统", test_config_system),
        ("基类功能", test_base_class),
        ("并发框架", test_concurrent_framework),
        ("性能报告", test_performance_report),
        ("测试运行器", test_runner)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"  ✗ {test_name}: 异常 - {e}")
            results.append((test_name, False))
    
    print("\n" + "="*60)
    print("测试结果摘要")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    
    for test_name, success in results:
        status = "✓" if success else "✗"
        print(f"{status} {test_name}")
    
    print(f"\n总计: {passed_tests}/{total_tests} 通过")
    
    if passed_tests == total_tests:
        print("\n✅ 所有测试通过！测试框架工作正常。")
        return True
    else:
        print(f"\n❌ {total_tests - passed_tests}个测试失败。")
        return False

def create_sample_test_files():
    """创建示例测试文件用于验证"""
    print("\n创建示例测试文件...")
    
    # 创建示例测试
    sample_test = '''"""
示例测试文件
"""
import unittest
from test_base import TestBase

class SampleStoreTest(TestBase):
    def test_store_creation(self):
        """测试店铺创建"""
        print("测试店铺创建...")
        self.assertTrue(True)
    
    def test_goods_management(self):
        """测试商品管理"""
        print("测试商品管理...")
        self.assertEqual(1 + 1, 2)

class SampleWarehouseTest(TestBase):
    def test_warehouse_operations(self):
        """测试仓库操作"""
        print("测试仓库操作...")
        self.assertIsNotNone("test")

if __name__ == '__main__':
    unittest.main()
'''
    
    with open('sample_store_test.py', 'w', encoding='utf-8') as f:
        f.write(sample_test)
    
    print("  ✓ 创建示例测试文件: sample_store_test.py")
    
    return 'sample_store_test.py'

def run_sample_tests(test_file):
    """运行示例测试"""
    print(f"\n运行示例测试: {test_file}")
    
    import subprocess
    
    try:
        result = subprocess.run(
            ['python', '-m', 'unittest', test_file],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("  ✓ 示例测试运行成功")
            print(f"输出:\n{result.stdout}")
            return True
        else:
            print("  ✗ 示例测试运行失败")
            print(f"错误:\n{result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ 运行测试时出错: {e}")
        return False

def main():
    """主函数"""
    
    # 运行框架测试
    framework_ok = run_all_tests()
    
    if not framework_ok:
        print("\n❌ 框架测试失败，跳过示例测试")
        return 1
    
    # 创建并运行示例测试
    test_file = create_sample_test_files()
    tests_ok = run_sample_tests(test_file)
    
    # 清理
    if os.path.exists(test_file):
        os.remove(test_file)
        print(f"\n清理测试文件: {test_file}")
    
    if framework_ok and tests_ok:
        print("\n🎉 所有验证通过！测试框架准备就绪。")
        print("\n使用方法:")
        print("  1. 运行完整测试: python test_runner.py --mode all --env test")
        print("  2. 运行并发测试: python test_runner.py --mode concurrent --env stress")
        print("  3. 运行场景测试: python test_runner.py --mode scenario --env test")
        return 0
    else:
        print("\n⚠️ 部分验证失败，请检查问题。")
        return 1

if __name__ == '__main__':
    sys.exit(main())