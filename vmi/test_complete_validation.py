#!/usr/bin/env python3
"""
VMI 测试框架 - 完整验证测试
验证核心功能，无需网络连接
"""

import json
import os
import unittest
from unittest.mock import Mock, patch


class TestFrameworkValidation(unittest.TestCase):
    """框架验证测试"""

    def test_config_system(self):
        """测试配置系统"""
        print("\n🔧 测试配置系统")

        self.assertTrue(os.path.exists("test_config.json"), "配置文件不存在")

        with open("test_config.json", "r") as f:
            config = json.load(f)

        self.assertIn("server", config, "配置缺少server字段")
        self.assertIn("credentials", config, "配置缺少credentials字段")

        print("✅ 配置系统测试通过")

    def test_module_imports(self):
        """测试模块导入"""
        print("\n📦 测试模块导入")

        try:
            from multi_tenant_manager import (MultiTenantSessionManager,
                                              SDKFactory)
            from tenant_config_helper import (get_multi_tenant_config,
                                              is_multi_tenant_enabled)
            from test_base_multi_tenant import TestBaseMultiTenant

            print("✅ 核心模块导入成功")
        except ImportError as e:
            self.fail(f"核心模块导入失败: {e}")

        try:
            from config_helper import get_config
            from session_manager import SessionManager
            from test_base_with_session_manager import (
                ConcurrentTestMixin, PerformanceMonitor,
                TestBaseWithSessionManager)

            print("✅ 基础模块导入成功")
        except ImportError as e:
            self.fail(f"基础模块导入失败: {e}")

        print("✅ 模块导入测试通过")

    def test_config_helpers(self):
        """测试配置助手"""
        print("\n⚙️ 测试配置助手")

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        self.assertFalse(config["enabled"])
        self.assertFalse(is_multi_tenant_enabled())
        self.assertIn("autotest", config["tenants"])

        print("✅ 配置助手测试通过")

    @patch("session_manager.SessionManager")
    def test_multi_tenant_manager(self, MockSessionManager):
        """测试多租户管理器"""
        print("\n🏢 测试多租户管理器")

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

        print("✅ 多租户管理器测试通过")

    def test_base_classes(self):
        """测试测试基类"""
        print("\n🧪 测试测试基类")

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

        print("✅ 测试基类测试通过")

    def test_backward_compatibility(self):
        """测试向后兼容性"""
        print("\n🔄 测试向后兼容性")

        test_files = ["scenario_test.py", "aging_test_simple.py", "run_tests.py"]

        for test_file in test_files:
            self.assertTrue(os.path.exists(test_file), f"测试文件不存在: {test_file}")

        from tenant_config_helper import is_multi_tenant_enabled

        self.assertFalse(is_multi_tenant_enabled())

        print("✅ 向后兼容性测试通过")

    def test_test_runner(self):
        """测试运行器"""
        print("\n🚀 测试运行器")

        self.assertTrue(os.path.exists("run_tests.py"), "统一测试入口不存在")

        with open("run_tests.py", "r") as f:
            content = f.read()

        self.assertIn("def run_", content)
        self.assertIn("--validation", content)
        self.assertIn("--multi-tenant", content)
        self.assertIn("--quick", content)
        self.assertIn("--all", content)

        print("✅ 测试运行器测试通过")

    def test_integration(self):
        """测试集成"""
        print("\n🔗 测试集成")

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

            print("✅ 集成测试通过")
        except Exception as e:
            self.fail(f"集成测试失败: {e}")


def run_validation():
    """运行验证测试"""
    print("=" * 60)
    print("VMI 测试框架 - 验证测试")
    print("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFrameworkValidation)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print("验证结果摘要")
    print("=" * 60)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)

    print(f"总测试数: {total}")
    print(f"通过数: {passed}")
    print(f"失败数: {len(result.failures)}")

    if result.wasSuccessful():
        print("\n🎉 所有验证测试通过！")
        print("\n框架验证清单：")
        print("✅ 1. 配置系统正常")
        print("✅ 2. 模块导入正常")
        print("✅ 3. 配置助手正常")
        print("✅ 4. 多租户管理器正常")
        print("✅ 5. 测试基类正常")
        print("✅ 6. 向后兼容性保证")
        print("✅ 7. 测试运行器正常")
        print("✅ 8. 集成测试正常")
        return True
    else:
        print("\n❌ 部分测试失败")
        if result.failures:
            for test, traceback in result.failures:
                print(f"  失败: {test}")
        if result.errors:
            for test, traceback in result.errors:
                print(f"  错误: {test}")
        return False


if __name__ == "__main__":
    success = run_validation()
    exit(0 if success else 1)
