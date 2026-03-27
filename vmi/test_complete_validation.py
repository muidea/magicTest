#!/usr/bin/env python3
"""
VMI 测试框架 - 完整验证测试
验证核心功能，无需网络连接
"""

import json
import logging
import os
import unittest
from unittest.mock import Mock, patch

logger = logging.getLogger(__name__)


def _clear_config_cache() -> None:
    import sys

    for module in ["config_helper", "tenant_config_helper"]:
        if module in sys.modules:
            del sys.modules[module]


class TestFrameworkValidation(unittest.TestCase):
    """框架验证测试"""

    def test_config_system(self):
        """测试配置系统"""
        logger.info("测试配置系统")

        self.assertTrue(os.path.exists("test_config.json"), "配置文件不存在")

        with open("test_config.json", "r") as f:
            config = json.load(f)

        self.assertIn("mode", config, "配置缺少mode字段")
        self.assertIn("environment", config, "配置缺少environment字段")
        self.assertIn("default_tenant", config, "配置缺少default_tenant字段")
        self.assertIn("default_server_url", config, "配置缺少default_server_url字段")
        self.assertIn("credentials", config, "配置缺少credentials字段")
        self.assertIn("tenant_targets", config, "配置缺少tenant_targets字段")
        self.assertNotIn("server", config, "配置仍包含旧server字段")
        self.assertNotIn("multi_tenant", config, "配置仍包含旧multi_tenant字段")

        logger.info("配置系统测试通过")

    def test_module_imports(self):
        """测试模块导入"""
        logger.info("测试模块导入")

        try:
            from multi_tenant_manager import (MultiTenantSessionManager,
                                              SDKFactory)
            from tenant_config_helper import (get_multi_tenant_config,
                                              is_multi_tenant_enabled)
            from test_base_multi_tenant import TestBaseMultiTenant

            logger.info("核心模块导入成功")
        except ImportError as e:
            self.fail(f"核心模块导入失败: {e}")

        try:
            from config_helper import get_config
            from session_manager import SessionManager
            from test_base_with_session_manager import (
                ConcurrentTestMixin, PerformanceMonitor,
                TestBaseWithSessionManager)

            logger.info("基础模块导入成功")
        except ImportError as e:
            self.fail(f"基础模块导入失败: {e}")

        logger.info("模块导入测试通过")

    def test_config_helpers(self):
        """测试配置助手"""
        logger.info("测试配置助手")
        _clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        self.assertIsInstance(config["enabled"], bool)
        self.assertEqual(config["enabled"], is_multi_tenant_enabled())
        self.assertIn("autotest", config["tenants"])

        logger.info("配置助手测试通过")

    @patch("session_manager.SessionManager")
    def test_multi_tenant_manager(self, MockSessionManager):
        """测试多租户管理器"""
        logger.info("测试多租户管理器")

        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory

        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session

        test_config = {
            "tenant1": {
                "server_url": "https://tenant1.local.vpc",
                "username": "admin1",
                "password": "password1",
                "namespace": "tenant1",
                "enabled": True,
            },
            "tenant2": {
                "server_url": "https://tenant2.local.vpc",
                "username": "admin2",
                "password": "password2",
                "namespace": "tenant2",
                "enabled": True,
            },
        }

        mt_manager = MultiTenantSessionManager(test_config)

        self.assertEqual(len(mt_manager.session_managers), 2)
        self.assertIn("tenant1", mt_manager.session_managers)
        self.assertIn("tenant2", mt_manager.session_managers)

        sdk_factory = SDKFactory(mt_manager)

        class TestSDK:
            def __init__(self, session):
                self.session = session

        sdk = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        self.assertIsNotNone(sdk)

        logger.info("多租户管理器测试通过")

    def test_base_classes(self):
        """测试测试基类"""
        logger.info("测试测试基类")

        from test_base_multi_tenant import TestBaseMultiTenant
        from test_base_with_session_manager import TestBaseWithSessionManager

        self.assertTrue(issubclass(TestBaseMultiTenant, TestBaseWithSessionManager))

        required_methods = [
            "switch_tenant",
            "get_sdk_for_current_tenant",
            "get_sdk_for_tenant",
            "run_for_tenant",
            "run_for_all_tenants",
            "get_tenant_status",
            "assert_tenant_isolation",
        ]

        for method in required_methods:
            self.assertTrue(
                hasattr(TestBaseMultiTenant, method),
                f"TestBaseMultiTenant缺少方法: {method}",
            )

        logger.info("测试基类测试通过")

    def test_runtime_readiness(self):
        """测试运行时入口完整性"""
        logger.info("测试运行时入口完整性")

        test_files = ["scenario_test.py", "aging_test_simple.py", "run_tests.py"]

        for test_file in test_files:
            self.assertTrue(os.path.exists(test_file), f"测试文件不存在: {test_file}")

        _clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()
        self.assertIsInstance(is_multi_tenant_enabled(), bool)
        self.assertIn("autotest", config["tenants"])
        self.assertTrue(config["tenants"]["autotest"]["enabled"])
        self.assertEqual(config["default_tenant"], "autotest")

        logger.info("运行时入口完整性测试通过")

    def test_multi_tenant_full_flow_coverage(self):
        """测试多租户全业务链路覆盖矩阵完整性"""
        logger.info("测试多租户全业务链路覆盖矩阵")

        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        coverage = MultiTenantBusinessScenarioFactory.get_full_flow_coverage()
        expected_entities = {
            "status",
            "warehouse",
            "shelf",
            "store",
            "partner",
            "member",
            "product",
            "product_info",
            "goods_info",
            "goods",
            "reward_policy",
            "credit",
            "credit_report",
            "credit_reward",
            "goods_item",
            "stockin",
            "stockout",
            "order",
        }

        self.assertEqual(set(coverage.keys()), expected_entities)
        self.assertEqual(coverage["status"], ["list", "query"])

        mutable_entities = expected_entities - {"status"}
        for entity_type in mutable_entities:
            self.assertEqual(
                coverage[entity_type],
                ["create", "query", "list", "update", "delete"],
                f"{entity_type} 覆盖矩阵不完整",
            )

        logger.info("多租户全业务链路覆盖矩阵测试通过")

    def test_test_runner(self):
        """测试运行器"""
        logger.info("测试运行器")

        self.assertTrue(os.path.exists("run_tests.py"), "统一测试入口不存在")

        with open("run_tests.py", "r") as f:
            content = f.read()

        self.assertIn("def run_", content)
        self.assertIn("--validation", content)
        self.assertIn("--multi-tenant", content)
        self.assertIn("--quick", content)
        self.assertIn("--all", content)

        logger.info("测试运行器测试通过")

    def test_integration(self):
        """测试集成"""
        logger.info("测试集成")

        try:
            from multi_tenant_manager import MultiTenantSessionManager
            from tenant_config_helper import get_multi_tenant_config

            config = get_multi_tenant_config()

            self.assertIsInstance(config, dict)
            self.assertIn("tenants", config)

            with patch("session_manager.SessionManager"):
                test_config = {
                    "autotest": {
                        "server_url": "https://autotest.local.vpc",
                        "username": "admin",
                        "password": "password",
                        "namespace": "autotest",
                        "enabled": True,
                    }
                }

                mt_manager = MultiTenantSessionManager(test_config)
                self.assertIn("autotest", mt_manager.session_managers)

            logger.info("集成测试通过")
        except Exception as e:
            self.fail(f"集成测试失败: {e}")


def run_validation():
    """运行验证测试"""
    logger.info("=" * 60)
    logger.info("VMI 测试框架 - 验证测试")
    logger.info("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFrameworkValidation)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    logger.info("=" * 60)
    logger.info("验证结果摘要")
    logger.info("=" * 60)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)

    logger.info("总测试数: %s", total)
    logger.info("通过数: %s", passed)
    logger.info("失败数: %s", len(result.failures))

    if result.wasSuccessful():
        logger.info("所有验证测试通过")
        logger.info("框架验证清单:")
        logger.info("1. 配置系统正常")
        logger.info("2. 模块导入正常")
        logger.info("3. 配置助手正常")
        logger.info("4. 多租户管理器正常")
        logger.info("5. 测试基类正常")
        logger.info("6. 运行时入口完整")
        logger.info("7. 测试运行器正常")
        logger.info("8. 集成测试正常")
        return True

    logger.error("部分测试失败")
    if result.failures:
        for test, _traceback in result.failures:
            logger.error("失败: %s", test)
    if result.errors:
        for test, _traceback in result.errors:
            logger.error("错误: %s", test)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_validation()
    exit(0 if success else 1)
