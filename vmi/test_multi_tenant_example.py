#!/usr/bin/env python3
"""
多租户测试示例 - 演示如何使用多租户测试框架

这个示例展示了：
1. 如何编写多租户测试用例
2. 如何验证租户隔离性
3. 如何在不同租户间切换
4. 如何复用现有测试逻辑
"""

import unittest
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TestMultiTenantExample(unittest.TestCase):
    """多租户测试示例
    
    演示多租户测试的基本用法和最佳实践。
    """
    
    def test_multi_tenant_configuration(self):
        """测试多租户配置加载"""
        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
        
        config = get_multi_tenant_config()
        enabled = is_multi_tenant_enabled()
        
        print(f"多租户启用状态: {enabled}")
        print(f"默认租户: {config.get('default_tenant', 'autotest')}")
        print(f"租户数量: {len(config.get('tenants', {}))}")
        
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
        from multi_tenant_manager import init_global_multi_tenant_manager
        
        # 初始化多租户管理器
        mt_manager = init_global_multi_tenant_manager()
        
        if mt_manager:
            # 获取租户列表
            tenant_ids = mt_manager.get_all_tenant_ids()
            print(f"可用租户: {tenant_ids}")
            
            # 验证至少有一个租户
            self.assertGreaterEqual(len(tenant_ids), 1)
            
            # 验证默认租户存在
            self.assertIn("autotest", tenant_ids)
            
            # 获取租户状态
            status = mt_manager.get_all_tenant_status()
            print(f"租户状态: {list(status.keys())}")
            
            # 清理
            from multi_tenant_manager import cleanup_global_multi_tenant_manager
            cleanup_global_multi_tenant_manager()
            
            logger.info("多租户会话管理测试通过")
        else:
            logger.info("多租户功能未启用，跳过会话管理测试")
            self.skipTest("多租户功能未启用")
    
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
                "enabled": True
            }
        }
        
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
        
        # 创建测试实例
        test_instance = TestBaseMultiTenant()
        test_instance.setUpClass()
        
        try:
            # 测试租户切换
            if test_instance.multi_tenant_enabled:
                tenant_ids = test_instance.multi_tenant_manager.get_all_tenant_ids()
                
                if len(tenant_ids) > 1:
                    # 测试切换到其他租户
                    for tenant_id in tenant_ids[:2]:  # 只测试前两个租户
                        success = test_instance.switch_tenant(tenant_id)
                        self.assertTrue(success, f"切换到租户 '{tenant_id}' 失败")
                        self.assertEqual(test_instance.current_tenant_id, tenant_id)
                        
                        # 验证租户状态
                        status = test_instance.get_tenant_status()
                        self.assertEqual(status["tenant_id"], tenant_id)
                        
                        print(f"成功切换到租户: {tenant_id}")
                
                # 切换回默认租户
                test_instance.switch_tenant("autotest")
                self.assertEqual(test_instance.current_tenant_id, "autotest")
                
            else:
                print("多租户功能未启用，跳过租户切换测试")
                self.skipTest("多租户功能未启用")
                
        finally:
            test_instance.tearDownClass()
        
        logger.info("租户切换测试通过")
    
    def test_multi_tenant_operation(self):
        """测试多租户操作"""
        from test_base_multi_tenant import TestBaseMultiTenant
        
        # 创建测试实例
        test_instance = TestBaseMultiTenant()
        test_instance.setUpClass()
        
        try:
            # 定义测试操作
            def test_operation(tenant_id):
                print(f"在租户 '{tenant_id}' 上执行测试操作")
                # 这里可以执行实际的SDK操作
                return {"tenant_id": tenant_id, "status": "success"}
            
            # 为所有租户执行测试
            results = test_instance.run_for_all_tenants(test_operation)
            
            # 验证结果
            self.assertIsInstance(results, dict)
            
            if test_instance.multi_tenant_enabled:
                enabled_tenants = test_instance.multi_tenant_manager.get_enabled_tenant_ids()
                self.assertEqual(len(results), len(enabled_tenants))
                
                for tenant_id, result in results.items():
                    self.assertIn("status", result)
                    if result["status"] == "passed":
                        self.assertIn("result", result)
                        self.assertEqual(result["result"]["tenant_id"], tenant_id)
            
            else:
                # 单租户模式
                self.assertIn("autotest", results)
                self.assertEqual(results["autotest"]["status"], "passed")
                
        finally:
            test_instance.tearDownClass()
        
        logger.info("多租户操作测试通过")


