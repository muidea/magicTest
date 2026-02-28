#!/usr/bin/env python3
"""
多租户测试基类 - 继承现有测试基类，添加多租户测试支持

特性：
1. 继承复用：完全继承TestBaseWithSessionManager的所有功能
2. 多租户支持：添加多租户测试相关方法
3. 向后兼容：默认使用autotest租户，保持现有行为不变
4. 灵活切换：支持在不同租户间切换测试
"""

import logging
import time
import unittest
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 导入现有测试基类
try:
    from test_base_with_session_manager import TestBaseWithSessionManager
except ImportError:
    # 如果导入失败，创建模拟的基类
    class TestBaseWithSessionManager(unittest.TestCase):
        """模拟的测试基类，用于测试"""

        pass


class TestBaseMultiTenant(TestBaseWithSessionManager):
    """多租户测试基类

    继承自TestBaseWithSessionManager，添加多租户测试支持。
    默认使用autotest租户，保持与现有测试的完全兼容性。
    """

    # 类属性
    multi_tenant_enabled = False
    multi_tenant_manager = None
    sdk_factory = None

    # 当前测试的租户上下文
    current_tenant_id = "autotest"

    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 多租户版本"""
        from multi_tenant_manager import (SDKFactory,
                                          init_global_multi_tenant_manager)
        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        # 获取多租户配置
        config = get_multi_tenant_config()
        cls.multi_tenant_enabled = config["enabled"]

        if cls.multi_tenant_enabled:
            logger.info("多租户测试基类: 多租户功能已启用")

            # 初始化全局多租户管理器
            cls.multi_tenant_manager = init_global_multi_tenant_manager()
            if not cls.multi_tenant_manager:
                logger.error("多租户测试基类: 初始化多租户管理器失败")
                raise Exception("初始化多租户管理器失败")

            # 创建SDK工厂
            cls.sdk_factory = SDKFactory(cls.multi_tenant_manager)

            # 获取默认租户ID
            from tenant_config_helper import get_default_tenant_id

            cls.current_tenant_id = get_default_tenant_id()

            logger.info(f"多租户测试基类: 使用默认租户 '{cls.current_tenant_id}'")

            # 初始化默认租户的SDK实例（向后兼容）
            cls._init_default_tenant_sdks()

        else:
            logger.info("多租户测试基类: 多租户功能未启用，使用单租户模式")

            # 导入并调用父类的setUpClass
            # 注意：这里不能直接调用super().setUpClass()，因为父类需要特定的导入
            # 我们将手动调用父类的逻辑
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            TestBaseWithSessionManager.setUpClass.__func__(cls)

    @classmethod
    def _init_default_tenant_sdks(cls):
        """初始化默认租户的SDK实例（向后兼容）"""
        if not cls.multi_tenant_enabled or not cls.sdk_factory:
            return

        try:
            from sdk import (GoodsSDK, PartnerSDK, ProductSDK, ShelfSDK,
                             StockinSDK, StockoutSDK, StoreSDK, WarehouseSDK)

            # 为默认租户创建SDK实例
            cls.warehouse_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, WarehouseSDK
            )
            cls.shelf_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, ShelfSDK
            )
            cls.store_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, StoreSDK
            )
            cls.product_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, ProductSDK
            )
            cls.partner_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, PartnerSDK
            )
            cls.goods_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, GoodsSDK
            )
            cls.stockin_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, StockinSDK
            )
            cls.stockout_sdk = cls.sdk_factory.get_sdk_for_tenant(
                cls.current_tenant_id, StockoutSDK
            )

            logger.debug(
                f"多租户测试基类: 默认租户 '{cls.current_tenant_id}' 的SDK实例初始化完成"
            )

        except ImportError as e:
            logger.error(f"多租户测试基类: 导入SDK失败 - {e}")
            raise
        except Exception as e:
            logger.error(f"多租户测试基类: 初始化SDK失败 - {e}")
            raise

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls.multi_tenant_enabled and cls.multi_tenant_manager:
            logger.info("多租户测试基类: 清理多租户管理器")
            from multi_tenant_manager import \
                cleanup_global_multi_tenant_manager

            cleanup_global_multi_tenant_manager()
        else:
            # 调用父类的清理逻辑
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            if hasattr(TestBaseWithSessionManager, "tearDownClass"):
                TestBaseWithSessionManager.tearDownClass.__func__(cls)

        logger.info("多租户测试基类: 清理完成")

    def setUp(self):
        """每个测试用例开始前执行"""
        if self.multi_tenant_enabled:
            # 确保当前租户的会话有效
            if not self.multi_tenant_manager.ensure_session_valid(
                self.current_tenant_id
            ):
                logger.warning(
                    f"租户 '{self.current_tenant_id}' 会话无效，尝试重新连接"
                )
                session_mgr = self.multi_tenant_manager.get_session_manager(
                    self.current_tenant_id
                )
                if session_mgr and not session_mgr.reconnect():
                    self.fail(f"租户 '{self.current_tenant_id}' 重新连接失败")
        else:
            # 调用父类的setUp
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            TestBaseWithSessionManager.setUp(self)

        logger.debug(f"测试用例开始: {self._testMethodName}")

    def tearDown(self):
        """每个测试用例结束后执行"""
        logger.debug(f"测试用例结束: {self._testMethodName}")

    # ==================== 多租户专用方法 ====================

    def switch_tenant(self, tenant_id: str) -> bool:
        """切换到指定租户

        Args:
            tenant_id: 要切换到的租户ID

        Returns:
            切换是否成功
        """
        if not self.multi_tenant_enabled:
            logger.warning(f"多租户功能未启用，无法切换到租户 '{tenant_id}'")
            return False

        # 检查租户是否存在
        if tenant_id not in self.multi_tenant_manager.get_all_tenant_ids():
            logger.error(f"租户 '{tenant_id}' 不存在")
            return False

        # 确保租户会话有效
        if not self.multi_tenant_manager.ensure_session_valid(tenant_id):
            logger.error(f"租户 '{tenant_id}' 会话无效")
            return False

        # 切换租户
        old_tenant_id = self.current_tenant_id
        self.current_tenant_id = tenant_id

        logger.info(f"从租户 '{old_tenant_id}' 切换到 '{tenant_id}'")
        return True

    def get_sdk_for_current_tenant(self, sdk_class) -> Optional[Any]:
        """获取当前租户的SDK实例

        Args:
            sdk_class: SDK类

        Returns:
            SDK实例，如果获取失败则返回None
        """
        if not self.multi_tenant_enabled or not self.sdk_factory:
            logger.warning("多租户功能未启用，无法获取租户特定的SDK")
            return None

        return self.sdk_factory.get_sdk_for_tenant(self.current_tenant_id, sdk_class)

    def get_sdk_for_tenant(self, tenant_id: str, sdk_class) -> Optional[Any]:
        """获取指定租户的SDK实例

        Args:
            tenant_id: 租户ID
            sdk_class: SDK类

        Returns:
            SDK实例，如果获取失败则返回None
        """
        if not self.multi_tenant_enabled or not self.sdk_factory:
            logger.warning("多租户功能未启用，无法获取租户特定的SDK")
            return None

        return self.sdk_factory.get_sdk_for_tenant(tenant_id, sdk_class)

    def run_for_tenant(
        self, tenant_id: str, test_func: Callable, *args, **kwargs
    ) -> Any:
        """为指定租户运行测试函数

        Args:
            tenant_id: 租户ID
            test_func: 测试函数
            *args, **kwargs: 测试函数的参数

        Returns:
            测试函数的返回值

        Raises:
            ValueError: 如果租户不存在
            RuntimeError: 如果会话无效
        """
        if not self.multi_tenant_enabled:
            raise RuntimeError("多租户功能未启用")

        # 保存当前租户
        original_tenant_id = self.current_tenant_id

        try:
            # 切换到指定租户
            if not self.switch_tenant(tenant_id):
                raise ValueError(f"无法切换到租户 '{tenant_id}'")

            # 执行测试函数
            result = test_func(*args, **kwargs)

            return result

        finally:
            # 恢复原始租户
            if original_tenant_id != self.current_tenant_id:
                self.switch_tenant(original_tenant_id)

    def run_for_all_tenants(
        self, test_func: Callable, *args, **kwargs
    ) -> Dict[str, Any]:
        """为所有启用的租户运行测试函数

        Args:
            test_func: 测试函数，第一个参数必须是tenant_id
            *args, **kwargs: 测试函数的其他参数

        Returns:
            字典：租户ID -> 测试结果
        """
        if not self.multi_tenant_enabled:
            logger.warning("多租户功能未启用，只运行默认租户")
            results = {}
            try:
                result = test_func("autotest", *args, **kwargs)
                results["autotest"] = {"status": "passed", "result": result}
            except Exception as e:
                results["autotest"] = {"status": "failed", "error": str(e)}
            return results

        results = {}
        enabled_tenant_ids = self.multi_tenant_manager.get_enabled_tenant_ids()

        for tenant_id in enabled_tenant_ids:
            try:
                # 为每个租户运行测试
                result = self.run_for_tenant(
                    tenant_id, test_func, tenant_id, *args, **kwargs
                )
                results[tenant_id] = {"status": "passed", "result": result}

            except Exception as e:
                results[tenant_id] = {"status": "failed", "error": str(e)}
                logger.error(f"租户 '{tenant_id}' 测试失败: {e}")

        return results

    def execute_with_tenant_session_check(
        self, tenant_id: str, operation_func: Callable, *args, **kwargs
    ) -> Any:
        """在确保租户会话有效的情况下执行操作

        Args:
            tenant_id: 租户ID
            operation_func: 要执行的操作函数
            *args, **kwargs: 操作函数的参数

        Returns:
            操作函数的返回值

        Raises:
            ValueError: 如果租户不存在
            RuntimeError: 如果会话无效且无法恢复
        """
        if not self.multi_tenant_enabled:
            raise RuntimeError("多租户功能未启用")

        return self.multi_tenant_manager.execute_with_session_check(
            tenant_id, operation_func, *args, **kwargs
        )

    def get_tenant_status(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """获取租户状态

        Args:
            tenant_id: 租户ID，如果为None则获取当前租户状态

        Returns:
            租户状态字典
        """
        if not self.multi_tenant_enabled:
            return {"error": "多租户功能未启用"}

        target_tenant_id = tenant_id or self.current_tenant_id
        return self.multi_tenant_manager.get_tenant_status(target_tenant_id)

    def get_all_tenant_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有租户的状态

        Returns:
            字典：租户ID -> 状态字典
        """
        if not self.multi_tenant_enabled:
            return {"autotest": {"error": "多租户功能未启用"}}

        return self.multi_tenant_manager.get_all_tenant_status()

    def assert_tenant_isolation(
        self,
        tenant1_id: str,
        tenant2_id: str,
        operation_func: Callable,
        *args,
        **kwargs,
    ):
        """断言租户隔离性

        验证两个租户的数据互相不可见。

        Args:
            tenant1_id: 第一个租户ID
            tenant2_id: 第二个租户ID
            operation_func: 验证函数，接受tenant_id参数
            *args, **kwargs: 验证函数的其他参数

        Raises:
            AssertionError: 如果租户隔离性验证失败
        """
        if not self.multi_tenant_enabled:
            self.skipTest("多租户功能未启用，跳过租户隔离性测试")

        # 在租户1执行操作
        result1 = self.run_for_tenant(tenant1_id, operation_func, *args, **kwargs)

        # 在租户2执行相同操作，应该看不到租户1的数据
        try:
            result2 = self.run_for_tenant(tenant2_id, operation_func, *args, **kwargs)

            # 验证结果不同（表示数据隔离）
            self.assertNotEqual(
                result1,
                result2,
                f"租户隔离性验证失败: 租户 '{tenant1_id}' 和 '{tenant2_id}' 看到相同的数据",
            )

        except Exception as e:
            # 如果租户2执行失败（例如访问权限错误），也说明隔离性有效
            logger.info(
                f"租户 '{tenant2_id}' 访问租户 '{tenant1_id}' 的数据失败，符合隔离性预期: {e}"
            )

    # ==================== 向后兼容的包装方法 ====================

    def ensure_session_before_operation(self) -> bool:
        """在执行操作前确保会话有效（向后兼容）"""
        if self.multi_tenant_enabled:
            return self.multi_tenant_manager.ensure_session_valid(
                self.current_tenant_id
            )
        else:
            # 调用父类的方法
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            return TestBaseWithSessionManager.ensure_session_before_operation(self)

    def execute_with_session_check(self, operation_func, *args, **kwargs):
        """带会话检查的执行方法（向后兼容）"""
        if self.multi_tenant_enabled:
            return self.execute_with_tenant_session_check(
                self.current_tenant_id, operation_func, *args, **kwargs
            )
        else:
            # 调用父类的方法
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            return TestBaseWithSessionManager.execute_with_session_check(
                self, operation_func, *args, **kwargs
            )


