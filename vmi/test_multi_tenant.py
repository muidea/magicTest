#!/usr/bin/env python3
"""
VMI 多租户测试
整合核心功能测试和配置验证测试，无需网络连接

包含测试类：
- TestMultiTenantCore：核心功能测试
- TestMultiTenantConfig：配置验证测试
"""

import json
import logging
import os
import unittest
from unittest.mock import Mock, patch

logger = logging.getLogger(__name__)


class TestMultiTenantCore(unittest.TestCase):
    """多租户核心功能测试"""

    def test_config_helper(self):
        """测试配置助手核心逻辑"""
        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        self.assertIn("autotest", config["tenants"])
        self.assertFalse(config["enabled"])
        self.assertFalse(is_multi_tenant_enabled())

        print("✅ 配置助手核心逻辑测试通过")

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
            sdk2 = sdk_factory.get_sdk_for_tenant("autotest", MockSDK)
            self.assertIs(sdk, sdk2)

            print("✅ 多租户管理器结构测试通过")

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

        print("✅ 测试基类继承关系测试通过")

    def test_backward_compatibility(self):
        """测试向后兼容性"""
        config_path = "test_config.json"
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = json.load(f)

            self.assertIn("server", config)

            print("✅ 向后兼容性测试通过")
        else:
            print("⚠️ 配置文件不存在，跳过测试")


class TestMultiTenantConfig(unittest.TestCase):
    """多租户配置验证测试"""

    def setUp(self):
        """备份原始配置"""
        self.original_config_exists = os.path.exists("test_config.json")
        if self.original_config_exists:
            with open("test_config.json", "r") as f:
                self.original_config = f.read()

    def tearDown(self):
        """恢复原始配置"""
        if self.original_config_exists:
            with open("test_config.json", "w") as f:
                f.write(self.original_config)
        elif os.path.exists("test_config.json"):
            os.remove("test_config.json")

    def _clear_config_cache(self):
        """清除配置缓存"""
        import sys

        for module in ["config_helper", "tenant_config_helper"]:
            if module in sys.modules:
                del sys.modules[module]

    def test_enabled_config_loading(self):
        """测试启用多租户的配置加载"""
        config_content = {
            "server": {
                "url": "https://test.local.vpc",
                "namespace": "test",
                "environment": "test",
            },
            "credentials": {"username": "admin", "password": "admin"},
            "session": {"refresh_interval": 540, "timeout": 1800},
            "multi_tenant": {
                "enabled": True,
                "default_tenant": "autotest",
                "tenants": [
                    {
                        "id": "autotest",
                        "server_url": "https://autotest.local.vpc",
                        "username": "administrator",
                        "password": "administrator",
                        "namespace": "autotest",
                        "enabled": True,
                    }
                ],
            },
        }

        with open("test_config.json", "w") as f:
            json.dump(config_content, f, indent=2)

        self._clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertTrue(config["enabled"])
        self.assertTrue(is_multi_tenant_enabled())

        print("✅ 启用多租户配置加载测试通过")

    def test_disabled_config_loading(self):
        """测试禁用多租户的配置加载"""
        config_content = {
            "server": {
                "url": "https://test.local.vpc",
                "namespace": "test",
                "environment": "test",
            },
            "credentials": {"username": "admin", "password": "admin"},
            "session": {"refresh_interval": 540, "timeout": 1800},
            "multi_tenant": {
                "enabled": False,
                "default_tenant": "autotest",
                "tenants": [
                    {
                        "id": "autotest",
                        "server_url": "https://autotest.local.vpc",
                        "username": "administrator",
                        "password": "administrator",
                        "namespace": "autotest",
                        "enabled": True,
                    }
                ],
            },
        }

        with open("test_config.json", "w") as f:
            json.dump(config_content, f, indent=2)

        self._clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertFalse(config["enabled"])
        self.assertFalse(is_multi_tenant_enabled())

        print("✅ 禁用多租户配置加载测试通过")


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

        print("✅ 多租户管理器与配置集成测试通过")


def run_multi_tenant_tests():
    """运行所有多租户测试"""
    print("=" * 60)
    print("VMI 多租户测试")
    print("=" * 60)

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

    print("\n" + "=" * 60)
    print("测试结果摘要")
    print("=" * 60)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)

    print(f"运行测试数: {total}")
    print(f"通过数: {passed}")
    print(f"失败数: {len(result.failures)}")
    print(f"错误数: {len(result.errors)}")

    if result.wasSuccessful():
        print("\n✅ 所有多租户测试通过！")
        return True
    else:
        print("\n❌ 部分测试失败")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    success = run_multi_tenant_tests()
    exit(0 if success else 1)
