#!/usr/bin/env python3
"""
基础功能测试 - pytest版本

测试系统核心功能，包括：
1. 配置加载
2. 模块导入
3. 会话管理
4. SDK基础功能
"""

import pytest
import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class TestBasicFunctionality:
    """基础功能测试类"""
    
    @pytest.mark.basic
    def test_config_loading(self):
        """测试配置文件加载"""
        try:
            with open('test_config.json', 'r') as f:
                config = json.load(f)
            
            assert 'server_url' in config, "配置文件中缺少server_url字段"
            assert 'environment' in config, "配置文件中缺少environment字段"
            assert 'namespace' in config, "配置文件中缺少namespace字段"
            
            logger.info(f"配置文件加载成功 - 服务器: {config.get('server_url')}")
            logger.info(f"环境: {config.get('environment')}")
            logger.info(f"命名空间: {config.get('namespace')}")
            
        except FileNotFoundError:
            pytest.fail("配置文件不存在: test_config.json")
        except json.JSONDecodeError as e:
            pytest.fail(f"配置文件JSON格式错误: {e}")
    
    @pytest.mark.basic
    def test_core_module_imports(self):
        """测试核心模块导入"""
        # 测试SDK基础类导入
        try:
            from sdk.base import MagicEntity
            logger.info("✅ SDK基础类导入成功")
        except ImportError as e:
            pytest.fail(f"导入SDK基础类失败: {e}")
        
        # 测试会话管理器导入
        try:
            from session_manager import SessionManager
            logger.info("✅ 会话管理器导入成功")
        except ImportError as e:
            pytest.fail(f"导入会话管理器失败: {e}")
        
        # 测试配置助手导入
        try:
            from config_helper import get_server_url, get_credentials
            logger.info("✅ 配置助手导入成功")
        except ImportError as e:
            pytest.fail(f"导入配置助手失败: {e}")
        
        # 测试性能监控导入（可选）
        try:
            from performance_monitor import PerformanceMonitor
            logger.info("✅ 性能监控器导入成功")
        except ImportError as e:
            logger.warning(f"⚠️ 性能监控器导入警告: {e}")
            logger.info("ℹ️ 可以运行: pip install psutil matplotlib numpy")
    
    @pytest.mark.basic
    @pytest.mark.session
    def test_session_manager_creation(self, test_config):
        """测试会话管理器创建"""
        from session_manager import SessionManager
        
        try:
            mgr = SessionManager(
                server_url=test_config['server_url'],
                namespace=test_config['namespace'],
                username=test_config['credentials']['username'],
                password=test_config['credentials']['password'],
                refresh_interval=540,  # 9分钟刷新一次
                session_timeout=1800   # 30分钟会话超时
            )
            
            assert mgr is not None, "会话管理器创建失败"
            assert mgr.server_url == test_config['server_url'], "服务器URL不匹配"
            assert mgr.namespace == test_config['namespace'], "命名空间不匹配"
            
            logger.info(f"✅ 会话管理器创建成功 - 服务器: {mgr.server_url}")
            logger.info(f"命名空间: {mgr.namespace}")
            
            # 清理
            if hasattr(mgr, 'close_session'):
                mgr.close_session()
                logger.info("✅ 会话管理器关闭成功")
            
        except Exception as e:
            pytest.fail(f"会话管理器测试失败: {e}")
    
    @pytest.mark.basic
    def test_sdk_module_structure(self):
        """测试SDK模块结构"""
        try:
            # 测试SDK包导入
            import sdk
            
            # 检查SDK模块是否包含必要的子模块
            expected_modules = [
                'base', 'warehouse', 'shelf', 'store', 'product',
                'partner', 'goods', 'stockin', 'stockout'
            ]
            
            for module_name in expected_modules:
                try:
                    module = __import__(f'sdk.{module_name}', fromlist=[''])
                    logger.info(f"✅ SDK模块 {module_name} 导入成功")
                except ImportError as e:
                    logger.warning(f"⚠️ SDK模块 {module_name} 导入警告: {e}")
            
            # 测试基础类定义
            from sdk.base import MagicEntity
            assert hasattr(MagicEntity, 'create'), "MagicEntity缺少create方法"
            assert hasattr(MagicEntity, 'query'), "MagicEntity缺少query方法"
            assert hasattr(MagicEntity, 'update'), "MagicEntity缺少update方法"
            assert hasattr(MagicEntity, 'delete'), "MagicEntity缺少delete方法"
            
            logger.info("✅ SDK模块结构验证通过")
            
        except ImportError as e:
            pytest.fail(f"导入SDK包失败: {e}")
        except Exception as e:
            pytest.fail(f"SDK模块结构测试失败: {e}")
    
    @pytest.mark.basic
    def test_test_data_factory(self):
        """测试测试数据工厂"""
        from test_data_factory import (
            create_partner_data,
            create_product_data,
            create_goods_data,
            create_stockin_data,
            create_stockout_data,
            create_single_tenant_scenario
        )
        
        # 测试合作伙伴数据生成
        partner_data = create_partner_data()
        assert 'name' in partner_data, "合作伙伴数据缺少name字段"
        assert 'telephone' in partner_data, "合作伙伴数据缺少telephone字段"
        assert 'status' in partner_data, "合作伙伴数据缺少status字段"
        logger.info("✅ 合作伙伴数据生成测试通过")
        
        # 测试产品数据生成
        product_data = create_product_data()
        assert 'name' in product_data, "产品数据缺少name字段"
        assert 'code' in product_data, "产品数据缺少code字段"
        assert 'price' in product_data, "产品数据缺少price字段"
        logger.info("✅ 产品数据生成测试通过")
        
        # 测试商品数据生成
        goods_data = create_goods_data(product_id=1)
        assert 'name' in goods_data, "商品数据缺少name字段"
        assert 'sku' in goods_data, "商品数据缺少sku字段"
        assert 'product' in goods_data, "商品数据缺少product字段"
        logger.info("✅ 商品数据生成测试通过")
        
        # 测试入库数据生成
        stockin_data = create_stockin_data(goods_id=1)
        assert 'warehouse' in stockin_data, "入库数据缺少warehouse字段"
        assert 'goodsInfo' in stockin_data, "入库数据缺少goodsInfo字段"
        assert 'type' in stockin_data, "入库数据缺少type字段"
        logger.info("✅ 入库数据生成测试通过")
        
        # 测试出库数据生成
        stockout_data = create_stockout_data(goods_id=1)
        assert 'warehouse' in stockout_data, "出库数据缺少warehouse字段"
        assert 'goodsInfo' in stockout_data, "出库数据缺少goodsInfo字段"
        assert 'type' in stockout_data, "出库数据缺少type字段"
        logger.info("✅ 出库数据生成测试通过")
        
        # 测试场景数据生成
        scenario_data = create_single_tenant_scenario()
        assert 'warehouse_count' in scenario_data, "场景数据缺少warehouse_count字段"
        assert 'product_count' in scenario_data, "场景数据缺少product_count字段"
        assert 'sku_count' in scenario_data, "场景数据缺少sku_count字段"
        logger.info("✅ 场景数据生成测试通过")
    
    @pytest.mark.basic
    @pytest.mark.parametrize("entity_type,expected_fields", [
        ("partner", ["name", "telephone", "status"]),
        ("product", ["name", "code", "price", "status"]),
        ("goods", ["name", "sku", "product", "status"]),
        ("stockin", ["warehouse", "goodsInfo", "type", "status"]),
        ("stockout", ["warehouse", "goodsInfo", "type", "status"]),
    ])
    def test_entity_data_structure(self, entity_type, expected_fields):
        """测试实体数据结构 - 参数化测试"""
        from test_data_factory import get_factory
        
        factory = get_factory()
        
        # 根据实体类型调用对应的生成方法
        if entity_type == "partner":
            data = factory.generate_partner_data()
        elif entity_type == "product":
            data = factory.generate_product_data()
        elif entity_type == "goods":
            data = factory.generate_goods_data()
        elif entity_type == "stockin":
            data = factory.generate_stockin_data()
        elif entity_type == "stockout":
            data = factory.generate_stockout_data()
        else:
            pytest.fail(f"不支持的实体类型: {entity_type}")
        
        # 验证必需字段
        for field in expected_fields:
            assert field in data, f"{entity_type}数据缺少{field}字段"
        
        logger.info(f"✅ {entity_type}数据结构验证通过")
    
    @pytest.mark.basic
    def test_logging_configuration(self):
        """测试日志配置"""
        import logging
        
        # 测试当前模块日志记录器
        current_logger = logging.getLogger(__name__)
        assert current_logger is not None, "当前模块日志记录器获取失败"
        
        # 测试日志记录器能够记录不同级别的日志
        test_levels = [logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR]
        
        # 保存原始级别
        original_level = current_logger.level
        
        # 测试日志级别设置
        for level in test_levels:
            current_logger.setLevel(level)
            assert current_logger.level == level, f"日志级别设置失败: 期望{level}, 实际{current_logger.level}"
            
            # 测试该级别下日志是否能够记录
            if level <= logging.INFO:
                # 对于INFO及以下级别，应该能够记录INFO日志
                current_logger.info(f"测试INFO级别日志 - 当前级别: {level}")
            if level <= logging.WARNING:
                # 对于WARNING及以下级别，应该能够记录WARNING日志
                current_logger.warning(f"测试WARNING级别日志 - 当前级别: {level}")
        
        # 恢复原始级别
        current_logger.setLevel(original_level)
        
        logger.info("✅ 日志配置测试通过")


