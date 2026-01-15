"""Shelf SDK

货架 SDK 类，提供货架实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class ShelfSDK(VMISDKBase):
    """货架 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化货架 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/warehouse/shelf')
    
    def filter_shelf(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤货架
        
        Args:
            param: 过滤参数
            
        Returns:
            货架列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_shelf(self, shelf_id: int) -> Optional[Dict[str, Any]]:
        """查询货架
        
        Args:
            shelf_id: 货架ID
            
        Returns:
            货架信息或 None（失败时）
        """
        return self.query(shelf_id)
    
    def create_shelf(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建货架
        
        Args:
            param: 货架参数
            
        Returns:
            创建的货架信息或 None（失败时）
        """
        return self.create(param)
    
    def update_shelf(self, shelf_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新货架
        
        Args:
            shelf_id: 货架ID
            param: 更新参数
            
        Returns:
            更新的货架信息或 None（失败时）
        """
        return self.update(shelf_id, param)
    
    def delete_shelf(self, shelf_id: int) -> Optional[Dict[str, Any]]:
        """删除货架
        
        Args:
            shelf_id: 货架ID
            
        Returns:
            删除的货架信息或 None（失败时）
        """
        return self.delete(shelf_id)
    
    def count_shelf(self) -> Optional[int]:
        """统计货架数量
        
        Returns:
            货架数量或 None（失败时）
        """
        return self.count()