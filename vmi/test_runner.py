#!/usr/bin/env python3
import argparse
import sys
import os
import json
from datetime import datetime
from typing import List, Dict, Any

def check_virtualenv():
    """检查是否在虚拟环境中运行"""
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    if not in_venv:
        print("❌ 错误：未在虚拟环境中运行")
        print("")
        print("要求：必须在激活的Python虚拟环境中运行")
        print("")
        print("请先激活虚拟环境:")
        print("   source venv/bin/activate  # Linux/Mac")
        print("   venv\\Scripts\\activate    # Windows")
        print("")
        sys.exit(1)
    
    print("✅ 虚拟环境检测通过")

# 检查虚拟环境
check_virtualenv()

# 设置环境路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # magicTest目录

sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, 'cas'))

from test_config import TestConfig


class TestRunner:
    def __init__(self):
        self.config = TestConfig()
        self.test_results = []
        
    def run_basic_tests(self, test_pattern: str = "test_*.py"):
        print("运行基础功能测试...")
        
        import unittest
        loader = unittest.TestLoader()
        
        test_files = []
        for root, dirs, files in os.walk("."):
            for file in files:
                if file.endswith("_test.py") and "concurrent" not in file and "scenario" not in file:
                    test_files.append(os.path.join(root, file))
        
        suite = unittest.TestSuite()
        for test_file in test_files:
            module_name = test_file.replace("./", "").replace("/", ".").replace(".py", "")
            try:
                module = __import__(module_name, fromlist=["*"])
                suite.addTests(loader.loadTestsFromModule(module))
            except Exception as e:
                print(f"加载测试模块 {module_name} 失败: {e}")
        
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return {
            'test_type': 'basic',
            'total_tests': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'successful': result.testsRun - len(result.failures) - len(result.errors),
            'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
        }
    
    def run_concurrent_tests(self):
        print("运行并发压力测试...")
        
        try:
            from concurrent_test import ConcurrentStoreTest, ConcurrentWarehouseTest
            import unittest
            
            suite = unittest.TestSuite()
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(ConcurrentStoreTest))
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(ConcurrentWarehouseTest))
            
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            
            return {
                'test_type': 'concurrent',
                'total_tests': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors),
                'successful': result.testsRun - len(result.failures) - len(result.errors),
                'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
            }
        except Exception as e:
            print(f"运行并发测试失败: {e}")
            return {
                'test_type': 'concurrent',
                'error': str(e)
            }
    
    def run_scenario_tests(self):
        print("运行业务场景测试...")
        
        try:
            # 尝试导入场景测试，如果不存在则跳过
            import unittest
            SingleTenantScenarioTest = None
            try:
                from scenario_test import SingleTenantScenarioTest
            except ImportError:
                print("场景测试模块不存在，跳过...")
                return {
                    'test_type': 'scenario',
                    'error': '场景测试模块不存在'
                }
            
            suite = unittest.TestSuite()
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(SingleTenantScenarioTest))
            
            runner = unittest.TextTestRunner(verbosity=2)
            result = runner.run(suite)
            
            return {
                'test_type': 'scenario',
                'total_tests': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors),
                'successful': result.testsRun - len(result.failures) - len(result.errors),
                'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
            }
        except Exception as e:
            print(f"运行场景测试失败: {e}")
            return {
                'test_type': 'scenario',
                'error': str(e)
            }
    
    def run_aging_tests(self):
        print("运行长期老化测试...")
        
        try:
            from aging_test_simple import AgingTestRunner, AgingTestConfig
            
            config = AgingTestConfig()
            config.duration_hours = 1  # 测试1小时
            config.concurrent_threads = 5  # 5个并发线程
            config.max_data_count = 10  # 限制10万条数据
            
            runner = AgingTestRunner(config)
            runner.run()
            
            return {
                'test_type': 'aging',
                'status': 'completed',
                'stop_reason': runner.stop_reason
            }
        except Exception as e:
            print(f"运行老化测试失败: {e}")
            return {
                'test_type': 'aging',
                'error': str(e)
            }
    
    def run_all_tests(self):
        print("=== 开始运行所有测试 ===")
        
        start_time = datetime.now()
        
        results = []
        
        results.append(self.run_basic_tests())
        results.append(self.run_concurrent_tests())
        results.append(self.run_scenario_tests())
        results.append(self.run_aging_tests())
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        summary = self._generate_summary(results, total_duration)
        
        self._save_report(summary)
        self._print_summary(summary)
        
        return summary
    
    def _generate_summary(self, results: List[Dict[str, Any]], total_duration: float) -> Dict[str, Any]:
        total_tests = sum(r.get('total_tests', 0) for r in results)
        total_successful = sum(r.get('successful', 0) for r in results)
        total_failures = sum(r.get('failures', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)
        
        overall_success_rate = total_successful / total_tests * 100 if total_tests > 0 else 0
        
        return {
            'timestamp': datetime.now().isoformat(),
            'total_duration': total_duration,
            'test_results': results,
            'summary': {
                'total_tests': total_tests,
                'total_successful': total_successful,
                'total_failures': total_failures,
                'total_errors': total_errors,
                'overall_success_rate': overall_success_rate,
                'status': 'PASS' if total_failures == 0 and total_errors == 0 else 'FAIL'
            },
            'environment': {
                'test_mode': self.config.get('test_mode'),
                'base_url': self.config.get('base_url'),
                'max_workers': self.config.get('max_workers', 10)
            }
        }
    
    def _save_report(self, summary: Dict[str, Any]):
        report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n测试报告已保存到: {report_file}")
    
    def _print_summary(self, summary: Dict[str, Any]):
        print("\n" + "="*60)
        print("测试执行摘要")
        print("="*60)
        
        print(f"执行时间: {summary['timestamp']}")
        print(f"总耗时: {summary['total_duration']:.2f}秒")
        print(f"测试模式: {summary['environment']['test_mode']}")
        
        print("\n测试结果:")
        for result in summary['test_results']:
            test_type = result['test_type']
            if 'error' in result:
                print(f"  {test_type}: 错误 - {result['error']}")
            else:
                success_rate = result.get('success_rate', 0)
                status = "✓" if result['failures'] == 0 and result['errors'] == 0 else "✗"
                print(f"  {test_type}: {status} {result['successful']}/{result['total_tests']} 通过 ({success_rate:.1f}%)")
        
        print("\n总体统计:")
        stats = summary['summary']
        print(f"  总测试数: {stats['total_tests']}")
        print(f"  通过: {stats['total_successful']}")
        print(f"  失败: {stats['total_failures']}")
        print(f"  错误: {stats['total_errors']}")
        print(f"  成功率: {stats['overall_success_rate']:.1f}%")
        
        if stats['status'] == 'PASS':
            print(f"\n✓ 所有测试通过!")
        else:
            print(f"\n✗ 测试失败!")
        
        print("="*60)


def main():
    parser = argparse.ArgumentParser(description='VMI系统测试运行器')
    parser.add_argument('--mode', choices=['basic', 'concurrent', 'scenario', 'aging', 'all'], 
                       default='all', help='测试模式 (默认: all)')
    parser.add_argument('--env', choices=['dev', 'test', 'stress', 'prod'], 
                       default='test', help='测试环境 (默认: test)')
    parser.add_argument('--config', type=str, help='配置文件路径')
    
    args = parser.parse_args()
    
    if args.config:
        config = TestConfig()
        config.load_config(args.config)
    else:
        config = TestConfig()
        # 映射环境参数到测试模式
        env_to_mode = {
            'dev': 'development',
            'test': 'functional',
            'stress': 'pressure',
            'prod': 'production'
        }
        test_mode = env_to_mode.get(args.env, "development")
        config.set_mode(test_mode)
    
    runner = TestRunner()
    
    if args.mode == 'basic':
        result = runner.run_basic_tests()
        print(f"基础测试完成: {result}")
    elif args.mode == 'concurrent':
        result = runner.run_concurrent_tests()
        print(f"并发测试完成: {result}")
    elif args.mode == 'scenario':
        result = runner.run_scenario_tests()
        print(f"场景测试完成: {result}")
    elif args.mode == 'aging':
        result = runner.run_aging_tests()
        print(f"老化测试完成: {result}")
    else:
        summary = runner.run_all_tests()
        
        if summary['summary']['status'] == 'FAIL':
            sys.exit(1)


if __name__ == '__main__':
    main()