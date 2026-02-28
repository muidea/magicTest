#!/usr/bin/env python3
"""
VMI 测试基类
提供统一的测试基础设施，包括会话管理、并发测试支持、性能监控

包含：
1. TestBaseWithSessionManager - 主测试基类（会话管理）
2. ConcurrentTestMixin - 并发测试混入类
3. PerformanceMonitor - 性能监控器
4. TestResult - 测试结果数据类
"""

import logging
import threading
import time
import unittest
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果数据类"""

    test_name: str
    passed: bool
    duration: float
    error_message: Optional[str] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class ConcurrentTestMixin:
    """并发测试混入类

    提供并发测试所需的基本实体操作接口，
    子类需要实现具体的实体操作方法。
    """

    def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现 create_entity 方法")

    def read_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现 read_entity 方法")

    def update_entity(
        self, entity_type: str, entity_id: str, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        raise NotImplementedError("子类必须实现 update_entity 方法")

    def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        raise NotImplementedError("子类必须实现 delete_entity 方法")

    def list_entities(
        self, entity_type: str, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError("子类必须实现 list_entities 方法")


class PerformanceMonitor:
    """性能监控器

    用于记录和统计测试执行过程中的性能指标。
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self.metrics: List[Dict[str, Any]] = []
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self):
        """开始监控"""
        self.start_time = time.time()

    def stop(self):
        """停止监控"""
        self.end_time = time.time()

    def record_metric(self, metric_name: str, value: float):
        """记录指标"""
        self.metrics.append(
            {
                "name": metric_name,
                "value": value,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        duration = (
            (self.end_time - self.start_time)
            if self.start_time and self.end_time
            else 0
        )

        return {
            "monitor_name": self.name,
            "duration": duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metrics": self.metrics,
        }


class TestBaseWithSessionManager(unittest.TestCase):
    """使用会话管理器的测试基类

    提供会话管理功能，包括：
    1. 自动会话创建和登录
    2. 定期会话刷新（9分钟）
    3. 会话超时处理
    4. SDK实例管理
    5. 便捷的实体操作方法
    """

    namespace = ""
    session_manager = None
    work_session = None
    cas_session = None

    warehouse_sdk = None
    shelf_sdk = None
    store_sdk = None
    product_sdk = None
    partner_sdk = None
    goods_sdk = None
    stockin_sdk = None
    stockout_sdk = None

    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 使用会话管理器"""
        from config_helper import get_credentials, get_server_url
        from session_manager import init_global_session_manager

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        logger.info(f"测试基类: 初始化会话管理器 - 服务器: {cls.server_url}")

        cls.session_manager = init_global_session_manager(
            server_url=cls.server_url,
            namespace=cls.namespace,
            username=cls.credentials["username"],
            password=cls.credentials["password"],
            refresh_interval=540,
            session_timeout=1800,
        )

        if not cls.session_manager.create_session():
            logger.error("测试基类: 创建会话失败")
            raise Exception("创建会话失败")

        cls.session_manager.start_auto_refresh()

        cls.work_session = cls.session_manager.get_session()
        cls.cas_session = cls.session_manager.get_cas_session()

        logger.info("测试基类: 会话初始化完成，自动刷新已启动")

        cls._init_sdk_instances()

    @classmethod
    def _init_sdk_instances(cls):
        """初始化SDK实例"""
        try:
            from sdk import (GoodsSDK, PartnerSDK, ProductSDK, ShelfSDK,
                             StockinSDK, StockoutSDK, StoreSDK, WarehouseSDK)
            from session_manager import ensure_session_valid

            ensure_session_valid(cls.session_manager)

            cls.warehouse_sdk = WarehouseSDK(cls.work_session)
            cls.shelf_sdk = ShelfSDK(cls.work_session)
            cls.store_sdk = StoreSDK(cls.work_session)
            cls.product_sdk = ProductSDK(cls.work_session)
            cls.partner_sdk = PartnerSDK(cls.work_session)
            cls.goods_sdk = GoodsSDK(cls.work_session)
            cls.stockin_sdk = StockinSDK(cls.work_session)
            cls.stockout_sdk = StockoutSDK(cls.work_session)

            logger.debug("测试基类: SDK实例初始化完成")

        except ImportError as e:
            logger.error(f"测试基类: 导入SDK失败 - {e}")
            raise
        except Exception as e:
            logger.error(f"测试基类: 初始化SDK失败 - {e}")
            raise

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls.session_manager:
            logger.info("测试基类: 停止会话管理器")
            cls.session_manager.stop_auto_refresh()
            cls.session_manager.close_session()

        logger.info("测试基类: 清理完成")

    def setUp(self):
        """每个测试用例开始前执行"""
        from session_manager import ensure_session_valid

        if not ensure_session_valid(self.session_manager):
            logger.warning("测试用例: 会话无效，尝试重新连接")
            if not self.session_manager.reconnect():
                self.fail("会话重新连接失败")

        self.session_manager.update_activity()
        logger.debug(f"测试用例开始: {self._testMethodName}")

    def tearDown(self):
        """每个测试用例结束后执行"""
        self.session_manager.update_activity()
        logger.debug(f"测试用例结束: {self._testMethodName}")

    def ensure_session_before_operation(self) -> bool:
        """在执行操作前确保会话有效"""
        from session_manager import ensure_session_valid

        if not ensure_session_valid(self.session_manager):
            logger.warning("操作前检查: 会话无效，尝试重新连接")
            if self.session_manager.reconnect():
                self._init_sdk_instances()
                return True
            else:
                logger.error("操作前检查: 重新连接失败")
                return False

        return True

    def execute_with_session_check(self, operation_func, *args, **kwargs):
        """带会话检查的执行方法"""
        if not self.ensure_session_before_operation():
            self.fail("会话无效且无法恢复，操作中止")

        try:
            result = operation_func(*args, **kwargs)
            self.session_manager.update_activity()
            return result

        except Exception as e:
            error_msg = str(e).lower()
            session_errors = [
                "session",
                "token",
                "auth",
                "login",
                "unauthorized",
                "timeout",
            ]

            if any(error in error_msg for error in session_errors):
                logger.warning(f"操作可能因会话问题失败: {e}")

                logger.info("尝试重新连接并重试操作")
                if self.session_manager.reconnect():
                    self._init_sdk_instances()

                    try:
                        result = operation_func(*args, **kwargs)
                        self.session_manager.update_activity()
                        logger.info("重试操作成功")
                        return result
                    except Exception as retry_error:
                        logger.error(f"重试操作失败: {retry_error}")
                        raise retry_error
                else:
                    logger.error("重新连接失败")
                    raise e
            else:
                raise e

    def create_warehouse(self, warehouse_data):
        return self.execute_with_session_check(
            self.warehouse_sdk.create_warehouse, warehouse_data
        )

    def create_shelf(self, shelf_data):
        return self.execute_with_session_check(self.shelf_sdk.create_shelf, shelf_data)

    def create_product(self, product_data):
        return self.execute_with_session_check(
            self.product_sdk.create_product, product_data
        )

    def create_partner(self, partner_data):
        return self.execute_with_session_check(
            self.partner_sdk.create_partner, partner_data
        )

    def create_goods(self, goods_data):
        return self.execute_with_session_check(self.goods_sdk.create_goods, goods_data)

    def create_stockin(self, stockin_data):
        return self.execute_with_session_check(
            self.stockin_sdk.create_stockin, stockin_data
        )

    def create_stockout(self, stockout_data):
        return self.execute_with_session_check(
            self.stockout_sdk.create_stockout, stockout_data
        )

    def refresh_session_manually(self):
        """手动刷新会话"""
        logger.info("手动刷新会话")
        return self.session_manager.refresh_session()


if __name__ == "__main__":
    print("VMI 测试基类模块")
    print("提供 TestBaseWithSessionManager, ConcurrentTestMixin, PerformanceMonitor")
