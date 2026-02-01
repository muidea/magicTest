#!/usr/bin/env python3
"""
基于会话管理器的并发测试V2
基于当前框架重新实现并发执行测试代码
"""

import concurrent.futures
import threading
import time
import random
import unittest
import logging
from typing import List, Dict, Any, Callable, Optional
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


class ConcurrentTestRunner:
    """基于会话管理器的并发测试运行器"""
    
    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.results_lock = threading.Lock()
        self.results: List[ConcurrentTestResult] = []
        self.session_managers = {}  # 线程ID -> 会话管理器映射
    
    def _get_session_manager_for_thread(self, thread_id: int):
        """为线程获取或创建会话管理器"""
        if thread_id not in self.session_managers:
            try:
                from config_helper import get_server_url, get_credentials
                from session_manager import init_global_session_manager
                
                server_url = get_server_url()
                credentials = get_credentials()
                
                # 为每个线程创建独立的会话管理器
                session_mgr = init_global_session_manager(
                    server_url=server_url,
                    namespace='autotest',
                    username=credentials['username'],
                    password=credentials['password'],
                    refresh_interval=540,
                    session_timeout=1800
                )
                
                if not session_mgr.create_session():
                    logger.error(f"线程 {thread_id}: 创建会话失败")
                    return None
                
                session_mgr.start_auto_refresh()
                self.session_managers[thread_id] = session_mgr
                logger.info(f"线程 {thread_id}: 会话管理器创建成功")
                
            except Exception as e:
                logger.error(f"线程 {thread_id}: 创建会话管理器失败 - {e}")
                return None
        
        return self.session_managers[thread_id]
    
    def _cleanup_session_managers(self):
        """清理所有会话管理器"""
        for thread_id, session_mgr in self.session_managers.items():
            try:
                session_mgr.stop_auto_refresh()
                session_mgr.close_session()
                logger.info(f"线程 {thread_id}: 会话管理器清理完成")
            except Exception as e:
                logger.error(f"线程 {thread_id}: 清理会话管理器失败 - {e}")
        
        self.session_managers.clear()
    
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
                # 获取会话管理器
                session_mgr = self._get_session_manager_for_thread(worker_id)
                if not session_mgr:
                    raise Exception("无法获取会话管理器")
                
                # 执行测试函数
                test_func(worker_id=worker_id, session_manager=session_mgr, **kwargs)
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
                logger.error(f"线程 {worker_id}: 测试失败 - {e}")
        
        logger.info(f"开始并发测试: {test_name}, 请求数: {num_requests}, 工作线程: {self.max_workers}")
        
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = [executor.submit(worker, i) for i in range(num_requests)]
                concurrent.futures.wait(futures)
        finally:
            # 清理会话管理器
            self._cleanup_session_managers()
        
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
        logger.info(f"\n{'='*60}")
        logger.info(f"并发测试摘要: {result.test_name}")
        logger.info(f"{'='*60}")
        logger.info(f"总请求数: {result.total_requests}")
        logger.info(f"成功: {result.successful_requests}")
        logger.info(f"失败: {result.failed_requests}")
        logger.info(f"成功率: {result.successful_requests/result.total_requests*100:.1f}%" if result.total_requests > 0 else "成功率: N/A")
        logger.info(f"总时间: {result.total_time:.2f}秒")
        logger.info(f"平均响应时间: {result.avg_response_time:.3f}秒")
        logger.info(f"最小响应时间: {result.min_response_time:.3f}秒")
        logger.info(f"最大响应时间: {result.max_response_time:.3f}秒")
        logger.info(f"吞吐量: {result.throughput:.2f} 请求/秒")
        
        if result.error_details:
            logger.info(f"\n错误详情 ({len(result.error_details)}个):")
            for i, error in enumerate(result.error_details[:5], 1):
                logger.info(f"  {i}. 线程 {error['worker_id']}: {error['error']}")
            if len(result.error_details) > 5:
                logger.info(f"  ... 还有 {len(result.error_details) - 5} 个错误")
    
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
            ],
            'errors': [
                error for r in self.results for error in r.error_details
            ]
        }
        
        return report
    
    def save_report(self, filepath: str = "concurrent_test_report.json"):
        """保存测试报告到文件"""
        report = self.generate_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"测试报告已保存到: {filepath}")


class ConcurrentTestBase(unittest.TestCase):
    """并发测试基类"""
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        try:
            from test_base_with_session_manager import TestBaseWithSessionManager
            cls.test_base = TestBaseWithSessionManager
            cls.test_base.setUpClass()
            logger.info("并发测试基类: 初始化完成")
        except Exception as e:
            logger.error(f"并发测试基类: 初始化失败 - {e}")
            raise
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if hasattr(cls, 'test_base'):
            cls.test_base.tearDownClass()
            logger.info("并发测试基类: 清理完成")


