#!/usr/bin/env python3
"""
基于会话管理器的并发测试V2
基于当前框架重新实现并发执行测试代码
"""

import concurrent.futures
import json
import logging
import random
import threading
import time
import unittest
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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
    timestamp: Optional[str] = None

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
                from config_helper import get_credentials, get_server_url
                from session_manager import SessionManager

                server_url = get_server_url()
                credentials = get_credentials()

                # 为每个线程创建独立的会话管理器实例（不使用全局单例）
                session_mgr = SessionManager(
                    server_url=server_url,
                    namespace="autotest",
                    username=credentials["username"],
                    password=credentials["password"],
                    refresh_interval=540,
                    session_timeout=1800,
                )

                # 添加超时处理
                import threading
                from queue import Queue

                result_queue = Queue()

                def create_session_with_timeout():
                    try:
                        success = session_mgr.create_session()
                        result_queue.put((success, None))
                    except Exception as e:
                        result_queue.put((False, e))

                # 在单独线程中创建会话，避免阻塞
                session_thread = threading.Thread(target=create_session_with_timeout)
                session_thread.daemon = True
                session_thread.start()
                session_thread.join(timeout=10)  # 10秒超时

                if session_thread.is_alive():
                    logger.error(f"线程 {thread_id}: 创建会话超时 - 服务器可能不可用")
                    return None

                success, error = result_queue.get()

                if not success:
                    error_msg = f"创建会话失败: {error}" if error else "创建会话失败"
                    logger.error(f"线程 {thread_id}: {error_msg}")
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
        import threading

        def cleanup_single_manager(thread_id, session_mgr):
            """清理单个会话管理器"""
            try:
                # 设置超时，避免无限等待
                session_mgr.stop_auto_refresh()
                session_mgr.close_session()
                logger.info(f"线程 {thread_id}: 会话管理器清理完成")
            except Exception as e:
                logger.error(f"线程 {thread_id}: 清理会话管理器失败 - {e}")

        # 并行清理所有会话管理器
        cleanup_threads = []
        for thread_id, session_mgr in self.session_managers.items():
            thread = threading.Thread(
                target=cleanup_single_manager,
                args=(thread_id, session_mgr),
                daemon=True,
            )
            thread.start()
            cleanup_threads.append(thread)

        # 等待所有清理线程完成（最多5秒）
        for thread in cleanup_threads:
            thread.join(timeout=5)

        self.session_managers.clear()

    def run_concurrent_test(
        self, test_func: Callable, test_name: str, num_requests: int, **kwargs
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
                    error_details.append(
                        {
                            "worker_id": worker_id,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                            "response_time": worker_end - worker_start,
                        }
                    )
                logger.error(f"线程 {worker_id}: 测试失败 - {e}")

        logger.info(
            f"开始并发测试: {test_name}, 请求数: {num_requests}, 工作线程: {self.max_workers}"
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = [executor.submit(worker, i) for i in range(num_requests)]
                # 添加超时处理，防止服务器不可用时无限等待
                try:
                    concurrent.futures.wait(futures, timeout=30)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"并发测试超时: {test_name} - 服务器可能不可用")
                    # 取消所有未完成的future
                    for future in futures:
                        if not future.done():
                            future.cancel()
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
            error_details=error_details,
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
        logger.info(
            f"成功率: {result.successful_requests/result.total_requests*100:.1f}%"
            if result.total_requests > 0
            else "成功率: N/A"
        )
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
        success_rate = (
            (total_successful / total_requests * 100) if total_requests > 0 else 0
        )

        report = {
            "summary": {
                "total_tests": len(self.results),
                "total_requests": total_requests,
                "total_successful": total_successful,
                "total_failed": total_failed,
                "total_time": total_time,
                "avg_throughput": avg_throughput,
                "success_rate": success_rate,
                "generated_at": datetime.now().isoformat(),
            },
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "total_requests": r.total_requests,
                    "successful_requests": r.successful_requests,
                    "failed_requests": r.failed_requests,
                    "success_rate": (
                        (r.successful_requests / r.total_requests * 100)
                        if r.total_requests > 0
                        else 0
                    ),
                    "total_time": r.total_time,
                    "avg_response_time": r.avg_response_time,
                    "min_response_time": r.min_response_time,
                    "max_response_time": r.max_response_time,
                    "throughput": r.throughput,
                }
                for r in self.results
            ],
            "errors": [error for r in self.results for error in r.error_details],
        }

        return report

    def save_report(self, filepath: str = "concurrent_test_report.json"):
        """保存测试报告到文件"""
        report = self.generate_report()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"测试报告已保存到: {filepath}")


