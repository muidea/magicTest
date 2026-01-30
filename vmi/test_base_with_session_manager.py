#!/usr/bin/env python3
"""
使用会话管理器的测试基类
"""

import unittest
import logging
import time
from typing import Optional

# 配置日志
logger = logging.getLogger(__name__)


class TestBaseWithSessionManager(unittest.TestCase):
    """使用会话管理器的测试基类
    
    提供会话管理功能，包括：
    1. 自动会话创建和登录
    2. 定期会话刷新
    3. 会话超时处理
    4. SDK实例管理
    """
    
    # 类属性
    namespace = ''
    session_manager = None
    work_session = None
    cas_session = None
    
    # SDK实例
    warehouse_sdk = None
    shelf_sdk = None
    store_sdk = None
    product_sdk = None
    partner_sdk = None
    goods_sdk = None
    stockin_sdk = None
    stockout_sdk = None
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 使用会话管理器"""
        from config_helper import get_server_url, get_credentials
        from session_manager import init_global_session_manager
        
        # 获取配置
        cls.server_url = get_server_url()
        cls.credentials = get_credentials()
        
        logger.info(f"测试基类: 初始化会话管理器 - 服务器: {cls.server_url}")
        
        # 初始化全局会话管理器（9分钟刷新一次，符合服务器要求）
        cls.session_manager = init_global_session_manager(
            server_url=cls.server_url,
            namespace=cls.namespace,
            username=cls.credentials['username'],
            password=cls.credentials['password'],
            refresh_interval=540,  # 9分钟刷新一次
            session_timeout=1800   # 30分钟会话超时
        )
        
        # 创建会话
        if not cls.session_manager.create_session():
            logger.error("测试基类: 创建会话失败")
            raise Exception("创建会话失败")
        
        # 启动自动刷新
        cls.session_manager.start_auto_refresh()
        
        # 获取会话对象
        cls.work_session = cls.session_manager.get_session()
        cls.cas_session = cls.session_manager.get_cas_session()
        
        logger.info("测试基类: 会话初始化完成，自动刷新已启动")
        
        # 初始化SDK实例
        cls._init_sdk_instances()
    
    @classmethod
    def _init_sdk_instances(cls):
        """初始化SDK实例"""
        try:
            from sdk import (
                WarehouseSDK, ShelfSDK, StoreSDK, ProductSDK,
                PartnerSDK, GoodsSDK, StockinSDK, StockoutSDK
            )
            
            # 确保会话有效
            from session_manager import ensure_session_valid
            ensure_session_valid(cls.session_manager)
            
            # 创建SDK实例
            cls.warehouse_sdk = WarehouseSDK(cls.work_session)
            cls.shelf_sdk = ShelfSDK(cls.work_session)
            cls.store_sdk = StoreSDK(cls.work_session)
            cls.product_sdk = ProductSDK(cls.work_session)
            cls.partner_sdk = PartnerSDK(cls.work_session)
            cls.goods_sdk = GoodsSDK(cls.work_session)
            cls.stockin_sdk = StockinSDK(cls.work_session)
            cls.stockout_sdk = StockoutSDK(cls.work_session)
            
            logger.debug("测试基类: SDK实例初始化完成")
            
        except ImportError as e:
            logger.error(f"测试基类: 导入SDK失败 - {e}")
            raise
        except Exception as e:
            logger.error(f"测试基类: 初始化SDK失败 - {e}")
            raise
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls.session_manager:
            logger.info("测试基类: 停止会话管理器")
            cls.session_manager.stop_auto_refresh()
            cls.session_manager.close_session()
        
        logger.info("测试基类: 清理完成")
    
    def setUp(self):
        """每个测试用例开始前执行"""
        # 确保会话有效
        from session_manager import ensure_session_valid
        if not ensure_session_valid(self.session_manager):
            logger.warning("测试用例: 会话无效，尝试重新连接")
            if not self.session_manager.reconnect():
                self.fail("会话重新连接失败")
        
        # 更新活动时间
        self.session_manager.update_activity()
        
        logger.debug(f"测试用例开始: {self._testMethodName}")
    
    def tearDown(self):
        """每个测试用例结束后执行"""
        # 更新活动时间
        self.session_manager.update_activity()
        
        logger.debug(f"测试用例结束: {self._testMethodName}")
    
    def ensure_session_before_operation(self) -> bool:
        """在执行操作前确保会话有效
        
        Returns:
            会话是否有效
        """
        from session_manager import ensure_session_valid
        
        if not ensure_session_valid(self.session_manager):
            logger.warning("操作前检查: 会话无效，尝试重新连接")
            if self.session_manager.reconnect():
                # 重新初始化SDK实例（因为会话已更新）
                self._init_sdk_instances()
                return True
            else:
                logger.error("操作前检查: 重新连接失败")
                return False
        
        return True
    
    def execute_with_session_check(self, operation_func, *args, **kwargs):
        """带会话检查的执行方法
        
        Args:
            operation_func: 要执行的操作函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            操作结果
        
        Raises:
            AssertionError: 如果会话无效且无法恢复
        """
        # 检查会话
        if not self.ensure_session_before_operation():
            self.fail("会话无效且无法恢复，操作中止")
        
        try:
            # 执行操作
            result = operation_func(*args, **kwargs)
            
            # 更新活动时间
            self.session_manager.update_activity()
            
            return result
            
        except Exception as e:
            # 检查是否是会话超时错误
            error_msg = str(e).lower()
            session_errors = ['session', 'token', 'auth', 'login', 'unauthorized', 'timeout']
            
            if any(error in error_msg for error in session_errors):
                logger.warning(f"操作可能因会话问题失败: {e}")
                
                # 尝试重新连接并重试
                logger.info("尝试重新连接并重试操作")
                if self.session_manager.reconnect():
                    # 重新初始化SDK
                    self._init_sdk_instances()
                    
                    # 重试操作
                    try:
                        result = operation_func(*args, **kwargs)
                        self.session_manager.update_activity()
                        logger.info("重试操作成功")
                        return result
                    except Exception as retry_error:
                        logger.error(f"重试操作失败: {retry_error}")
                        raise retry_error
                else:
                    logger.error("重新连接失败")
                    raise e
            else:
                # 其他错误，直接抛出
                raise e
    
    # 便捷方法
    def create_warehouse(self, warehouse_data):
        """创建仓库（带会话检查）"""
        return self.execute_with_session_check(
            self.warehouse_sdk.create_warehouse, warehouse_data
        )
    
    def create_shelf(self, shelf_data):
        """创建货架（带会话检查）"""
        return self.execute_with_session_check(
            self.shelf_sdk.create_shelf, shelf_data
        )
    
    def create_product(self, product_data):
        """创建产品（带会话检查）"""
        return self.execute_with_session_check(
            self.product_sdk.create_product, product_data
        )
    
    def create_partner(self, partner_data):
        """创建合作伙伴（带会话检查）"""
        return self.execute_with_session_check(
            self.partner_sdk.create_partner, partner_data
        )
    
    def create_goods(self, goods_data):
        """创建商品（带会话检查）"""
        return self.execute_with_session_check(
            self.goods_sdk.create_goods, goods_data
        )
    
    def create_stockin(self, stockin_data):
        """创建入库单（带会话检查）"""
        return self.execute_with_session_check(
            self.stockin_sdk.create_stockin, stockin_data
        )
    
    def create_stockout(self, stockout_data):
        """创建出库单（带会话检查）"""
        return self.execute_with_session_check(
            self.stockout_sdk.create_stockout, stockout_data
        )
    
    def refresh_session_manually(self):
        """手动刷新会话"""
        logger.info("手动刷新会话")
        return self.session_manager.refresh_session()