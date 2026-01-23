"""Stockin SDK

入库单 SDK 类，提供入库单实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class StockinSDK(VMISDKBase):
    """入库单 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化入库单 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/store/stockin')
    
    def filter_stockin(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤入库单
        
        Args:
            param: 过滤参数
            
        Returns:
            入库单列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_stockin(self, stockin_id: int) -> Optional[Dict[str, Any]]:
        """查询入库单
        
        Args:
            stockin_id: 入库单ID
            
        Returns:
            入库单信息或 None（失败时）
        """
        return self.query(stockin_id)
    
    def create_stockin(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建入库单
        
        Args:
            param: 入库单参数
            
        Returns:
            创建的入库单信息或 None（失败时）
        """
        return self.create(param)
    
    def update_stockin(self, stockin_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新入库单
        
        Args:
            stockin_id: 入库单ID
            param: 更新参数
            
        Returns:
            更新的入库单信息或 None（失败时）
        """
        return self.update(stockin_id, param)
    
    def delete_stockin(self, stockin_id: int) -> Optional[Dict[str, Any]]:
        """删除入库单
        
        Args:
            stockin_id: 入库单ID
            
        Returns:
            删除的入库单信息或 None（失败时）
        """
        return self.delete(stockin_id)
    
    def count_stockin(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计入库单数量
        
        Returns:
            入库单数量或 None（失败时）
        """
        return self.count(param)