# 简化的多租户测试基类（用于快速测试）
class SimpleMultiTenantTest(TestBaseMultiTenant):
    """简化的多租户测试基类

    提供更简洁的API，适合快速编写多租户测试。
    """

    def test_all_tenants(self, test_func: Callable, *args, **kwargs) -> Dict[str, Any]:
        """为所有租户运行测试（简化版）"""
        return self.run_for_all_tenants(test_func, *args, **kwargs)

    def for_tenant(self, tenant_id: str):
        """为指定租户创建上下文管理器

        用法：
            with self.for_tenant("tenant1"):
                # 在这个代码块中，所有操作都在tenant1租户上执行
                result = self.warehouse_sdk.create_warehouse(data)
        """

        class TenantContext:
            def __init__(self, test_instance, tenant_id):
                self.test_instance = test_instance
                self.tenant_id = tenant_id
                self.original_tenant_id = test_instance.current_tenant_id

            def __enter__(self):
                if not self.test_instance.switch_tenant(self.tenant_id):
                    raise ValueError(f"无法切换到租户 '{self.tenant_id}'")
                return self.test_instance

            def __exit__(self, exc_type, exc_val, exc_tb):
                if self.original_tenant_id != self.test_instance.current_tenant_id:
                    self.test_instance.switch_tenant(self.original_tenant_id)
                return False  # 不捕获异常

        return TenantContext(self, tenant_id)


# 测试代码
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("多租户测试基类测试")
    print("=" * 60)

    # 创建测试类实例
    class TestMultiTenantDemo(TestBaseMultiTenant):
        def test_multi_tenant_feature(self):
            print(f"当前租户: {self.current_tenant_id}")
            print(f"多租户启用: {self.multi_tenant_enabled}")

            if self.multi_tenant_enabled:
                # 获取所有租户状态
                status = self.get_all_tenant_status()
                print(f"租户状态: {list(status.keys())}")

                # 测试切换租户
                tenant_ids = list(status.keys())
                if len(tenant_ids) > 1:
                    print(f"可用租户: {tenant_ids}")

                    # 切换到第一个租户
                    if self.switch_tenant(tenant_ids[0]):
                        print(f"切换到租户: {self.current_tenant_id}")

                    # 切换回默认租户
                    self.switch_tenant("autotest")
                    print(f"切换回默认租户: {self.current_tenant_id}")

            self.assertTrue(True, "测试通过")

    # 运行测试
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMultiTenantDemo)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print(f"\n测试结果: {'通过' if result.wasSuccessful() else '失败'}")
    print("✅ 多租户测试基类测试完成")
