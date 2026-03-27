#!/usr/bin/env python3
"""
VMI 多租户测试
整合核心功能测试和配置验证测试，无需网络连接
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


def _build_config(
    tenant_targets=None,
    tenant_url_template="https://{tenant}.test.vpc",
    default_server_url="https://autotest.test.vpc",
    mode="aging_multi_tenant",
) -> dict:
    return {
        "mode": mode,
        "environment": "test",
        "default_tenant": "autotest",
        "request_namespace": "",
        "default_server_url": default_server_url,
        "tenant_targets": tenant_targets or [],
        "tenant_url_template": tenant_url_template,
        "credentials": {"username": "administrator", "password": "administrator"},
        "session": {"refresh_interval": 540, "timeout": 1800},
        "concurrent": {"max_workers": 10, "timeout": 30, "retry_count": 3},
        "aging": {
            "duration_hours": 0.1,
            "concurrent_threads": 5,
            "operation_interval": 1.0,
            "max_data_count": 1000,
            "performance_degradation_threshold": 20.0,
            "report_interval_minutes": 5,
            "multi_tenant_business_flow_enabled": True,
        },
    }


class TestMultiTenantCore(unittest.TestCase):
    """多租户核心功能测试"""

    def test_config_helper(self):
        """测试配置助手核心逻辑"""
        _clear_config_cache()
        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled

        config = get_multi_tenant_config()

        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        self.assertIn("autotest", config["tenants"])
        self.assertIsInstance(config["enabled"], bool)
        self.assertEqual(config["enabled"], is_multi_tenant_enabled())

        logger.info("配置助手核心逻辑测试通过")

    def test_multi_tenant_manager_structure(self):
        """测试多租户管理器结构"""
        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory

        mock_config = {
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "admin",
                "password": "password",
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

            mt_manager = MultiTenantSessionManager(mock_config)

            self.assertIn("autotest", mt_manager.session_managers)
            self.assertIn("autotest", mt_manager.session_locks)
            self.assertIsNotNone(mt_manager.get_session_manager("autotest"))
            self.assertIsNone(mt_manager.get_session_manager("nonexistent"))

            sdk_factory = SDKFactory(mt_manager)

            class MockSDK:
                def __init__(self, session):
                    self.session = session

            sdk = sdk_factory.get_sdk_for_tenant("autotest", MockSDK)
            self.assertIsNotNone(sdk)
            self.assertIs(sdk, sdk_factory.get_sdk_for_tenant("autotest", MockSDK))

            logger.info("多租户管理器结构测试通过")

    def test_test_base_inheritance(self):
        """测试测试基类继承关系"""
        from test_base_multi_tenant import TestBaseMultiTenant
        from test_base_with_session_manager import TestBaseWithSessionManager

        self.assertTrue(issubclass(TestBaseMultiTenant, TestBaseWithSessionManager))
        self.assertTrue(hasattr(TestBaseMultiTenant, "multi_tenant_enabled"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "multi_tenant_manager"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "sdk_factory"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "current_tenant_id"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "switch_tenant"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "run_for_all_tenants"))
        self.assertTrue(hasattr(TestBaseMultiTenant, "get_tenant_status"))

        logger.info("测试基类继承关系测试通过")

    def test_config_schema(self):
        """测试当前配置文件使用精简后的最终结构"""
        config_path = "test_config.json"
        if not os.path.exists(config_path):
            self.skipTest("配置文件不存在")

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertIn("default_server_url", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenant_targets", config)
        self.assertNotIn("server", config)
        self.assertNotIn("multi_tenant", config)

        logger.info("最终配置结构测试通过")


class TestMultiTenantConfig(unittest.TestCase):
    """多租户配置验证测试"""

    def setUp(self):
        self.original_config_exists = os.path.exists("test_config.json")
        if self.original_config_exists:
            with open("test_config.json", "r", encoding="utf-8") as f:
                self.original_config = f.read()

    def tearDown(self):
        if self.original_config_exists:
            with open("test_config.json", "w", encoding="utf-8") as f:
                f.write(self.original_config)
        elif os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def _write_config(self, content: dict) -> None:
        with open("test_config.json", "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
        _clear_config_cache()

    def test_enabled_config_loading(self):
        """测试启用多租户的配置加载"""
        self._write_config(_build_config(tenant_targets=["t001", "t002"]))

        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled

        config = get_multi_tenant_config()

        self.assertTrue(config["enabled"])
        self.assertTrue(is_multi_tenant_enabled())
        self.assertEqual(config["default_tenant"], "autotest")
        self.assertEqual(set(config["tenants"].keys()), {"autotest", "t001", "t002"})

        logger.info("启用多租户配置加载测试通过")

    def test_concurrent_tenant_config_generation(self):
        """测试租户地址由模板自动生成"""
        self._write_config(
            _build_config(
                tenant_targets=["t001", "t002", "t003", "t004", "t005"],
                tenant_url_template="https://{tenant}.remote.vpc",
                default_server_url="https://autotest.remote.vpc",
            )
        )

        from tenant_config_helper import (get_concurrent_tenant_configs,
                                          get_concurrent_tenant_ids,
                                          get_preferred_concurrent_tenant_ids)

        preferred_ids = get_preferred_concurrent_tenant_ids()
        self.assertEqual(preferred_ids, ["t001", "t002", "t003", "t004", "t005"])

        tenant_ids = get_concurrent_tenant_ids()
        self.assertEqual(tenant_ids, preferred_ids)

        tenant_configs = get_concurrent_tenant_configs()
        self.assertEqual(set(tenant_configs.keys()), set(preferred_ids))
        self.assertEqual(
            tenant_configs["t001"]["server_url"], "https://t001.remote.vpc"
        )
        self.assertEqual(tenant_configs["t003"]["namespace"], "")
        self.assertEqual(tenant_configs["t005"]["username"], "administrator")

        logger.info("并发租户配置生成测试通过")

    def test_disabled_config_loading(self):
        """测试未配置目标租户时多租户关闭"""
        self._write_config(_build_config(tenant_targets=[], mode="single_tenant"))

        from tenant_config_helper import (get_multi_tenant_config, get_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertFalse(config["enabled"])
        self.assertFalse(is_multi_tenant_enabled())
        self.assertEqual(list(config["tenants"].keys()), ["autotest"])
        self.assertIsNone(get_tenant_config("t001"))

        logger.info("禁用多租户配置加载测试通过")


class TestMultiTenantIntegration(unittest.TestCase):
    """多租户集成测试"""

    @patch("session_manager.SessionManager")
    def test_manager_with_config(self, MockSessionManager):
        """测试多租户管理器与配置集成"""
        from multi_tenant_manager import MultiTenantSessionManager

        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session

        test_config = {
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
                "enabled": True,
            },
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
                "enabled": False,
            },
        }

        mt_manager = MultiTenantSessionManager(test_config)

        self.assertEqual(len(mt_manager.session_managers), 2)
        self.assertIn("autotest", mt_manager.session_managers)
        self.assertIn("tenant1", mt_manager.session_managers)
        self.assertNotIn("tenant2", mt_manager.session_managers)

        logger.info("多租户管理器与配置集成测试通过")


def run_multi_tenant_tests():
    """运行所有多租户测试"""
    logger.info("=" * 60)
    logger.info("VMI 多租户测试")
    logger.info("=" * 60)

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_class in [
        TestMultiTenantCore,
        TestMultiTenantConfig,
        TestMultiTenantIntegration,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(test_class))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    logger.info("=" * 60)
    logger.info("测试结果摘要")
    logger.info("=" * 60)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)

    logger.info("运行测试数: %s", total)
    logger.info("通过数: %s", passed)
    logger.info("失败数: %s", len(result.failures))
    logger.info("错误数: %s", len(result.errors))

    if result.wasSuccessful():
        logger.info("所有多租户测试通过")
        return True

    logger.error("部分测试失败")
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_multi_tenant_tests()
    exit(0 if success else 1)
