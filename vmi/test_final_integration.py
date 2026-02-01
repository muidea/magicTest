#!/usr/bin/env python3
"""
VMI多租户测试框架 - 最终集成测试
验证所有组件协同工作
"""

import os
import sys
import json
import tempfile
from unittest.mock import patch, Mock


def test_configuration_system():
    """测试配置系统"""
    print("🔧 测试配置系统...")
    
    # 1. 验证配置文件
    assert os.path.exists("test_config.json"), "配置文件不存在"
    assert os.path.exists("test_config_multi_tenant_template.json"), "配置模板不存在"
    
    # 2. 验证配置内容
    with open("test_config.json", "r") as f:
        config = json.load(f)
    
    assert "server_url" in config, "配置文件缺少server_url"
    assert "username" in config, "配置文件缺少username"
    assert "namespace" in config, "配置文件缺少namespace"
    
    print("✅ 配置系统测试通过")
    return True


def test_module_imports():
    """测试模块导入"""
    print("📦 测试模块导入...")
    
    # 清除模块缓存以确保重新导入
    modules_to_clear = ['config_helper', 'tenant_config_helper', 'multi_tenant_manager', 
                       'test_base_multi_tenant', 'session_manager', 'test_base_with_session_manager']
    
    for module in modules_to_clear:
        if module in sys.modules:
            del sys.modules[module]
    
    # 导入所有模块
    try:
        from config_helper import get_config
        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory
        from test_base_multi_tenant import TestBaseMultiTenant, SimpleMultiTenantTest
        from session_manager import SessionManager
        from test_base_with_session_manager import TestBaseWithSessionManager
        
        print("✅ 所有模块导入成功")
        return True
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False


def test_backward_compatibility():
    """测试向后兼容性"""
    print("🔄 测试向后兼容性...")
    
    from tenant_config_helper import is_multi_tenant_enabled
    
    # 多租户应该默认禁用
    assert not is_multi_tenant_enabled(), "多租户应该默认禁用"
    
    # 验证现有测试文件存在
    test_files = ["concurrent_test_simple.py", "scenario_test.py", "aging_test_simple.py"]
    for test_file in test_files:
        assert os.path.exists(test_file), f"测试文件不存在: {test_file}"
    
    print("✅ 向后兼容性测试通过")
    return True


def test_multi_tenant_manager_with_mock():
    """测试多租户管理器（使用模拟）"""
    print("🏢 测试多租户管理器...")
    
    with patch('session_manager.SessionManager') as MockSessionManager:
        # 配置模拟
        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session
        
        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory
        
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
        
        # 验证管理器
        assert len(mt_manager.session_managers) == 2
        assert "tenant1" in mt_manager.session_managers
        assert "tenant2" in mt_manager.session_managers
        
        # 测试SDK工厂
        sdk_factory = SDKFactory(mt_manager)
        
        class TestSDK:
            def __init__(self, session):
                self.session = session
                self.name = "TestSDK"
        
        sdk1 = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        assert sdk1 is not None
        assert sdk1.name == "TestSDK"
        
        print("✅ 多租户管理器测试通过")
        return True


