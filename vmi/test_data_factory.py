#!/usr/bin/env python3
"""
测试数据工厂模块

提供统一的测试数据生成功能，支持：
1. 随机数据生成
2. 数据模板
3. 数据验证
4. 数据清理
"""

import random
import time
import uuid
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class TestDataFactory:
    """测试数据工厂基类"""
    
    def __init__(self, seed: Optional[int] = None):
        """初始化数据工厂
        
        Args:
            seed: 随机种子，用于可重复的测试数据
        """
        if seed is not None:
            random.seed(seed)
        self._created_entities = {}
    
    def generate_partner_data(self, **overrides) -> Dict[str, Any]:
        """生成合作伙伴测试数据
        
        Args:
            **overrides: 覆盖默认值的字段
            
        Returns:
            合作伙伴数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试合作伙伴_{timestamp}_{random_id}',
            'telephone': f'138{random.randint(10000000, 99999999)}',
            'wechat': f'wechat_{random_id}',
            'description': f'测试合作伙伴描述_{timestamp}',
            'status': {'id': 3}
        }
        
        return {**base_data, **overrides}
    
    def generate_product_data(self, **overrides) -> Dict[str, Any]:
        """生成产品测试数据
        
        Args:
            **overrides: 覆盖默认值的字段
            
        Returns:
            产品数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试产品_{timestamp}_{random_id}',
            'code': f'PROD_{random_id:04d}',
            'price': round(random.uniform(10.0, 1000.0), 2),
            'description': f'测试产品描述_{timestamp}',
            'status': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_goods_data(self, product_id: int = 1, **overrides) -> Dict[str, Any]:
        """生成商品测试数据
        
        Args:
            product_id: 关联的产品ID
            **overrides: 覆盖默认值的字段
            
        Returns:
            商品数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试商品_{timestamp}_{random_id}',
            'code': f'GOODS_{random_id:04d}',
            'sku': f'SKU_{random_id:04d}_{timestamp}',
            'price': round(random.uniform(5.0, 500.0), 2),
            'count': random.randint(1, 1000),
            'description': f'测试商品描述_{timestamp}',
            'status': {'id': 1},
            'product': {'id': product_id},
            'shelf': [{'id': 1}],
            'store': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_stockin_data(self, goods_id: int = 1, **overrides) -> Dict[str, Any]:
        """生成入库测试数据
        
        Args:
            goods_id: 关联的商品ID
            **overrides: 覆盖默认值的字段
            
        Returns:
            入库数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'warehouse': {'id': 1},
            'goodsInfo': [{
                'id': goods_id,
                'sku': f'SKU_{random_id:04d}_{timestamp}',
                'product': {'id': 1},
                'type': 1,
                'count': random.randint(1, 100),
                'price': round(random.uniform(5.0, 500.0), 2),
                'shelf': [{'id': 1}]
            }],
            'quantity': random.randint(1, 100),
            'type': 'in',
            'remark': f'测试入库_{timestamp}',
            'operator': f'operator_{random.randint(1, 100)}',
            'status': {'id': 1},
            'store': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_stockout_data(self, goods_id: int = 1, **overrides) -> Dict[str, Any]:
        """生成出库测试数据
        
        Args:
            goods_id: 关联的商品ID
            **overrides: 覆盖默认值的字段
            
        Returns:
            出库数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'warehouse': {'id': 1},
            'goodsInfo': [{
                'id': goods_id,
                'sku': f'SKU_{random_id:04d}_{timestamp}',
                'product': {'id': 1},
                'type': 2,
                'count': random.randint(1, 50),
                'price': round(random.uniform(5.0, 500.0), 2),
                'shelf': [{'id': 1}]
            }],
            'quantity': random.randint(1, 50),
            'type': 'out',
            'remark': f'测试出库_{timestamp}',
            'operator': f'operator_{random.randint(1, 100)}',
            'status': {'id': 1},
            'store': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_warehouse_data(self, **overrides) -> Dict[str, Any]:
        """生成仓库测试数据
        
        Args:
            **overrides: 覆盖默认值的字段
            
        Returns:
            仓库数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试仓库_{timestamp}_{random_id}',
            'code': f'WH_{random_id:04d}',
            'address': f'测试地址_{random_id}',
            'contact': f'联系人_{random_id}',
            'phone': f'138{random.randint(10000000, 99999999)}',
            'description': f'测试仓库描述_{timestamp}',
            'status': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_shelf_data(self, warehouse_id: int = 1, **overrides) -> Dict[str, Any]:
        """生成货架测试数据
        
        Args:
            warehouse_id: 关联的仓库ID
            **overrides: 覆盖默认值的字段
            
        Returns:
            货架数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试货架_{timestamp}_{random_id}',
            'code': f'SHELF_{random_id:04d}',
            'warehouse': {'id': warehouse_id},
            'capacity': random.randint(100, 1000),
            'description': f'测试货架描述_{timestamp}',
            'status': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_store_data(self, **overrides) -> Dict[str, Any]:
        """生成店铺测试数据
        
        Args:
            **overrides: 覆盖默认值的字段
            
        Returns:
            店铺数据字典
        """
        timestamp = int(time.time())
        random_id = random.randint(1000, 9999)
        
        base_data = {
            'name': f'测试店铺_{timestamp}_{random_id}',
            'code': f'STORE_{random_id:04d}',
            'address': f'测试店铺地址_{random_id}',
            'contact': f'店铺联系人_{random_id}',
            'phone': f'138{random.randint(10000000, 99999999)}',
            'description': f'测试店铺描述_{timestamp}',
            'status': {'id': 1}
        }
        
        return {**base_data, **overrides}
    
    def generate_batch_data(self, entity_type: str, count: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """批量生成测试数据
        
        Args:
            entity_type: 实体类型 ('partner', 'product', 'goods', 'stockin', 'stockout', 'warehouse', 'shelf', 'store')
            count: 生成数量
            **kwargs: 传递给生成函数的参数
            
        Returns:
            测试数据列表
        """
        generator_map = {
            'partner': self.generate_partner_data,
            'product': self.generate_product_data,
            'goods': self.generate_goods_data,
            'stockin': self.generate_stockin_data,
            'stockout': self.generate_stockout_data,
            'warehouse': self.generate_warehouse_data,
            'shelf': self.generate_shelf_data,
            'store': self.generate_store_data,
        }
        
        if entity_type not in generator_map:
            raise ValueError(f"不支持的实体类型: {entity_type}")
        
        generator = generator_map[entity_type]
        return [generator(**kwargs) for _ in range(count)]
    
    def record_created_entity(self, entity_type: str, entity_id: str):
        """记录创建的实体ID
        
        Args:
            entity_type: 实体类型
            entity_id: 实体ID
        """
        if entity_type not in self._created_entities:
            self._created_entities[entity_type] = []
        
        self._created_entities[entity_type].append(entity_id)
        logger.debug(f"记录创建的实体: {entity_type} ID: {entity_id}")
    
    def get_created_entities(self, entity_type: Optional[str] = None) -> Dict[str, List[str]]:
        """获取创建的实体ID
        
        Args:
            entity_type: 实体类型，如果为None则返回所有
            
        Returns:
            创建的实体ID字典
        """
        if entity_type:
            return {entity_type: self._created_entities.get(entity_type, [])}
        return self._created_entities.copy()
    
    def clear_created_entities(self, entity_type: Optional[str] = None):
        """清除记录的实体ID
        
        Args:
            entity_type: 实体类型，如果为None则清除所有
        """
        if entity_type:
            if entity_type in self._created_entities:
                self._created_entities[entity_type] = []
                logger.debug(f"清除记录的实体: {entity_type}")
        else:
            self._created_entities.clear()
            logger.debug("清除所有记录的实体")


class ScenarioDataFactory(TestDataFactory):
    """场景测试数据工厂"""
    
    def generate_single_tenant_scenario(self) -> Dict[str, Any]:
        """生成单租户场景测试数据
        
        Returns:
            单租户场景数据
        """
        return {
            'warehouse_count': 1,
            'shelf_count': 20,
            'store_count': 10,
            'product_count': 50000,
            'sku_count': 150000,
            'description': '单租户业务场景测试数据'
        }
    
    def generate_multi_tenant_scenario(self, tenant_count: int = 3) -> Dict[str, Any]:
        """生成多租户场景测试数据
        
        Args:
            tenant_count: 租户数量
            
        Returns:
            多租户场景数据
        """
        base_scenario = self.generate_single_tenant_scenario()
        
        return {
            'tenant_count': tenant_count,
            'warehouse_count': base_scenario['warehouse_count'] * tenant_count,
            'shelf_count': base_scenario['shelf_count'] * tenant_count,
            'store_count': base_scenario['store_count'] * tenant_count,
            'product_count': base_scenario['product_count'] * tenant_count,
            'sku_count': base_scenario['sku_count'] * tenant_count,
            'description': f'{tenant_count}租户业务场景测试数据'
        }
    
    def generate_performance_scenario(self, scale_factor: float = 1.0) -> Dict[str, Any]:
        """生成性能测试场景数据
        
        Args:
            scale_factor: 规模因子，1.0表示标准规模
            
        Returns:
            性能测试场景数据
        """
        base_scenario = self.generate_single_tenant_scenario()
        
        scaled_data = {}
        for key, value in base_scenario.items():
            if isinstance(value, int) and key.endswith('_count'):
                scaled_data[key] = int(value * scale_factor)
            else:
                scaled_data[key] = value
        
        scaled_data['description'] = f'性能测试场景 (规模因子: {scale_factor})'
        return scaled_data


# 全局数据工厂实例
_default_factory = TestDataFactory()
_scenario_factory = ScenarioDataFactory()


# 便捷函数
def create_partner_data(**overrides) -> Dict[str, Any]:
    """创建合作伙伴测试数据"""
    return _default_factory.generate_partner_data(**overrides)


def create_product_data(**overrides) -> Dict[str, Any]:
    """创建产品测试数据"""
    return _default_factory.generate_product_data(**overrides)


def create_goods_data(product_id: int = 1, **overrides) -> Dict[str, Any]:
    """创建商品测试数据"""
    return _default_factory.generate_goods_data(product_id=product_id, **overrides)


def create_stockin_data(goods_id: int = 1, **overrides) -> Dict[str, Any]:
    """创建入库测试数据"""
    return _default_factory.generate_stockin_data(goods_id=goods_id, **overrides)


def create_stockout_data(goods_id: int = 1, **overrides) -> Dict[str, Any]:
    """创建出库测试数据"""
    return _default_factory.generate_stockout_data(goods_id=goods_id, **overrides)


def create_single_tenant_scenario() -> Dict[str, Any]:
    """创建单租户场景数据"""
    return _scenario_factory.generate_single_tenant_scenario()


def create_multi_tenant_scenario(tenant_count: int = 3) -> Dict[str, Any]:
    """创建多租户场景数据"""
    return _scenario_factory.generate_multi_tenant_scenario(tenant_count)


def get_factory(seed: Optional[int] = None) -> TestDataFactory:
    """获取测试数据工厂实例
    
    Args:
        seed: 随机种子
        
    Returns:
        测试数据工厂实例
    """
    return TestDataFactory(seed)


def get_scenario_factory(seed: Optional[int] = None) -> ScenarioDataFactory:
    """获取场景测试数据工厂实例
    
    Args:
        seed: 随机种子
        
    Returns:
        场景测试数据工厂实例
    """
    return ScenarioDataFactory(seed)