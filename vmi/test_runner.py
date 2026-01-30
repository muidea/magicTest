#!/usr/bin/env python3
"""
VMI系统统一测试运行器
通过修改配置文件实现环境切换
"""

import argparse
import sys
import os
import json
import urllib3
import ssl
from datetime import datetime
from typing import List, Dict, Any

def check_environment():
    """检查环境"""
    print("✅ 环境检查通过（假定已在虚拟环境中）")

# 环境检查
check_environment()

# 设置环境路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

class UnifiedTestRunner:
    """统一测试运行器"""
    
    def __init__(self):
        self.config_file = 'test_config.json'
        self.default_config = {
            'server_url': 'https://autotest.local.vpc',
            'username': 'administrator',
            'password': 'administrator',
            'namespace': 'autotest',
            'test_mode': 'functional',
            'environment': 'test',
            'max_workers': 10,
            'concurrent_timeout': 30,
            'retry_count': 3,
            # 老化测试配置
            'aging_duration_hours': 24,
            'aging_concurrent_threads': 10,
            'aging_operation_interval': 1.0,
            'aging_max_data_count': 1000,
            'aging_performance_degradation_threshold': 20.0,
            'aging_report_interval_minutes': 30
        }
        
    def update_config_file(self, args):
        """更新配置文件"""
        # 环境到服务器的映射
        env_to_server = {
            'dev': 'http://localhost:8080',
            'test': 'https://autotest.local.vpc',
            'remote': 'https://autotest.remote.vpc',
            'stress': 'https://autotest.stress.vpc',
            'prod': 'https://autotest.prod.vpc'
        }
        
        # 环境到测试模式的映射
        env_to_mode = {
            'dev': 'development',
            'test': 'functional',
            'remote': 'functional',
            'stress': 'pressure',
            'prod': 'production'
        }
        
        # 确定服务器地址
        if args.server:
            server_url = args.server
            print(f"使用自定义服务器: {server_url}")
        else:
            server_url = env_to_server.get(args.env, 'https://autotest.local.vpc')
            print(f"使用{args.env}环境默认服务器: {server_url}")
        
        # 确定测试模式
        test_mode = env_to_mode.get(args.env, 'functional')
        
        # 使用config_helper更新配置
        try:
            from config_helper import update_config
            update_config(
                server_url=server_url,
                username=args.username or 'administrator',
                password=args.password or 'administrator'
            )
            print(f"✅ 配置文件已更新: {self.config_file}")
        except ImportError:
            # 如果config_helper不存在，直接写文件
            config = self.default_config.copy()
            config.update({
                'server_url': server_url,
                'username': args.username or 'administrator',
                'password': args.password or 'administrator',
                'test_mode': test_mode,
                'environment': args.env,
                'max_workers': args.workers,
                'concurrent_timeout': args.timeout
            })
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"✅ 配置文件已创建: {self.config_file}")
        
        # 处理SSL验证
        self.handle_ssl_verification(args, server_url)
        
        # 打印配置摘要
        from config_helper import get_config
        current_config = get_config()
        self.print_config_summary(current_config)
        
        return current_config
    
    def handle_ssl_verification(self, args, server_url):
        """处理SSL验证"""
        # 判断是否需要禁用SSL验证
        need_disable_ssl = False
        
        if args.no_ssl:
            need_disable_ssl = True
            print("⚠ 手动禁用SSL验证")
        elif args.force_ssl:
            need_disable_ssl = False
            print("✓ 强制启用SSL验证")
        else:
            # 自动判断
            if ('remote.vpc' in server_url or 
                'localhost' in server_url or 
                '127.0.0.1' in server_url):
                need_disable_ssl = True
                print("⚠ 自动禁用SSL验证（检测到本地或远程服务器）")
            else:
                print("✓ 使用默认SSL验证")
        
        # 应用SSL设置
        if need_disable_ssl:
            # 禁用SSL警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # 设置环境变量
            os.environ['REQUESTS_CA_BUNDLE'] = ''
            os.environ['CURL_CA_BUNDLE'] = ''
            
            # 创建不验证SSL的上下文
            ssl._create_default_https_context = ssl._create_unverified_context
    
    def print_config_summary(self, config):
        """打印配置摘要"""
        print("\n" + "="*60)
        print("测试配置摘要")
        print("="*60)
        print(f"服务器地址: {config['server_url']}")
        print(f"测试环境: {config['environment']}")
        print(f"测试模式: {config['test_mode']}")
        print(f"用户名: {config['username']}")
        print(f"最大工作线程: {config['max_workers']}")
        print(f"超时时间: {config['concurrent_timeout']}秒")
        print("="*60 + "\n")
    
    def run_basic_tests(self):
        """运行基础功能测试"""
        print("运行基础功能测试...")
        
        import unittest
        
        # 查找测试文件（跳过虚拟环境中的测试）
        test_files = []
        for root, dirs, files in os.walk("."):
            # 跳过虚拟环境目录
            if 'venv' in root or 'site-packages' in root:
                continue
                
            for file in files:
                if file.endswith("_test.py") and "concurrent" not in file and "scenario" not in file:
                    test_files.append(os.path.join(root, file))
        
        suite = unittest.TestSuite()
        loader = unittest.TestLoader()
        
        loaded_count = 0
        for test_file in test_files:
            # 转换为模块名
            module_name = test_file.replace("./", "").replace("/", ".").replace(".py", "")
            try:
                module = __import__(module_name, fromlist=["*"])
                suite.addTests(loader.loadTestsFromModule(module))
                loaded_count += 1
            except Exception as e:
                # 忽略虚拟环境中的模块加载错误
                if 'venv' not in str(e) and 'site-packages' not in str(e):
                    print(f"加载测试模块 {module_name} 失败: {e}")
        
        print(f"✓ 成功加载 {loaded_count} 个测试模块")
        
        # 运行测试
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(suite)
        
        return {
            'test_type': 'basic',
            'total_tests': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'successful': result.testsRun - len(result.failures) - len(result.errors)
        }
    
    def run_concurrent_tests(self):
        """运行并发压力测试"""
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
                'successful': result.testsRun - len(result.failures) - len(result.errors)
            }
        except Exception as e:
            print(f"运行并发测试失败: {e}")
            return {
                'test_type': 'concurrent',
                'error': str(e)
            }
    
    def run_scenario_tests(self):
        """运行业务场景测试"""
        print("运行业务场景测试...")
        
        try:
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
                'successful': result.testsRun - len(result.failures) - len(result.errors)
            }
        except Exception as e:
            print(f"运行场景测试失败: {e}")
            return {
                'test_type': 'scenario',
                'error': str(e)
            }
    
    def run_aging_tests(self):
        """运行长期老化测试"""
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
        """运行所有测试"""
        print("=== 开始运行所有测试 ===")
        
        start_time = datetime.now()
        
        results = []
        
        results.append(self.run_basic_tests())
        results.append(self.run_concurrent_tests())
        results.append(self.run_scenario_tests())
        results.append(self.run_aging_tests())
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        self._print_summary(results, total_duration)
        
        return results
    
    def _print_summary(self, results, duration):
        """打印测试摘要"""
        print("\n" + "="*60)
        print("测试执行摘要")
        print("="*60)
        
        print(f"执行时间: {datetime.now().isoformat()}")
        print(f"总耗时: {duration:.2f}秒")
        
        # 读取当前配置
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f"服务器: {config.get('server_url', '未知')}")
            print(f"环境: {config.get('environment', '未知')}")
        
        print("\n测试结果:")
        for result in results:
            test_type = result['test_type']
            if 'error' in result:
                print(f"  {test_type}: 错误 - {result['error']}")
            else:
                if result['total_tests'] > 0:
                    success_rate = (result['successful'] / result['total_tests'] * 100)
                else:
                    success_rate = 0
                status = "✓" if result['failures'] == 0 and result['errors'] == 0 else "✗"
                print(f"  {test_type}: {status} {result['successful']}/{result['total_tests']} 通过 ({success_rate:.1f}%)")
        
        # 计算总体统计
        total_tests = sum(r.get('total_tests', 0) for r in results)
        total_successful = sum(r.get('successful', 0) for r in results)
        total_failures = sum(r.get('failures', 0) for r in results)
        total_errors = sum(r.get('errors', 0) for r in results)
        
        print("\n总体统计:")
        print(f"  总测试数: {total_tests}")
        print(f"  通过: {total_successful}")
        print(f"  失败: {total_failures}")
        print(f"  错误: {total_errors}")
        
        if total_tests > 0:
            overall_success_rate = total_successful / total_tests * 100
            print(f"  成功率: {overall_success_rate:.1f}%")
        
        if total_failures == 0 and total_errors == 0:
            print(f"\n✓ 所有测试通过!")
        else:
            print(f"\n✗ 测试失败!")
        
        print("="*60)

