#!/usr/bin/env python3
"""
多租户测试示例 - 演示如何使用多租户测试框架

这个示例展示了：
1. 如何编写多租户测试用例
2. 如何验证租户隔离性
3. 如何在不同租户间切换
4. 如何复用现有测试逻辑
"""

import logging
import unittest
from typing import Any, Dict
from unittest.mock import Mock, patch

logger = logging.getLogger(__name__)


def _build_mock_multi_tenant_manager(tenant_ids=None):
    tenant_ids = tenant_ids or ["autotest", "tenant1"]
    manager = Mock()
    manager.get_all_tenant_ids.return_value = tenant_ids
    manager.get_enabled_tenant_ids.return_value = tenant_ids
    manager.ensure_session_valid.return_value = True
    manager.get_tenant_status.side_effect = (
        lambda tenant_id: {"tenant_id": tenant_id, "is_logged_in": True}
    )
    manager.get_all_tenant_status.return_value = {
        tenant_id: {"tenant_id": tenant_id, "is_logged_in": True}
        for tenant_id in tenant_ids
    }
    return manager


class TestMultiTenantExample(unittest.TestCase):
    """多租户测试示例

    演示多租户测试的基本用法和最佳实践。
    """

    def test_multi_tenant_configuration(self):
        """测试多租户配置加载"""
        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()
        enabled = is_multi_tenant_enabled()

        logger.info("多租户启用状态: %s", enabled)
        logger.info("默认租户: %s", config.get("default_tenant", "autotest"))
        logger.info("租户数量: %s", len(config.get("tenants", {})))

        # 验证配置结构
        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)

        # 验证至少有一个租户（autotest）
        self.assertGreaterEqual(len(config["tenants"]), 1)
        self.assertIn("autotest", config["tenants"])

        logger.info("多租户配置测试通过")

    def test_multi_tenant_session_management(self):
        """测试多租户会话管理"""
        import multi_tenant_manager

        mock_manager = _build_mock_multi_tenant_manager()
        multi_tenant_manager.cleanup_global_multi_tenant_manager()

        with patch(
            "multi_tenant_manager.init_global_multi_tenant_manager",
            return_value=mock_manager,
        ):
            mt_manager = multi_tenant_manager.init_global_multi_tenant_manager()

        tenant_ids = mt_manager.get_all_tenant_ids()
        logger.info("可用租户: %s", tenant_ids)

        self.assertGreaterEqual(len(tenant_ids), 1)
        self.assertIn("autotest", tenant_ids)

        status = mt_manager.get_all_tenant_status()
        logger.info("租户状态: %s", list(status.keys()))
        self.assertIn("autotest", status)

        logger.info("多租户会话管理测试通过")

    def test_multi_tenant_sdk_factory(self):
        """测试多租户SDK工厂"""
        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory

        # 创建测试配置
        test_config = {
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
                "enabled": True,
            }
        }

        with patch("session_manager.SessionManager") as MockSessionManager:
            mock_session_mgr = Mock()
            mock_session_mgr.create_session.return_value = True
            mock_session_mgr.is_logged_in = True
            mock_session_mgr.work_session = Mock()
            MockSessionManager.return_value = mock_session_mgr

            # 创建多租户管理器
            mt_manager = MultiTenantSessionManager(test_config)

            # 创建SDK工厂
            sdk_factory = SDKFactory(mt_manager)

            # 模拟SDK类
            class MockSDK:
                def __init__(self, session):
                    self.session = session
                    self.name = "MockSDK"

            # 测试获取SDK实例
            sdk = sdk_factory.get_sdk_for_tenant("autotest", MockSDK)

            # 验证SDK实例创建成功
            self.assertIsNotNone(sdk)
            self.assertEqual(sdk.name, "MockSDK")

        logger.info("多租户SDK工厂测试通过")


