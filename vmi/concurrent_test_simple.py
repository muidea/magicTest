#!/usr/bin/env python3
"""
简化版并发测试
基于当前框架重新实现，避免SDK依赖问题
"""

import concurrent.futures
import threading
import time
import random
import unittest
import logging
from typing import List, Dict, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime
import json

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class ConcurrentTestResult:
    """并发测试结果数据类"""
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    throughput: float
    error_details: List[Dict[str, Any]]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class SimpleConcurrentTestRunner:
    """简化版并发测试运行器"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.results_lock = threading.Lock()
        self.results: List[ConcurrentTestResult] = []
    
    def run_concurrent_test(
        self,
        test_func: Callable,
        test_name: str,
        num_requests: int,
        **kwargs
    ) -> ConcurrentTestResult:
        """运行并发测试
        
        Args:
            test_func: 测试函数，接受worker_id参数
            test_name: 测试名称
            num_requests: 请求数量
            **kwargs: 传递给测试函数的额外参数
            
        Returns:
            测试结果
        """
        start_time = time.time()
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []
        
        def worker(worker_id: int):
            nonlocal successful_requests, failed_requests
            worker_start = time.time()
            
            try:
                # 执行测试函数
                test_func(worker_id=worker_id, **kwargs)
                worker_end = time.time()
                
                with self.results_lock:
                    successful_requests += 1
                    response_times.append(worker_end - worker_start)
                    
            except Exception as e:
                worker_end = time.time()
                with self.results_lock:
                    failed_requests += 1
                    error_details.append({
                        'worker_id': worker_id,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat(),
                        'response_time': worker_end - worker_start
                    })
                logger.debug(f"线程 {worker_id}: 测试失败 - {e}")
        
        logger.info(f"开始并发测试: {test_name}, 请求数: {num_requests}, 工作线程: {self.max_workers}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(worker, i) for i in range(num_requests)]
            concurrent.futures.wait(futures)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0
        
        throughput = successful_requests / total_time if total_time > 0 else 0
        
        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details
        )
        
        self.results.append(result)
        
        # 打印测试摘要
        self._print_test_summary(result)
        
        return result
    
    def _print_test_summary(self, result: ConcurrentTestResult):
        """打印测试摘要"""
        print(f"\n{'='*60}")
        print(f"并发测试摘要: {result.test_name}")
        print(f"{'='*60}")
        print(f"总请求数: {result.total_requests}")
        print(f"成功: {result.successful_requests}")
        print(f"失败: {result.failed_requests}")
        success_rate = (result.successful_requests / result.total_requests * 100) if result.total_requests > 0 else 0
        print(f"成功率: {success_rate:.1f}%")
        print(f"总时间: {result.total_time:.2f}秒")
        print(f"平均响应时间: {result.avg_response_time:.3f}秒")
        print(f"最小响应时间: {result.min_response_time:.3f}秒")
        print(f"最大响应时间: {result.max_response_time:.3f}秒")
        print(f"吞吐量: {result.throughput:.2f} 请求/秒")
        
        if result.error_details:
            print(f"\n错误详情 ({len(result.error_details)}个):")
            for i, error in enumerate(result.error_details[:3], 1):
                print(f"  {i}. 线程 {error['worker_id']}: {error['error']}")
            if len(result.error_details) > 3:
                print(f"  ... 还有 {len(result.error_details) - 3} 个错误")
    
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        if not self.results:
            return {}
        
        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful_requests for r in self.results)
        total_failed = sum(r.failed_requests for r in self.results)
        total_time = sum(r.total_time for r in self.results)
        
        avg_throughput = total_successful / total_time if total_time > 0 else 0
        success_rate = (total_successful / total_requests * 100) if total_requests > 0 else 0
        
        report = {
            'summary': {
                'total_tests': len(self.results),
                'total_requests': total_requests,
                'total_successful': total_successful,
                'total_failed': total_failed,
                'total_time': total_time,
                'avg_throughput': avg_throughput,
                'success_rate': success_rate,
                'generated_at': datetime.now().isoformat()
            },
            'detailed_results': [
                {
                    'test_name': r.test_name,
                    'total_requests': r.total_requests,
                    'successful_requests': r.successful_requests,
                    'failed_requests': r.failed_requests,
                    'success_rate': (r.successful_requests / r.total_requests * 100) if r.total_requests > 0 else 0,
                    'total_time': r.total_time,
                    'avg_response_time': r.avg_response_time,
                    'min_response_time': r.min_response_time,
                    'max_response_time': r.max_response_time,
                    'throughput': r.throughput
                }
                for r in self.results
            ]
        }
        
        return report
    
    def save_report(self, filepath: str = "concurrent_test_report.json"):
        """保存测试报告到文件"""
        report = self.generate_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"测试报告已保存到: {filepath}")


# 测试函数定义
class ConcurrentTestFunctions:
    """并发测试函数集合"""
    
    @staticmethod
    def mock_api_call(worker_id: int, delay_range: tuple = (0.1, 0.5)):
        """模拟API调用"""
        delay = random.uniform(*delay_range)
        time.sleep(delay)
        
        # 模拟随机失败
        if random.random() < 0.05:  # 5%失败率
            raise Exception(f"模拟API调用失败 (线程 {worker_id})")
        
        return {"worker_id": worker_id, "delay": delay, "status": "success"}
    
    @staticmethod
    def mock_database_operation(worker_id: int):
        """模拟数据库操作"""
        operation_type = random.choice(['insert', 'update', 'select', 'delete'])
        delay = random.uniform(0.05, 0.3)
        time.sleep(delay)
        
        # 模拟随机失败
        if random.random() < 0.03:  # 3%失败率
            raise Exception(f"模拟数据库操作失败: {operation_type} (线程 {worker_id})")
        
        return {"worker_id": worker_id, "operation": operation_type, "delay": delay}
    
    @staticmethod
    def mock_file_operation(worker_id: int):
        """模拟文件操作"""
        file_size = random.randint(1024, 10240)  # 1KB到10KB
        delay = file_size / 10240 * 0.2  # 模拟文件大小相关的延迟
        time.sleep(delay)
        
        # 模拟随机失败
        if random.random() < 0.02:  # 2%失败率
            raise Exception(f"模拟文件操作失败 (线程 {worker_id}, 大小: {file_size}字节)")
        
        return {"worker_id": worker_id, "file_size": file_size, "delay": delay}


# 具体的并发测试类
class TestConcurrentOperations(unittest.TestCase):
    """并发操作测试"""
    
    def test_low_concurrency(self):
        """低并发测试"""
        runner = SimpleConcurrentTestRunner(max_workers=5)
        
        result = runner.run_concurrent_test(
            test_func=ConcurrentTestFunctions.mock_api_call,
            test_name="low_concurrency_api_calls",
            num_requests=10,
            delay_range=(0.1, 0.3)
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 8, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 1.0, "平均响应时间应小于1秒")
    
    def test_medium_concurrency(self):
        """中等并发测试"""
        runner = SimpleConcurrentTestRunner(max_workers=10)
        
        result = runner.run_concurrent_test(
            test_func=ConcurrentTestFunctions.mock_database_operation,
            test_name="medium_concurrency_db_operations",
            num_requests=30
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 25, "至少83%的请求应该成功")
        self.assertLess(result.avg_response_time, 2.0, "平均响应时间应小于2秒")
    
    def test_high_concurrency(self):
        """高并发测试"""
        runner = SimpleConcurrentTestRunner(max_workers=20)
        
        result = runner.run_concurrent_test(
            test_func=ConcurrentTestFunctions.mock_file_operation,
            test_name="high_concurrency_file_operations",
            num_requests=50
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 45, "至少90%的请求应该成功")
        self.assertLess(result.avg_response_time, 3.0, "平均响应时间应小于3秒")
    
    def test_mixed_operations(self):
        """混合操作测试"""
        runner = SimpleConcurrentTestRunner(max_workers=15)
        
        def mixed_operation(worker_id: int):
            # 随机选择操作类型
            operation_type = worker_id % 3
            if operation_type == 0:
                ConcurrentTestFunctions.mock_api_call(worker_id)
            elif operation_type == 1:
                ConcurrentTestFunctions.mock_database_operation(worker_id)
            else:
                ConcurrentTestFunctions.mock_file_operation(worker_id)
        
        result = runner.run_concurrent_test(
            test_func=mixed_operation,
            test_name="mixed_concurrent_operations",
            num_requests=40
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 35, "至少87.5%的请求应该成功")
        self.assertLess(result.avg_response_time, 2.5, "平均响应时间应小于2.5秒")


def run_all_concurrent_tests():
    """运行所有并发测试"""
    import unittest
    
    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConcurrentOperations))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 生成报告
    if result.wasSuccessful():
        print("\n🎉 所有并发测试通过！")
    else:
        print(f"\n❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误")
    
    return result


if __name__ == '__main__':
    print("🚀 简化版并发测试")
    print("="*60)
    print("基于当前框架重新实现的并发测试")
    print("使用模拟操作测试并发框架功能")
    print("="*60)
    
    # 运行所有并发测试
    result = run_all_concurrent_tests()
    
    # 生成综合报告
    if result.wasSuccessful():
        # 创建一个测试运行器来生成报告
        test_runner = SimpleConcurrentTestRunner()
        
        # 运行一个综合测试来生成报告数据
        def comprehensive_test(worker_id: int):
            time.sleep(random.uniform(0.05, 0.2))
            if random.random() < 0.98:  # 98%成功率
                return True
            raise Exception("模拟失败")
        
        test_result = test_runner.run_concurrent_test(
            test_func=comprehensive_test,
            test_name="comprehensive_concurrency_test",
            num_requests=100
        )
        
        # 保存报告
        test_runner.save_report("concurrent_test_simple_report.json")
    
    # 退出码
    exit(0 if result.wasSuccessful() else 1)