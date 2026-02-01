#!/usr/bin/env python3
"""
多租户配置验证测试
验证多租户配置的加载和使用
"""

import unittest
import json
import os
import tempfile
from unittest.mock import patch, Mock


class TestMultiTenantConfigValidation(unittest.TestCase):
    """测试多租户配置验证"""
    
    def test_enabled_config_loading(self):
        """测试启用多租户的配置加载"""
        # 备份原始配置文件
        original_config_exists = os.path.exists("test_config.json")
        if original_config_exists:
            with open("test_config.json", "r") as f:
                original_config = f.read()
        
        try:
            # 创建启用多租户的配置文件
            config_content = {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
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
                            "enabled": True
                        },
                        {
                            "id": "tenant1",
                            "server_url": "https://tenant1.local.vpc",
                            "username": "admin1",
                            "password": "password1",
                            "namespace": "tenant1",
                            "enabled": True
                        }
                    ]
                }
            }
            
            # 写入配置文件
            with open("test_config.json", "w") as f:
                json.dump(config_content, f, indent=2)
            
            # 清除配置缓存并重新导入
            import sys
            if 'config_helper' in sys.modules:
                del sys.modules['config_helper']
            if 'tenant_config_helper' in sys.modules:
                del sys.modules['tenant_config_helper']
            
            # 重新导入配置模块
            import config_helper
            import tenant_config_helper
            
            # 测试配置加载
            from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
            
            config = get_multi_tenant_config()
            
            # 验证配置
            self.assertTrue(config["enabled"])
            self.assertEqual(config["default_tenant"], "autotest")
            self.assertEqual(len(config["tenants"]), 2)
            
            # 验证租户列表
            tenant_ids = list(config["tenants"].keys())
            self.assertIn("autotest", tenant_ids)
            self.assertIn("tenant1", tenant_ids)
            
            # 验证启用状态
            self.assertTrue(is_multi_tenant_enabled())
            
            print("✅ 启用多租户配置加载测试通过")
            
        finally:
            # 恢复原始配置文件
            if original_config_exists:
                with open("test_config.json", "w") as f:
                    f.write(original_config)
            else:
                os.remove("test_config.json")
    
    def test_disabled_config_loading(self):
        """测试禁用多租户的配置加载"""
        # 备份原始配置文件
        original_config_exists = os.path.exists("test_config.json")
        if original_config_exists:
            with open("test_config.json", "r") as f:
                original_config = f.read()
        
        try:
            # 创建禁用多租户的配置文件
            config_content = {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
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
                            "enabled": True
                        }
                    ]
                }
            }
            
            # 写入配置文件
            with open("test_config.json", "w") as f:
                json.dump(config_content, f, indent=2)
            
            # 清除配置缓存并重新导入
            import sys
            if 'config_helper' in sys.modules:
                del sys.modules['config_helper']
            if 'tenant_config_helper' in sys.modules:
                del sys.modules['tenant_config_helper']
            
            # 重新导入配置模块
            import config_helper
            import tenant_config_helper
            
            # 测试配置加载
            from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
            
            config = get_multi_tenant_config()
            
            # 验证配置
            self.assertFalse(config["enabled"])
            self.assertEqual(config["default_tenant"], "autotest")
            
            # 验证启用状态
            self.assertFalse(is_multi_tenant_enabled())
            
            print("✅ 禁用多租户配置加载测试通过")
            
        finally:
            # 恢复原始配置文件
            if original_config_exists:
                with open("test_config.json", "w") as f:
                    f.write(original_config)
            else:
                os.remove("test_config.json")
    
    def test_backward_compatibility(self):
        """测试向后兼容性 - 无multi_tenant字段的配置"""
        # 备份原始配置文件
        original_config_exists = os.path.exists("test_config.json")
        if original_config_exists:
            with open("test_config.json", "r") as f:
                original_config = f.read()
        
        try:
            # 创建无multi_tenant字段的配置文件（向后兼容）
            config_content = {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest"
            }
            
            # 写入配置文件
            with open("test_config.json", "w") as f:
                json.dump(config_content, f, indent=2)
            
            # 清除配置缓存并重新导入
            import sys
            if 'config_helper' in sys.modules:
                del sys.modules['config_helper']
            if 'tenant_config_helper' in sys.modules:
                del sys.modules['tenant_config_helper']
            
            # 重新导入配置模块
            import config_helper
            import tenant_config_helper
            
            # 测试配置加载
            from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
            
            config = get_multi_tenant_config()
            
            # 验证配置
            self.assertFalse(config["enabled"])
            self.assertEqual(config["default_tenant"], "autotest")
            self.assertEqual(len(config["tenants"]), 1)
            
            # 验证autotest租户配置
            autotest_tenant = config["tenants"]["autotest"]
            self.assertEqual(autotest_tenant["server_url"], "https://autotest.local.vpc")
            self.assertEqual(autotest_tenant["username"], "administrator")
            self.assertEqual(autotest_tenant["namespace"], "autotest")
            
            # 验证启用状态
            self.assertFalse(is_multi_tenant_enabled())
            
            print("✅ 向后兼容性测试通过")
            
        finally:
            # 恢复原始配置文件
            if original_config_exists:
                with open("test_config.json", "w") as f:
                    f.write(original_config)
            else:
                os.remove("test_config.json")