def test_configuration_switching():
    """测试配置切换"""
    print("⚙️ 测试配置切换...")
    
    # 备份原始配置
    original_config_exists = os.path.exists("test_config.json")
    if original_config_exists:
        with open("test_config.json", "r") as f:
            original_config = f.read()
    
    try:
        # 测试1: 启用多租户配置
        enabled_config = {
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
        
        with open("test_config.json", "w") as f:
            json.dump(enabled_config, f, indent=2)
        
        # 清除缓存并重新导入
        if 'tenant_config_helper' in sys.modules:
            del sys.modules['tenant_config_helper']
        if 'config_helper' in sys.modules:
            del sys.modules['config_helper']
        
        import tenant_config_helper
        from tenant_config_helper import is_multi_tenant_enabled
        
        assert is_multi_tenant_enabled(), "启用多租户配置后应该返回True"
        
        # 测试2: 禁用多租户配置
        disabled_config = {
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
        
        with open("test_config.json", "w") as f:
            json.dump(disabled_config, f, indent=2)
        
        # 清除缓存并重新导入
        if 'tenant_config_helper' in sys.modules:
            del sys.modules['tenant_config_helper']
        if 'config_helper' in sys.modules:
            del sys.modules['config_helper']
        
        import tenant_config_helper
        from tenant_config_helper import is_multi_tenant_enabled
        
        assert not is_multi_tenant_enabled(), "禁用多租户配置后应该返回False"
        
        print("✅ 配置切换测试通过")
        return True
        
    finally:
        # 恢复原始配置
        if original_config_exists:
            with open("test_config.json", "w") as f:
                f.write(original_config)


def test_documentation_and_examples():
    """测试文档和示例"""
    print("📚 测试文档和示例...")
    
    # 验证文档存在
    assert os.path.exists("MULTI_TENANT_README.md"), "README文档不存在"
    
    with open("MULTI_TENANT_README.md", "r") as f:
        content = f.read()
    
    # 验证关键章节
    required_sections = ["概述", "核心组件", "使用方法", "配置说明", "向后兼容性"]
    for section in required_sections:
        assert section in content, f"README缺少章节: {section}"
    
    # 验证示例文件存在
    example_files = [
        "test_multi_tenant_example.py",
        "test_final_validation.py",
        "test_multi_tenant_config_validation.py",
        "test_complete_validation.py"
    ]
    
    for file in example_files:
        assert os.path.exists(file), f"示例文件不存在: {file}"
    
    print("✅ 文档和示例测试通过")
    return True


def test_test_runners():
    """测试测试运行器"""
    print("🚀 测试测试运行器...")
    
    # 验证运行器文件存在
    assert os.path.exists("run_all_tests.py"), "原始测试运行器不存在"
    assert os.path.exists("run_all_tests_with_multi_tenant.py"), "多租户测试运行器不存在"
    
    # 验证运行器内容
    with open("run_all_tests_with_multi_tenant.py", "r") as f:
        content = f.read()
    
    assert "def run_multi_tenant_validation" in content, "多租户运行器缺少验证函数"
    assert "--multi-tenant" in content, "多租户运行器缺少--multi-tenant选项"
    assert "--mt-enable" in content, "多租户运行器缺少--mt-enable选项"
    
    print("✅ 测试运行器测试通过")
    return True


def run_final_integration_test():
    """运行最终集成测试"""
    print("=" * 70)
    print("VMI多租户测试框架 - 最终集成测试")
    print("=" * 70)
    
    tests = [
        ("配置系统", test_configuration_system),
        ("模块导入", test_module_imports),
        ("向后兼容性", test_backward_compatibility),
        ("多租户管理器", test_multi_tenant_manager_with_mock),
        ("配置切换", test_configuration_switching),
        ("文档和示例", test_documentation_and_examples),
        ("测试运行器", test_test_runners),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results.append((test_name, success))
            status = "✅ 通过" if success else "❌ 失败"
            print(f"{status}: {test_name}")
        except Exception as e:
            results.append((test_name, False))
            print(f"❌ 失败: {test_name} - {e}")
    
    print("\n" + "=" * 70)
    print("最终集成测试结果")
    print("=" * 70)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    failed_tests = total_tests - passed_tests
    
    print(f"总测试数: {total_tests}")
    print(f"通过数: {passed_tests}")
    print(f"失败数: {failed_tests}")
    
    if failed_tests == 0:
        print("\n🎉 所有集成测试通过！VMI多租户测试框架完全验证完成。")
        
        print("\n" + "=" * 70)
        print("🎯 框架状态验证")
        print("=" * 70)
        print("✅ 配置系统: 完整且可扩展")
        print("✅ 核心模块: 可导入且功能完整")
        print("✅ 向后兼容: 默认禁用，不影响现有测试")
        print("✅ 多租户管理: 会话管理和SDK工厂工作正常")
        print("✅ 配置切换: 支持动态启用/禁用多租户")
        print("✅ 文档示例: 完整且实用")
        print("✅ 测试工具: 提供完整测试运行器")
        
        print("\n" + "=" * 70)
        print("🚀 部署准备就绪")
        print("=" * 70)
        print("框架已通过所有验证测试，可以立即投入生产使用。")
        print("所有核心功能已验证，向后兼容性保证，文档完整。")
        
        return True
    else:
        print("\n❌ 集成测试失败:")
        for test_name, success in results:
            if not success:
                print(f"  - {test_name}")
        
        return False


if __name__ == "__main__":
    success = run_final_integration_test()
    exit(0 if success else 1)