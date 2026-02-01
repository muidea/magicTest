#!/usr/bin/env python3
"""
VMI多租户测试框架最终验证测试
不依赖网络连接，验证所有核心功能
"""

import unittest
import json
import os
from unittest.mock import Mock, patch, MagicMock


class TestConfigurationSystem(unittest.TestCase):
    """测试配置系统"""
    
    def test_existing_config_loading(self):
        """测试现有配置文件加载"""
        config_path = "test_config.json"
        self.assertTrue(os.path.exists(config_path), "现有配置文件不存在")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # 验证必要字段
        required_fields = ["server_url", "username", "password", "namespace"]
        for field in required_fields:
            self.assertIn(field, config, f"配置文件缺少字段: {field}")
        
        print("✅ 现有配置文件加载测试通过")
    
    def test_multi_tenant_config_extension(self):
        """测试多租户配置扩展"""
        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
        
        config = get_multi_tenant_config()
        
        # 验证配置结构
        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        
        # 验证默认禁用
        self.assertFalse(config["enabled"])
        self.assertFalse(is_multi_tenant_enabled())
        
        # 验证包含autotest租户
        self.assertIn("autotest", config["tenants"])
        
        print("✅ 多租户配置扩展测试通过")
    
    def test_config_template(self):
        """测试配置模板"""
        template_path = "test_config_multi_tenant_template.json"
        self.assertTrue(os.path.exists(template_path), "配置模板不存在")
        
        with open(template_path, 'r') as f:
            template = json.load(f)
        
        # 验证模板结构
        self.assertIn("multi_tenant", template)
        mt_config = template["multi_tenant"]
        
        self.assertIn("enabled", mt_config)
        self.assertIn("default_tenant", mt_config)
        self.assertIn("tenants", mt_config)
        
        # 验证默认禁用
        self.assertFalse(mt_config["enabled"])
        
        # 验证包含autotest租户
        tenant_ids = [t["id"] for t in mt_config["tenants"]]
        self.assertIn("autotest", tenant_ids)
        
        print("✅ 配置模板测试通过")


class TestMultiTenantManager(unittest.TestCase):
    """测试多租户管理器"""
    
    @patch('session_manager.SessionManager')
    def test_manager_creation(self, MockSessionManager):
        """测试管理器创建"""
        from multi_tenant_manager import MultiTenantSessionManager
        
        # 配置模拟的SessionManager
        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session
        
        # 创建测试配置
        test_config = {
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
                "enabled": True
            }
        }
        
        # 创建管理器
        mt_manager = MultiTenantSessionManager(test_config)
        
        # 验证管理器结构
        self.assertEqual(len(mt_manager.session_managers), 2)
        self.assertIn("tenant1", mt_manager.session_managers)
        self.assertIn("tenant2", mt_manager.session_managers)
        
        # 验证获取会话管理器
        session_mgr1 = mt_manager.get_session_manager("tenant1")
        session_mgr2 = mt_manager.get_session_manager("tenant2")
        self.assertIsNotNone(session_mgr1)
        self.assertIsNotNone(session_mgr2)
        
        # 验证获取不存在的租户
        self.assertIsNone(mt_manager.get_session_manager("nonexistent"))
        
        print("✅ 多租户管理器创建测试通过")
    
    @patch('session_manager.SessionManager')
    def test_sdk_factory(self, MockSessionManager):
        """测试SDK工厂"""
        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory
        
        # 配置模拟的SessionManager
        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock(name="mock_session")
        MockSessionManager.return_value = mock_session
        
        # 创建测试配置
        test_config = {
            "tenant1": {
                "server_url": "https://tenant1.local.vpc",
                "username": "admin1",
                "password": "password1",
                "namespace": "tenant1",
                "enabled": True
            }
        }
        
        # 创建管理器和SDK工厂
        mt_manager = MultiTenantSessionManager(test_config)
        sdk_factory = SDKFactory(mt_manager)
        
        # 定义测试SDK类
        class TestSDK:
            def __init__(self, session):
                self.session = session
                self.name = "TestSDK"
        
        # 测试获取SDK实例
        sdk1 = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        self.assertIsNotNone(sdk1)
        self.assertEqual(sdk1.name, "TestSDK")
        
        # 测试缓存功能
        sdk2 = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        self.assertIs(sdk1, sdk2)  # 应该是同一个实例
        
        # 测试清理缓存
        sdk_factory.clear_cache("tenant1")
        sdk3 = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        self.assertIsNot(sdk1, sdk3)  # 应该是新实例
        
        print("✅ SDK工厂测试通过")