class TestMultiTenantManagerWithConfig(unittest.TestCase):
    """测试多租户管理器与配置集成"""
    
    @patch('session_manager.SessionManager')
    def test_manager_with_enabled_config(self, MockSessionManager):
        """测试启用多租户配置的管理器"""
        from multi_tenant_manager import MultiTenantSessionManager
        
        # 配置模拟的SessionManager
        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session
        
        # 创建测试配置（启用多租户）
        test_config = {
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
                "enabled": True
            },
            "tenant1": {
                "server_url": "https://tenant1.local.vpc",
                "username": "admin1",
                "password": "password1",
                "namespace": "tenant1",
                "enabled": True
            }
        }
        
        # 创建管理器
        mt_manager = MultiTenantSessionManager(test_config)
        
        # 验证管理器结构
        self.assertEqual(len(mt_manager.session_managers), 2)
        self.assertIn("autotest", mt_manager.session_managers)
        self.assertIn("tenant1", mt_manager.session_managers)
        
        # 验证获取会话管理器
        autotest_mgr = mt_manager.get_session_manager("autotest")
        tenant1_mgr = mt_manager.get_session_manager("tenant1")
        self.assertIsNotNone(autotest_mgr)
        self.assertIsNotNone(tenant1_mgr)
        
        print("✅ 启用多租户配置的管理器测试通过")
    
    @patch('session_manager.SessionManager')
    def test_manager_with_disabled_tenant(self, MockSessionManager):
        """测试包含禁用租户的配置"""
        from multi_tenant_manager import MultiTenantSessionManager
        
        # 配置模拟的SessionManager
        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session
        
        # 创建测试配置（包含禁用租户）
        test_config = {
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
                "enabled": True
            },
            "tenant1": {
                "server_url": "https://tenant1.local.vpc",
                "username": "admin1",
                "password": "password1",
                "namespace": "tenant1",
                "enabled": True
            },
            "tenant2": {
                "server_url": "https://tenant2.local.vpc",
                "username": "admin2",
                "password": "password2",
                "namespace": "tenant2",
                "enabled": False  # 禁用租户
            }
        }
        
        # 创建管理器
        mt_manager = MultiTenantSessionManager(test_config)
        
        # 验证管理器结构（只包含启用的租户）
        self.assertEqual(len(mt_manager.session_managers), 2)  # 只有2个启用的租户
        self.assertIn("autotest", mt_manager.session_managers)
        self.assertIn("tenant1", mt_manager.session_managers)
        self.assertNotIn("tenant2", mt_manager.session_managers)  # 禁用的租户不应该被创建
        
        print("✅ 包含禁用租户的配置测试通过")


def run_validation_tests():
    """运行验证测试"""
    print("=" * 60)
    print("多租户配置验证测试")
    print("=" * 60)
    
    # 加载测试套件
    loader = unittest.TestLoader()
    
    # 添加所有测试类
    test_classes = [
        TestMultiTenantConfigValidation,
        TestMultiTenantManagerWithConfig
    ]
    
    suite = unittest.TestSuite()
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("验证测试结果")
    print("=" * 60)
    
    if result.wasSuccessful():
        print("🎉 所有验证测试通过！多租户配置系统工作正常。")
        
        print("\n" + "=" * 60)
        print("配置系统验证清单")
        print("=" * 60)
        print("✅ 1. 启用多租户配置加载正常")
        print("✅ 2. 禁用多租户配置加载正常")
        print("✅ 3. 向后兼容性保证")
        print("✅ 4. 多租户管理器与配置集成正常")
        print("✅ 5. 禁用租户正确处理")
        
        print("\n" + "=" * 60)
        print("实际使用指南")
        print("=" * 60)
        print("1. 启用多租户测试:")
        print("   cp test_config_multi_tenant_enabled.json test_config.json")
        print("   # 或编辑现有test_config.json，添加multi_tenant配置")
        
        print("\n2. 配置说明:")
        print("   - multi_tenant.enabled: true/false (启用/禁用多租户)")
        print("   - multi_tenant.default_tenant: 默认租户ID")
        print("   - multi_tenant.tenants: 租户列表")
        print("     - id: 租户唯一标识")
        print("     - server_url: 租户服务器地址")
        print("     - username/password: 认证信息")
        print("     - namespace: 命名空间")
        print("     - enabled: 是否启用该租户")
        
        print("\n3. 示例配置:")
        print("   test_config_multi_tenant_enabled.json - 启用多租户")
        print("   test_config_multi_tenant_enabled_simple.json - 简化版")
        
        return True
    else:
        print("\n❌ 验证测试失败，需要修复以下问题:")
        
        if result.failures:
            print("\n失败详情:")
            for test, traceback in result.failures:
                test_name = str(test).split()[0]
                print(f"  {test_name}: {traceback.splitlines()[-1]}")
        
        if result.errors:
            print("\n错误详情:")
            for test, traceback in result.errors:
                test_name = str(test).split()[0]
                print(f"  {test_name}: {traceback.splitlines()[-1]}")
        
        return False


if __name__ == '__main__':
    success = run_validation_tests()
    exit(0 if success else 1)