class TestMultiTenantBestPractices(unittest.TestCase):
    """多租户最佳实践示例"""
    
    def test_context_manager_usage(self):
        """测试上下文管理器用法"""
        from test_base_multi_tenant import SimpleMultiTenantTest
        
        # 创建测试实例
        test_instance = SimpleMultiTenantTest()
        test_instance.setUpClass()
        
        try:
            if test_instance.multi_tenant_enabled:
                tenant_ids = test_instance.multi_tenant_manager.get_enabled_tenant_ids()
                
                if len(tenant_ids) > 1:
                    # 使用上下文管理器切换租户
                    with test_instance.for_tenant(tenant_ids[0]):
                        print(f"在上下文管理器中，当前租户: {test_instance.current_tenant_id}")
                        self.assertEqual(test_instance.current_tenant_id, tenant_ids[0])
                    
                    # 验证已切换回原租户
                    self.assertEqual(test_instance.current_tenant_id, "autotest")
                    
            else:
                print("多租户功能未启用，跳过上下文管理器测试")
                self.skipTest("多租户功能未启用")
                
        finally:
            test_instance.tearDownClass()
        
        logger.info("上下文管理器测试通过")
    
    def test_tenant_isolation_verification(self):
        """测试租户隔离性验证"""
        from test_base_multi_tenant import TestBaseMultiTenant
        
        # 创建测试实例
        test_instance = TestBaseMultiTenant()
        test_instance.setUpClass()
        
        try:
            if test_instance.multi_tenant_enabled:
                tenant_ids = test_instance.multi_tenant_manager.get_enabled_tenant_ids()
                
                if len(tenant_ids) >= 2:
                    # 定义验证函数
                    def verify_tenant_data(tenant_id):
                        # 模拟获取租户特定数据
                        return {"tenant_id": tenant_id, "data": f"data_for_{tenant_id}"}
                    
                    # 验证租户隔离性
                    test_instance.assert_tenant_isolation(
                        tenant_ids[0], tenant_ids[1], verify_tenant_data
                    )
                    
                    print(f"租户 '{tenant_ids[0]}' 和 '{tenant_ids[1]}' 隔离性验证通过")
                    
            else:
                print("多租户功能未启用，跳过隔离性验证测试")
                self.skipTest("多租户功能未启用")
                
        finally:
            test_instance.tearDownClass()
        
        logger.info("租户隔离性验证测试通过")


# 运行所有测试
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("多租户测试示例")
    print("=" * 60)
    
    # 运行测试
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestMultiTenantExample)
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTenantIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiTenantBestPractices))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 输出测试结果
    print("\n" + "=" * 60)
    print("测试结果摘要")
    print("=" * 60)
    print(f"运行测试数: {result.testsRun}")
    print(f"通过数: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败数: {len(result.failures)}")
    print(f"错误数: {len(result.errors)}")
    
    if result.wasSuccessful():
        print("\n✅ 所有测试通过！")
    else:
        print("\n❌ 测试失败或出错")
        
        if result.failures:
            print("\n失败详情:")
            for test, traceback in result.failures:
                print(f"  {test}: {traceback.splitlines()[-1]}")
        
        if result.errors:
            print("\n错误详情:")
            for test, traceback in result.errors:
                print(f"  {test}: {traceback.splitlines()[-1]}")
    
    print("\n多租户测试示例执行完成")