class TestMultiTenantIntegration(TestMultiTenantExample):
    """多租户集成测试

    使用实际的多租户测试基类进行测试。
    继承自TestMultiTenantExample以复用测试方法。
    """

    def test_tenant_switching(self):
        """测试租户切换功能"""
        from test_base_multi_tenant import TestBaseMultiTenant

        test_instance = TestBaseMultiTenant()
        test_instance.multi_tenant_enabled = True
        test_instance.multi_tenant_manager = _build_mock_multi_tenant_manager()
        test_instance.current_tenant_id = "autotest"

        tenant_ids = test_instance.multi_tenant_manager.get_all_tenant_ids()

        for tenant_id in tenant_ids[:2]:
            success = test_instance.switch_tenant(tenant_id)
            self.assertTrue(success, f"切换到租户 '{tenant_id}' 失败")
            self.assertEqual(test_instance.current_tenant_id, tenant_id)

            status = test_instance.get_tenant_status()
            self.assertEqual(status["tenant_id"], tenant_id)
            logger.info("成功切换到租户: %s", tenant_id)

        test_instance.switch_tenant("autotest")
        self.assertEqual(test_instance.current_tenant_id, "autotest")

        logger.info("租户切换测试通过")

    def test_multi_tenant_operation(self):
        """测试多租户操作"""
        from test_base_multi_tenant import TestBaseMultiTenant

        test_instance = TestBaseMultiTenant()
        test_instance.multi_tenant_enabled = True
        test_instance.multi_tenant_manager = _build_mock_multi_tenant_manager()
        test_instance.current_tenant_id = "autotest"

        def test_operation(tenant_id):
            logger.info("在租户 '%s' 上执行测试操作", tenant_id)
            return {"tenant_id": tenant_id, "status": "success"}

        results = test_instance.run_for_all_tenants(test_operation)

        self.assertIsInstance(results, dict)
        enabled_tenants = test_instance.multi_tenant_manager.get_enabled_tenant_ids()
        self.assertEqual(len(results), len(enabled_tenants))

        for tenant_id, result in results.items():
            self.assertIn("status", result)
            if result["status"] == "passed":
                self.assertIn("result", result)
                self.assertEqual(result["result"]["tenant_id"], tenant_id)

        logger.info("多租户操作测试通过")


class TestMultiTenantBestPractices(unittest.TestCase):
    """多租户最佳实践示例"""

    def test_context_manager_usage(self):
        """测试上下文管理器用法"""
        from test_base_multi_tenant import SimpleMultiTenantTest

        test_instance = SimpleMultiTenantTest()
        test_instance.multi_tenant_enabled = True
        test_instance.multi_tenant_manager = _build_mock_multi_tenant_manager()
        test_instance.current_tenant_id = "autotest"

        tenant_ids = test_instance.multi_tenant_manager.get_enabled_tenant_ids()

        with test_instance.for_tenant(tenant_ids[0]):
            logger.info(
                "在上下文管理器中，当前租户: %s",
                test_instance.current_tenant_id,
            )
            self.assertEqual(test_instance.current_tenant_id, tenant_ids[0])

        self.assertEqual(test_instance.current_tenant_id, "autotest")

        logger.info("上下文管理器测试通过")

    def test_tenant_isolation_verification(self):
        """测试租户隔离性验证"""
        from test_base_multi_tenant import TestBaseMultiTenant

        test_instance = TestBaseMultiTenant()
        test_instance.multi_tenant_enabled = True
        test_instance.multi_tenant_manager = _build_mock_multi_tenant_manager()
        test_instance.current_tenant_id = "autotest"

        tenant_ids = test_instance.multi_tenant_manager.get_enabled_tenant_ids()

        def verify_tenant_data():
            tenant_id = test_instance.current_tenant_id
            return {"tenant_id": tenant_id, "data": f"data_for_{tenant_id}"}

        test_instance.assert_tenant_isolation(
            tenant_ids[0], tenant_ids[1], verify_tenant_data
        )

        logger.info(
            "租户 '%s' 和 '%s' 隔离性验证通过",
            tenant_ids[0],
            tenant_ids[1],
        )

        logger.info("租户隔离性验证测试通过")


# 运行所有测试
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    logger.info("=" * 60)
    logger.info("多租户测试示例")
    logger.info("=" * 60)

    # 运行测试
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestMultiTenantExample)
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTenantIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTenantBestPractices))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 输出测试结果
    logger.info("=" * 60)
    logger.info("测试结果摘要")
    logger.info("=" * 60)
    logger.info("运行测试数: %s", result.testsRun)
    logger.info(
        "通过数: %s",
        result.testsRun - len(result.failures) - len(result.errors),
    )
    logger.info("失败数: %s", len(result.failures))
    logger.info("错误数: %s", len(result.errors))

    if result.wasSuccessful():
        logger.info("所有测试通过")
    else:
        logger.error("测试失败或出错")

        if result.failures:
            logger.error("失败详情:")
            for test, traceback in result.failures:
                logger.error("%s: %s", test, traceback.splitlines()[-1])

        if result.errors:
            logger.error("错误详情:")
            for test, traceback in result.errors:
                logger.error("%s: %s", test, traceback.splitlines()[-1])

    logger.info("多租户测试示例执行完成")