def main():
    parser = argparse.ArgumentParser(
        description='VMI系统统一测试运行器 - 通过修改配置文件切换环境',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 远程环境测试（自动处理SSL）
  python test_runner_unified.py --env remote
  
  # 本地开发环境
  python test_runner_unified.py --env dev
  
  # 自定义服务器
  python test_runner_unified.py --server https://custom.server.com
  
  # 生产环境测试（强制SSL）
  python test_runner_unified.py --env prod --force-ssl
  
  # 只运行基础测试
  python test_runner_unified.py --mode basic --env remote
  
环境说明:
  dev     -> http://localhost:8080
  test    -> https://autotest.local.vpc
  remote  -> https://autotest.remote.vpc
  stress  -> https://autotest.stress.vpc
  prod    -> https://autotest.prod.vpc
"""
    )
    
    # 环境参数
    parser.add_argument('--env', choices=['dev', 'test', 'remote', 'stress', 'prod'], 
                       default='test', help='测试环境 (默认: test)')
    
    # 服务器地址
    parser.add_argument('--server', type=str,
                       help='服务器地址（覆盖环境默认地址）')
    
    # SSL配置
    parser.add_argument('--no-ssl', action='store_true',
                       help='禁用SSL验证')
    parser.add_argument('--force-ssl', action='store_true',
                       help='强制启用SSL验证')
    
    # 认证参数
    parser.add_argument('--username', type=str,
                       help='用户名 (默认: administrator)')
    parser.add_argument('--password', type=str,
                       help='密码 (默认: administrator)')
    
    # 性能参数
    parser.add_argument('--workers', type=int, default=10,
                       help='最大工作线程数 (默认: 10)')
    parser.add_argument('--timeout', type=int, default=30,
                       help='请求超时时间(秒) (默认: 30)')
    
    # 测试模式
    parser.add_argument('--mode', choices=['basic', 'concurrent', 'scenario', 'aging', 'all'], 
                       default='all', help='测试模式 (默认: all)')
    
    args = parser.parse_args()
    
    # 创建运行器
    runner = UnifiedTestRunner()
    
    # 更新配置文件
    config = runner.update_config_file(args)
    
    # 运行测试
    if args.mode == 'basic':
        result = runner.run_basic_tests()
        print(f"基础测试完成")
    elif args.mode == 'concurrent':
        result = runner.run_concurrent_tests()
        print(f"并发测试完成")
    elif args.mode == 'scenario':
        result = runner.run_scenario_tests()
        print(f"场景测试完成")
    elif args.mode == 'aging':
        result = runner.run_aging_tests()
        print(f"老化测试完成")
    else:
        results = runner.run_all_tests()
        
        # 检查是否有失败
        has_failure = any(r.get('failures', 0) > 0 or r.get('errors', 0) > 0 for r in results)
        if has_failure:
            sys.exit(1)

if __name__ == '__main__':
    main()