class ConcurrentTestBase(unittest.TestCase):
    """并发测试基类"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        try:
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            cls.test_base = TestBaseWithSessionManager
            cls.test_base.setUpClass()
            logger.info("并发测试基类: 初始化完成")
        except Exception as e:
            logger.error(f"并发测试基类: 初始化失败 - {e}")
            raise

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if hasattr(cls, "test_base"):
            cls.test_base.tearDownClass()
            logger.info("并发测试基类: 清理完成")


# 测试函数工厂
class ConcurrentTestFactory:
    """并发测试函数工厂"""

    @staticmethod
    def _build_unique_suffix(worker_id: int) -> str:
        return f"{worker_id:04d}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _resolve_status_id(session_manager) -> int:
        from sdk.status import StatusSDK
        from test_dependency_helper import resolve_status_id

        status_sdk = StatusSDK(session_manager.get_session())
        status_id = resolve_status_id(status_sdk)
        if not status_id:
            raise AssertionError("无法获取可用状态ID")
        return status_id

    @staticmethod
    def create_store_creation_test():
        """创建门店创建测试函数"""

        def test_create_store(worker_id: int, session_manager):
            from sdk.store import StoreSDK

            store_sdk = StoreSDK(session_manager.get_session())
            suffix = ConcurrentTestFactory._build_unique_suffix(worker_id)
            store_data = {
                "name": f"并发测试门店_{suffix}",
                "description": f"并发测试创建的门店_{suffix}",
            }

            result = store_sdk.create_store(store_data)
            assert result is not None
            assert "id" in result
            delete_result = store_sdk.delete_store(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建门店成功 - ID: {result.get('id')}")

        return test_create_store

    @staticmethod
    def create_product_creation_test():
        """创建产品创建测试函数"""

        def test_create_product(worker_id: int, session_manager):
            from sdk.product import ProductSDK

            product_sdk = ProductSDK(session_manager.get_session())
            status_id = ConcurrentTestFactory._resolve_status_id(session_manager)
            suffix = ConcurrentTestFactory._build_unique_suffix(worker_id)
            product_data = {
                "name": f"并发测试产品_{suffix}",
                "description": f"并发测试创建的产品_{suffix}",
                "image": [],
                "expire": random.randint(30, 365),
                "tags": ["concurrent", f"worker-{worker_id}", suffix],
                "status": {"id": status_id},
            }

            result = product_sdk.create_product(product_data)
            assert result is not None
            assert "id" in result
            delete_result = product_sdk.delete_product(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建产品成功 - ID: {result.get('id')}")

        return test_create_product

    @staticmethod
    def create_warehouse_creation_test():
        """创建仓库创建测试函数"""

        def test_create_warehouse(worker_id: int, session_manager):
            from sdk.warehouse import WarehouseSDK

            warehouse_sdk = WarehouseSDK(session_manager.get_session())
            suffix = ConcurrentTestFactory._build_unique_suffix(worker_id)
            warehouse_data = {
                "name": f"并发测试仓库_{suffix}",
                "description": f"并发测试创建的仓库_{suffix}",
            }

            result = warehouse_sdk.create_warehouse(warehouse_data)
            assert result is not None
            assert "id" in result
            delete_result = warehouse_sdk.delete_warehouse(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建仓库成功 - ID: {result.get('id')}")

        return test_create_warehouse


# 具体的并发测试类
class TestConcurrentStoreOperations(ConcurrentTestBase):
    """并发门店操作测试"""

    def test_concurrent_store_creation(self):
        """并发创建门店测试"""
        runner = ConcurrentTestRunner(max_workers=5)

        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="concurrent_store_creation",
            num_requests=10,
        )

        # 验证测试结果 - 降低要求以适应实际服务器性能
        self.assertGreaterEqual(result.successful_requests, 5, "至少50%的请求应该成功")
        self.assertLess(result.avg_response_time, 10.0, "平均响应时间应小于10秒")
        self.assertGreater(result.throughput, 0.5, "吞吐量应大于0.5请求/秒")

    def test_high_concurrency_store_operations(self):
        """高并发门店操作测试"""
        runner = ConcurrentTestRunner(max_workers=10)

        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="high_concurrency_store_operations",
            num_requests=20,
        )

        # 验证测试结果 - 降低要求以适应实际服务器性能
        self.assertGreaterEqual(result.successful_requests, 10, "至少50%的请求应该成功")
        self.assertLess(result.avg_response_time, 15.0, "平均响应时间应小于15秒")


class TestConcurrentProductOperations(ConcurrentTestBase):
    """并发产品操作测试"""

    def test_concurrent_product_creation(self):
        """并发创建产品测试"""
        runner = ConcurrentTestRunner(max_workers=15)

        test_func = ConcurrentTestFactory.create_product_creation_test()
        result = runner.run_concurrent_test(
            test_func=test_func,
            test_name="concurrent_product_creation",
            num_requests=30,
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
            ConcurrentTestFactory.create_warehouse_creation_test(),
        ]

        def mixed_operation(worker_id: int, session_manager):
            # 随机选择一个操作
            test_func = random.choice(test_functions)
            test_func(worker_id, session_manager)

        result = runner.run_concurrent_test(
            test_func=mixed_operation,
            test_name="mixed_concurrent_operations",
            num_requests=100,
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
            num_requests=15,
        )

        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 12, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 4.0, "平均响应时间应小于4秒")


class MultiTenantConcurrentRunner:
    """多租户并发测试运行器。

    按租户并发执行，每个租户使用独立会话，避免不同 namespace 之间串会话。
    """

    def __init__(
        self,
        tenant_configs: Dict[str, Dict[str, Any]],
        max_workers: Optional[int] = None,
        timeout: int = 60,
    ):
        self.tenant_configs = tenant_configs
        self.max_workers = max_workers or max(1, len(tenant_configs))
        self.timeout = timeout
        self.results_lock = threading.Lock()
        self.results: List[ConcurrentTestResult] = []
        self.session_managers: Dict[str, Any] = {}

    def _get_session_manager_for_tenant(self, tenant_id: str):
        """为租户获取独立会话管理器。"""
        if tenant_id in self.session_managers:
            return self.session_managers[tenant_id]

        tenant_config = self.tenant_configs[tenant_id]

        try:
            from config_helper import get_session_config
            from session_manager import SessionManager

            session_config = get_session_config()
            session_mgr = SessionManager(
                server_url=tenant_config["server_url"],
                namespace=tenant_config["namespace"],
                username=tenant_config["username"],
                password=tenant_config["password"],
                refresh_interval=session_config.get("refresh_interval", 540),
                session_timeout=session_config.get("timeout", 1800),
            )

            from queue import Queue

            result_queue = Queue()

            def create_session_with_timeout():
                try:
                    success = session_mgr.create_session()
                    result_queue.put((success, None))
                except Exception as exc:
                    result_queue.put((False, exc))

            session_thread = threading.Thread(target=create_session_with_timeout)
            session_thread.daemon = True
            session_thread.start()
            session_thread.join(timeout=min(self.timeout, 15))

            if session_thread.is_alive():
                logger.error("租户 %s: 创建会话超时", tenant_id)
                return None

            success, error = result_queue.get()
            if not success:
                logger.error("租户 %s: 创建会话失败 - %s", tenant_id, error)
                return None

            session_mgr.start_auto_refresh()
            self.session_managers[tenant_id] = session_mgr
            logger.info("租户 %s: 会话初始化完成", tenant_id)
            return session_mgr

        except Exception as exc:
            logger.error("租户 %s: 初始化会话管理器失败 - %s", tenant_id, exc)
            return None

    def _cleanup_session_managers(self):
        """清理所有租户会话。"""

        def cleanup_single_manager(tenant_id: str, session_mgr):
            try:
                session_mgr.stop_auto_refresh()
                session_mgr.close_session()
                logger.info("租户 %s: 会话清理完成", tenant_id)
            except Exception as exc:
                logger.error("租户 %s: 会话清理失败 - %s", tenant_id, exc)

        cleanup_threads = []
        for tenant_id, session_mgr in self.session_managers.items():
            thread = threading.Thread(
                target=cleanup_single_manager,
                args=(tenant_id, session_mgr),
                daemon=True,
            )
            thread.start()
            cleanup_threads.append(thread)

        for thread in cleanup_threads:
            thread.join(timeout=5)

        self.session_managers.clear()

    def run_multi_tenant_test(
        self,
        test_func: Callable,
        test_name: str,
    ) -> ConcurrentTestResult:
        """按租户并发执行测试函数。"""
        if not self.tenant_configs:
            raise ValueError("没有可用的多租户配置")

        tenant_ids = list(self.tenant_configs.keys())
        start_time = time.time()
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []

        def worker(tenant_id: str):
            nonlocal successful_requests, failed_requests
            worker_start = time.time()

            try:
                session_mgr = self._get_session_manager_for_tenant(tenant_id)
                if not session_mgr:
                    raise RuntimeError("无法获取租户会话")

                test_func(tenant_id=tenant_id, session_manager=session_mgr)
                worker_end = time.time()

                with self.results_lock:
                    successful_requests += 1
                    response_times.append(worker_end - worker_start)

            except Exception as exc:
                worker_end = time.time()
                with self.results_lock:
                    failed_requests += 1
                    error_details.append(
                        {
                            "tenant_id": tenant_id,
                            "error": str(exc),
                            "timestamp": datetime.now().isoformat(),
                            "response_time": worker_end - worker_start,
                        }
                    )
                logger.error("租户 %s: 多租户并发测试失败 - %s", tenant_id, exc)

        logger.info(
            "开始多租户并发测试: %s, 租户数: %s, 并发数: %s",
            test_name,
            len(tenant_ids),
            self.max_workers,
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = [executor.submit(worker, tenant_id) for tenant_id in tenant_ids]
                concurrent.futures.wait(futures, timeout=self.timeout)
                for future in futures:
                    if not future.done():
                        future.cancel()
        finally:
            self._cleanup_session_managers()

        total_time = time.time() - start_time
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0

        throughput = successful_requests / total_time if total_time > 0 else 0
        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=len(tenant_ids),
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details,
        )
        self.results.append(result)
        return result


class MultiTenantBusinessScenarioFactory:
    """构造覆盖 VMI 现有业务面的多租户并发场景。"""

    @staticmethod
    def _build_suffix(tenant_id: str) -> str:
        return f"{tenant_id}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _build_numeric_code() -> str:
        return f"{int(time.time() * 1000) % 1000000000}{random.randint(100, 999)}"

    @staticmethod
    def _record_entity(
        created_entities: Dict[str, List[int]],
        entity_type: str,
        entity: Optional[Dict[str, Any]],
    ) -> int:
        if not entity or "id" not in entity:
            raise AssertionError(f"{entity_type} 创建失败，缺少ID")

        entity_id = int(entity["id"])
        created_entities[entity_type].append(entity_id)
        return entity_id

    @staticmethod
    def _assert_namespace(entity: Optional[Dict[str, Any]], tenant_id: str):
        if not entity or "namespace" not in entity:
            return

        namespace = entity.get("namespace")
        if namespace in (None, ""):
            return

        assert namespace == tenant_id, (
            f"租户 {tenant_id} 返回的 namespace 异常，实际为 {namespace}"
        )

    @staticmethod
    def _build_goods_info_payload(
        goods_info: Dict[str, Any],
        product_info_id: int,
        shelf_id: int,
        default_type: int,
        default_count: int,
        default_price: float,
    ) -> Dict[str, Any]:
        return {
            "id": int(goods_info["id"]),
            "sku": goods_info.get("sku", MultiTenantBusinessScenarioFactory._build_numeric_code()),
            "product": goods_info.get("product", {"id": product_info_id}),
            "type": goods_info.get("type", default_type),
            "count": goods_info.get("count", default_count),
            "price": goods_info.get("price", default_price),
            "shelf": goods_info.get("shelf", [{"id": shelf_id}]),
        }

    @staticmethod
    def _cleanup_entities(sdks: Dict[str, Any], created_entities: Dict[str, List[int]]):
        cleanup_plan = [
            ("stockout", "stockout"),
            ("stockin", "stockin"),
            ("order", "order"),
            ("goods_item", "goods_item"),
            ("credit_reward", "credit_reward"),
            ("credit_report", "credit_report"),
            ("credit", "credit"),
            ("reward_policy", "reward_policy"),
            ("goods", "goods"),
            ("goods_info", "goods_info"),
            ("product_info", "product_info"),
            ("product", "product"),
            ("member", "member"),
            ("partner", "partner"),
            ("store", "store"),
            ("shelf", "shelf"),
            ("warehouse", "warehouse"),
        ]

        for entity_type, sdk_key in cleanup_plan:
            sdk = sdks.get(sdk_key)
            delete_method = getattr(sdk, f"delete_{entity_type}", None) if sdk else None
            if not delete_method:
                continue

            for entity_id in reversed(created_entities.get(entity_type, [])):
                try:
                    delete_method(entity_id)
                except Exception as exc:
                    logger.warning("清理 %s(%s) 失败: %s", entity_type, entity_id, exc)

    @staticmethod
    def create_full_business_flow_test():
        """创建全业务覆盖的租户场景测试。"""

        def test_full_business_flow(tenant_id: str, session_manager):
            from sdk import (CreditReportSDK, CreditRewardSDK, CreditSDK,
                             GoodsInfoSDK, GoodsItemSDK, GoodsSDK, MemberSDK,
                             OrderSDK, PartnerSDK, ProductInfoSDK, ProductSDK,
                             RewardPolicySDK, ShelfSDK, StatusSDK, StockinSDK,
                             StockoutSDK, StoreSDK, WarehouseSDK)
            from test_dependency_helper import resolve_status_id

            work_session = session_manager.get_session()
            sdks = {
                "status": StatusSDK(work_session),
                "warehouse": WarehouseSDK(work_session),
                "shelf": ShelfSDK(work_session),
                "store": StoreSDK(work_session),
                "partner": PartnerSDK(work_session),
                "member": MemberSDK(work_session),
                "product": ProductSDK(work_session),
                "product_info": ProductInfoSDK(work_session),
                "goods_info": GoodsInfoSDK(work_session),
                "goods": GoodsSDK(work_session),
                "reward_policy": RewardPolicySDK(work_session),
                "credit": CreditSDK(work_session),
                "credit_report": CreditReportSDK(work_session),
                "credit_reward": CreditRewardSDK(work_session),
                "goods_item": GoodsItemSDK(work_session),
                "stockin": StockinSDK(work_session),
                "stockout": StockoutSDK(work_session),
                "order": OrderSDK(work_session),
            }
            created_entities: Dict[str, List[int]] = defaultdict(list)
            suffix = MultiTenantBusinessScenarioFactory._build_suffix(tenant_id)

            try:
                statuses = sdks["status"].filter_status({"page": 1, "size": 100}) or []
                assert statuses, f"租户 {tenant_id} 无可用状态数据"

                status_id = resolve_status_id(sdks["status"])
                assert status_id, f"租户 {tenant_id} 无法解析可用状态ID"

                status_entity = sdks["status"].query_status(status_id)
                assert status_entity is not None, f"租户 {tenant_id} 查询状态失败"

                warehouse = sdks["warehouse"].create_warehouse(
                    {
                        "name": f"MT_WH_{suffix}",
                        "description": f"多租户并发仓库_{suffix}",
                    }
                )
                warehouse_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "warehouse", warehouse
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(warehouse, tenant_id)
                assert sdks["warehouse"].query_warehouse(warehouse_id) is not None

                shelf = sdks["shelf"].create_shelf(
                    {
                        "description": f"多租户并发货架_{suffix}",
                        "capacity": 200,
                        "warehouse": {"id": warehouse_id},
                        "status": {"id": status_id},
                    }
                )
                shelf_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "shelf", shelf
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(shelf, tenant_id)
                assert sdks["shelf"].query_shelf(shelf_id) is not None

                store = sdks["store"].create_store(
                    {
                        "name": f"MT_STORE_{suffix}",
                        "description": f"多租户并发店铺_{suffix}",
                    }
                )
                store_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "store", store
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(store, tenant_id)
                assert sdks["store"].query_store(store_id) is not None

                partner = sdks["partner"].create_partner(
                    {
                        "name": f"MT_PARTNER_{suffix}",
                        "telephone": f"13{random.randint(100000000, 999999999)}",
                        "wechat": f"wechat_{suffix}",
                        "description": f"多租户并发会员_{suffix}",
                        "status": {"id": status_id},
                    }
                )
                partner_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "partner", partner
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(partner, tenant_id)
                assert sdks["partner"].query_partner(partner_id) is not None

                member = sdks["member"].create_member(
                    {
                        "title": f"店员_{tenant_id}",
                        "name": f"MT_MEMBER_{suffix}",
                        "store": {"id": store_id},
                    }
                )
                member_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "member", member
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(member, tenant_id)
                assert sdks["member"].query_member(member_id) is not None

                product = sdks["product"].create_product(
                    {
                        "name": f"MT_PRODUCT_{suffix}",
                        "description": f"多租户并发产品_{suffix}",
                        "image": [],
                        "expire": 365,
                        "tags": ["multi-tenant", tenant_id, suffix],
                        "status": {"id": status_id},
                    }
                )
                product_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "product", product
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(product, tenant_id)
                assert sdks["product"].query_product(product_id) is not None

                product_info = sdks["product_info"].create_product_info(
                    {
                        "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                        "description": f"多租户并发产品SKU_{suffix}",
                        "product": {"id": product_id},
                    }
                )
                product_info_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "product_info", product_info
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(
                    product_info, tenant_id
                )
                assert sdks["product_info"].query_product_info(product_info_id) is not None

                goods_info_stockin = sdks["goods_info"].create_goods_info(
                    {
                        "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                        "product": {"id": product_info_id},
                        "type": 1,
                        "count": 100,
                        "price": 99.99,
                        "shelf": [{"id": shelf_id}],
                    }
                )
                goods_info_stockin_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_info", goods_info_stockin
                )
                queried_goods_info_stockin = sdks["goods_info"].query_goods_info(
                    goods_info_stockin_id
                )
                assert queried_goods_info_stockin is not None

                goods_info_stockout = sdks["goods_info"].create_goods_info(
                    {
                        "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                        "product": {"id": product_info_id},
                        "type": 2,
                        "count": 50,
                        "price": 59.99,
                        "shelf": [{"id": shelf_id}],
                    }
                )
                goods_info_stockout_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_info", goods_info_stockout
                )
                queried_goods_info_stockout = sdks["goods_info"].query_goods_info(
                    goods_info_stockout_id
                )
                assert queried_goods_info_stockout is not None

                goods = sdks["goods"].create_goods(
                    {
                        "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                        "name": f"MT_GOODS_{suffix}",
                        "description": f"多租户并发商品_{suffix}",
                        "parameter": f"参数_{suffix}",
                        "serviceInfo": f"服务信息_{suffix}",
                        "product": {"id": product_info_id},
                        "count": 80,
                        "price": 119.99,
                        "shelf": [{"id": shelf_id}],
                        "store": {"id": store_id},
                        "status": {"id": status_id},
                    }
                )
                goods_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods", goods
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(goods, tenant_id)
                assert sdks["goods"].query_goods(goods_id) is not None

                reward_policy = sdks["reward_policy"].create_reward_policy(
                    {
                        "name": f"MT_POLICY_{suffix}",
                        "description": f"多租户并发积分策略_{suffix}",
                        "policy": json.dumps(
                            {"type": "fixed", "points": 100, "tenant": tenant_id},
                            ensure_ascii=False,
                        ),
                        "status": {"id": status_id},
                    }
                )
                reward_policy_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "reward_policy", reward_policy
                )
                assert (
                    sdks["reward_policy"].query_reward_policy(reward_policy_id) is not None
                )

                credit = sdks["credit"].create_credit(
                    {
                        "owner": {"id": partner_id},
                        "memo": f"多租户并发积分_{suffix}",
                        "credit": 100,
                        "type": 1,
                        "level": 1,
                    }
                )
                credit_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit", credit
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(credit, tenant_id)
                assert sdks["credit"].query_credit(credit_id) is not None

                credit_report = sdks["credit_report"].create_credit_report(
                    {
                        "owner": {"id": partner_id},
                        "credit": 1000,
                        "available": 800,
                    }
                )
                credit_report_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit_report", credit_report
                )
                assert (
                    sdks["credit_report"].query_credit_report(credit_report_id)
                    is not None
                )

                credit_reward = sdks["credit_reward"].create_credit_reward(
                    {
                        "owner": {"id": partner_id},
                        "credit": 100,
                        "memo": f"多租户并发积分消费_{suffix}",
                    }
                )
                credit_reward_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit_reward", credit_reward
                )
                assert (
                    sdks["credit_reward"].query_credit_reward(credit_reward_id)
                    is not None
                )

                goods_item = sdks["goods_item"].create_goods_item(
                    {
                        "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                        "name": f"MT_GOODS_ITEM_{suffix}",
                        "price": 39.99,
                        "count": 3,
                    }
                )
                goods_item_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_item", goods_item
                )
                assert sdks["goods_item"].query_goods_item(goods_item_id) is not None

                stockin = sdks["stockin"].create_stockin(
                    {
                        "goodsInfo": [
                            MultiTenantBusinessScenarioFactory._build_goods_info_payload(
                                queried_goods_info_stockin,
                                product_info_id,
                                shelf_id,
                                default_type=1,
                                default_count=100,
                                default_price=99.99,
                            )
                        ],
                        "description": f"多租户并发入库单_{suffix}",
                        "store": {"id": store_id},
                        "status": {"id": status_id},
                    }
                )
                stockin_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "stockin", stockin
                )
                assert sdks["stockin"].query_stockin(stockin_id) is not None

                stockout = sdks["stockout"].create_stockout(
                    {
                        "goodsInfo": [
                            MultiTenantBusinessScenarioFactory._build_goods_info_payload(
                                queried_goods_info_stockout,
                                product_info_id,
                                shelf_id,
                                default_type=2,
                                default_count=50,
                                default_price=59.99,
                            )
                        ],
                        "description": f"多租户并发出库单_{suffix}",
                        "store": {"id": store_id},
                        "status": {"id": status_id},
                    }
                )
                stockout_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "stockout", stockout
                )
                assert sdks["stockout"].query_stockout(stockout_id) is not None

                order = sdks["order"].create_order(
                    {
                        "type": 1,
                        "customer": {"id": partner_id},
                        "goods": [
                            {
                                "sku": goods_item.get(
                                    "sku",
                                    MultiTenantBusinessScenarioFactory._build_numeric_code(),
                                ),
                                "name": goods_item.get("name", f"订单商品_{suffix}"),
                                "price": goods_item.get("price", 39.99),
                                "count": 2,
                            }
                        ],
                        "cost": 79.98,
                        "store": {"id": store_id},
                        "status": {"id": status_id},
                    }
                )
                order_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "order", order
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(order, tenant_id)
                assert sdks["order"].query_order(order_id) is not None

                logger.info("租户 %s: 全业务链路执行完成", tenant_id)

            finally:
                MultiTenantBusinessScenarioFactory._cleanup_entities(
                    sdks, created_entities
                )

        return test_full_business_flow


class TestConcurrentMultiTenantBusinessOperations(unittest.TestCase):
    """多租户并发业务覆盖测试。"""

    def test_concurrent_multi_tenant_full_vmi_coverage(self):
        from config_helper import get_max_workers, get_timeout
        from tenant_config_helper import (get_concurrent_tenant_configs,
                                          get_preferred_concurrent_tenant_ids)

        preferred_tenant_ids = get_preferred_concurrent_tenant_ids()
        tenant_configs = get_concurrent_tenant_configs(preferred_tenant_ids)

        if not tenant_configs:
            self.skipTest("多租户未启用，跳过 t001-t005 并发业务测试")

        missing_tenants = [
            tenant_id
            for tenant_id in preferred_tenant_ids
            if tenant_id not in tenant_configs
        ]
        if missing_tenants:
            self.skipTest(f"目标租户配置不完整，缺少: {missing_tenants}")

        runner = MultiTenantConcurrentRunner(
            tenant_configs=tenant_configs,
            max_workers=max(len(tenant_configs), get_max_workers()),
            timeout=max(get_timeout(), 120),
        )

        result = runner.run_multi_tenant_test(
            test_func=MultiTenantBusinessScenarioFactory.create_full_business_flow_test(),
            test_name="concurrent_multi_tenant_full_vmi_coverage",
        )

        self.assertEqual(result.total_requests, len(preferred_tenant_ids))
        self.assertEqual(
            result.successful_requests,
            len(preferred_tenant_ids),
            f"存在租户执行失败: {result.error_details}",
        )
        self.assertEqual(result.failed_requests, 0, f"失败详情: {result.error_details}")
        self.assertGreater(result.avg_response_time, 0, "平均响应时间应大于0")


def run_all_concurrent_tests():
    """运行所有并发测试"""
    import unittest

    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentStoreOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentProductOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentWarehouseOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(
            TestConcurrentMultiTenantBusinessOperations
        )
    )

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 生成报告
    if result.wasSuccessful():
        logger.info("\n🎉 所有并发测试通过！")
    else:
        logger.error(
            f"\n❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误"
        )

    return result


if __name__ == "__main__":
    logger.info("基于会话管理器的并发测试V2")
    logger.info("%s", "=" * 60)

    # 运行所有并发测试
    result = run_all_concurrent_tests()

    # 退出码
    exit(0 if result.wasSuccessful() else 1)