# 测试函数工厂
class ConcurrentTestFactory:
    """并发测试函数工厂"""
    
    @staticmethod
    def create_store_creation_test():
        """创建门店创建测试函数"""
        def test_create_store(worker_id: int, session_manager):
            from sdk.store import StoreSDK
            
            store_sdk = StoreSDK(session_manager.get_session())
            store_data = {
                'name': f'并发测试门店 {worker_id}',
                'code': f'STORE_CONC_{worker_id:04d}',
                'address': f'测试地址 {worker_id}',
                'contact': f'test{worker_id}@example.com',
                'status': 'active'
            }
            
            result = store_sdk.create_store(store_data)
            assert result is not None
            assert 'id' in result
            logger.debug(f"线程 {worker_id}: 创建门店成功 - ID: {result.get('id')}")
        
        return test_create_store
    
    @staticmethod
    def create_product_creation_test():
        """创建产品创建测试函数"""
        def test_create_product(worker_id: int, session_manager):
            from sdk.product import ProductSDK
            
            product_sdk = ProductSDK(session_manager.get_session())
            product_data = {
                'name': f'并发测试产品 {worker_id}',
                'code': f'PRODUCT_CONC_{worker_id:04d}',
                'price': random.uniform(10.0, 1000.0),
                'category': 'test',
                'status': 'active'
            }
            
            result = product_sdk.create_product(product_data)
            assert result is not None
            assert 'id' in result
            logger.debug(f"线程 {worker_id}: 创建产品成功 - ID: {result.get('id')}")
        
        return test_create_product
    
    @staticmethod
    def create_warehouse_creation_test():
        """创建仓库创建测试函数"""
        def test_create_warehouse(worker_id: int, session_manager):
            from sdk.warehouse import WarehouseSDK
            
            warehouse_sdk = WarehouseSDK(session_manager.get_session())
            warehouse_data = {
                'name': f'并发测试仓库 {worker_id}',
                'code': f'WAREHOUSE_CONC_{worker_id:04d}',
                'address': f'仓库地址 {worker_id}',
                'contact': f'warehouse{worker_id}@example.com',
                'status': 'active'
            }
            
            result = warehouse_sdk.create_warehouse(warehouse_data)
            assert result is not None
            assert 'id' in result
            logger.debug(f"线程 {worker_id}: 创建仓库成功 - ID: {result.get('id')}")
        
        return test_create_warehouse


# 具体的并发测试类
class TestConcurrentStoreOperations(ConcurrentTestBase):
    """并发门店操作测试"""
    
    def test_concurrent_store_creation(self):
        """并发创建门店测试"""
        runner = ConcurrentTestRunner(max_workers=10)
        
        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="concurrent_store_creation",
            num_requests=20
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 15, "至少75%的请求应该成功")
        self.assertLess(result.avg_response_time, 5.0, "平均响应时间应小于5秒")
        self.assertGreater(result.throughput, 1.0, "吞吐量应大于1请求/秒")
    
    def test_high_concurrency_store_operations(self):
        """高并发门店操作测试"""
        runner = ConcurrentTestRunner(max_workers=20)
        
        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="high_concurrency_store_operations",
            num_requests=50
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 40, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 10.0, "平均响应时间应小于10秒")


class TestConcurrentProductOperations(ConcurrentTestBase):
    """并发产品操作测试"""
    
    def test_concurrent_product_creation(self):
        """并发创建产品测试"""
        runner = ConcurrentTestRunner(max_workers=15)
        
        test_func = ConcurrentTestFactory.create_product_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="concurrent_product_creation",
            num_requests=30
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 25, "至少83%的请求应该成功")
        self.assertLess(result.avg_response_time, 3.0, "平均响应时间应小于3秒")
    
    def test_mixed_concurrent_operations(self):
        """混合并发操作测试"""
        runner = ConcurrentTestRunner(max_workers=25)
        
        # 随机选择测试函数
        test_functions = [
            ConcurrentTestFactory.create_store_creation_test(),
            ConcurrentTestFactory.create_product_creation_test(),
            ConcurrentTestFactory.create_warehouse_creation_test()
        ]
        
        def mixed_operation(worker_id: int, session_manager):
            # 随机选择一个操作
            test_func = random.choice(test_functions)
            test_func(worker_id, session_manager)
        
        result = runner.run_concurrent_test(
            test_func=mixed_operation,
            test_name="mixed_concurrent_operations",
            num_requests=100
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 80, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 5.0, "平均响应时间应小于5秒")


class TestConcurrentWarehouseOperations(ConcurrentTestBase):
    """并发仓库操作测试"""
    
    def test_concurrent_warehouse_creation(self):
        """并发创建仓库测试"""
        runner = ConcurrentTestRunner(max_workers=10)
        
        test_func = ConcurrentTestFactory.create_warehouse_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="concurrent_warehouse_creation",
            num_requests=15
        )
        
        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 12, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 4.0, "平均响应时间应小于4秒")


def run_all_concurrent_tests():
    """运行所有并发测试"""
    import unittest
    
    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConcurrentStoreOperations))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConcurrentProductOperations))
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestConcurrentWarehouseOperations))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 生成报告
    if result.wasSuccessful():
        logger.info("\n🎉 所有并发测试通过！")
    else:
        logger.error(f"\n❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误")
    
    return result


if __name__ == '__main__':
    print("🚀 基于会话管理器的并发测试V2")
    print("="*60)
    
    # 运行所有并发测试
    result = run_all_concurrent_tests()
    
    # 退出码
    exit(0 if result.wasSuccessful() else 1)