class TestTestBaseClasses(unittest.TestCase):
    """测试测试基类"""
    
    def test_inheritance(self):
        """测试继承关系"""
        from test_base_with_session_manager import TestBaseWithSessionManager
        from test_base_multi_tenant import TestBaseMultiTenant
        
        # 验证继承关系
        self.assertTrue(issubclass(TestBaseMultiTenant, TestBaseWithSessionManager))
        
        print("✅ 测试基类继承关系测试通过")
    
    def test_multi_tenant_methods(self):
        """测试多租户方法"""
        from test_base_multi_tenant import TestBaseMultiTenant
        
        # 检查关键方法是否存在
        required_methods = [
            'switch_tenant',
            'get_sdk_for_current_tenant',
            'get_sdk_for_tenant',
            'run_for_tenant',
            'run_for_all_tenants',
            'execute_with_tenant_session_check',
            'get_tenant_status',
            'get_all_tenant_status',
            'assert_tenant_isolation'
        ]
        
        for method in required_methods:
            self.assertTrue(hasattr(TestBaseMultiTenant, method),
                          f"TestBaseMultiTenant缺少方法: {method}")
        
        print("✅ 多租户方法测试通过")


class TestBackwardCompatibility(unittest.TestCase):
    """测试向后兼容性"""
    
    def test_existing_tests_unchanged(self):
        """测试现有测试未受影响"""
        # 检查现有测试文件是否仍然可以导入
        try:
            from test_base_with_session_manager import TestBaseWithSessionManager
            from session_manager import SessionManager
            from config_helper import get_config
            
            print("✅ 现有模块导入正常")
        except ImportError as e:
            self.fail(f"现有模块导入失败: {e}")
    
    def test_multi_tenant_disabled_by_default(self):
        """测试多租户默认禁用"""
        from tenant_config_helper import is_multi_tenant_enabled
        
        # 多租户应该默认禁用
        self.assertFalse(is_multi_tenant_enabled())
        
        print("✅ 多租户默认禁用测试通过")


class TestDocumentation(unittest.TestCase):
    """测试文档"""
    
    def test_readme_exists(self):
        """测试README文档存在"""
        readme_path = "MULTI_TENANT_README.md"
        self.assertTrue(os.path.exists(readme_path), "多租户README文档不存在")
        
        with open(readme_path, 'r') as f:
            content = f.read()
        
        # 验证关键内容
        required_sections = [
            "概述",
            "核心组件",
            "使用方法",
            "配置说明",
            "向后兼容性"
        ]
        
        for section in required_sections:
            self.assertIn(section, content, f"README缺少章节: {section}")
        
        print("✅ 文档测试通过")


class TestExampleCode(unittest.TestCase):
    """测试示例代码"""
    
    def test_example_files_exist(self):
        """测试示例文件存在"""
        example_files = [
            "test_multi_tenant_example.py",
            "test_config_multi_tenant_template.json"
        ]
        
        for file in example_files:
            self.assertTrue(os.path.exists(file), f"示例文件不存在: {file}")
        
        print("✅ 示例文件测试通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("VMI多租户测试框架 - 最终验证测试")
    print("=" * 60)
    
    # 加载测试套件
    loader = unittest.TestLoader()
    
    # 添加所有测试类
    test_classes = [
        TestConfigurationSystem,
        TestMultiTenantManager,
        TestTestBaseClasses,
        TestBackwardCompatibility,
        TestDocumentation,
        TestExampleCode
    ]
    
    suite = unittest.TestSuite()
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出详细结果
    print("\n" + "=" * 60)
    print("测试结果摘要")
    print("=" * 60)
    
    total_tests = result.testsRun
    passed_tests = total_tests - len(result.failures) - len(result.errors)
    
    print(f"总测试数: {total_tests}")
    print(f"通过数: {passed_tests}")
    print(f"失败数: {len(result.failures)}")
    print(f"错误数: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n🎉 所有测试通过！VMI多租户测试框架验证完成。")
        
        print("\n" + "=" * 60)
        print("框架功能验证清单")
        print("=" * 60)
        print("✅ 1. 配置系统向后兼容")
        print("✅ 2. 多租户配置扩展正常")
        print("✅ 3. 多租户管理器功能完整")
        print("✅ 4. SDK工厂工作正常")
        print("✅ 5. 测试基类继承关系正确")
        print("✅ 6. 多租户方法完整")
        print("✅ 7. 向后兼容性保证")
        print("✅ 8. 文档完整")
        print("✅ 9. 示例代码完整")
        
        print("\n" + "=" * 60)
        print("下一步操作指南")
        print("=" * 60)
        print("1. 启用多租户测试:")
        print("   cp test_config_multi_tenant_template.json test_config.json")
        print("   # 编辑test_config.json，设置multi_tenant.enabled=true")
        print("   # 配置实际的租户服务器地址和认证信息")
        
        print("\n2. 编写多租户测试:")
        print("   参考 test_multi_tenant_example.py")
        print("   使用 TestBaseMultiTenant 作为测试基类")
        
        print("\n3. 运行多租户测试:")
        print("   python3 -m unittest test_multi_tenant_example.py")
        print("   # 或使用现有测试运行器")
        print("   python3 run_all_tests.py --basic")
        
        print("\n4. 验证租户隔离性:")
        print("   使用 assert_tenant_isolation 方法")
        print("   验证不同租户的数据互相不可见")
        
        return True
    else:
        print("\n❌ 测试失败，需要修复以下问题:")
        
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
    success = run_all_tests()
    exit(0 if success else 1)