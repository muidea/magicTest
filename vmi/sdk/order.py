"""Order SDK

订单信息 SDK 类，提供订单信息实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class OrderSDK(VMISDKBase):
    """订单信息 SDK 类"""
    
    def __init__(self, work_session):
        """初始化订单信息 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/order')
    
    def filter_order(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤订单信息
        
        Args:
            param: 过滤参数
            
        Returns:
            订单信息列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """查询订单信息
        
        Args:
            order_id: 订单信息ID
            
        Returns:
            订单信息或 None（失败时）
        """
        return self.query(order_id)
    
    def create_order(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建订单信息
        
        Args:
            param: 订单信息参数
            
        Returns:
            创建的订单信息或 None（失败时）
        """
        return self.create(param)
    
    def update_order(self, order_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新订单信息
        
        Args:
            order_id: 订单信息ID
            param: 更新参数
            
        Returns:
            更新的订单信息或 None（失败时）
        """
        return self.update(order_id, param)
    
    def delete_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """删除订单信息
        
        Args:
            order_id: 订单信息ID
            
        Returns:
            删除的订单信息或 None（失败时）
        """
        return self.delete(order_id)
    
    def count_order(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计订单信息数量
        
        Returns:
            订单信息数量或 None（失败时）
        """
        return self.count(param)