@pytest.mark.basic
def test_quick_smoke_test():
    """快速冒烟测试 - 函数式测试示例"""
    # 测试基本Python功能
    assert 1 + 1 == 2, "基本数学运算失败"
    
    # 测试字符串操作
    test_string = "Hello, World!"
    assert len(test_string) == 13, "字符串长度计算错误"
    assert test_string.upper() == "HELLO, WORLD!", "字符串大写转换失败"
    
    # 测试列表操作
    test_list = [1, 2, 3, 4, 5]
    assert sum(test_list) == 15, "列表求和失败"
    assert len(test_list) == 5, "列表长度错误"
    
    logger.info("✅ 快速冒烟测试通过")


@pytest.mark.basic
@pytest.mark.parametrize("test_input,expected", [
    ({"a": 1, "b": 2}, 3),
    ({"a": 0, "b": 0}, 0),
    ({"a": -1, "b": 1}, 0),
    ({"a": 100, "b": 200}, 300),
])
def test_parametrized_addition(test_input, expected):
    """参数化加法测试 - 演示pytest参数化功能"""
    result = test_input["a"] + test_input["b"]
    assert result == expected, f"加法计算错误: {test_input['a']} + {test_input['b']} = {result}, 期望 {expected}"
    
    logger.info(f"✅ 参数化加法测试通过: {test_input['a']} + {test_input['b']} = {result}")


if __name__ == "__main__":
    # 允许直接运行测试
    pytest.main([__file__, "-v"])