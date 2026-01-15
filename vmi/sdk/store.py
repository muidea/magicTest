"""Store SDK

店铺 SDK 类，提供店铺实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class StoreSDK(VMISDKBase):
    """店铺 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化店铺 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/store')
    
    def filter_store(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤店铺
        
        Args:
            param: 过滤参数
            
        Returns:
            店铺列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_store(self, store_id: int) -> Optional[Dict[str, Any]]:
        """查询店铺
        
        Args:
            store_id: 店铺ID
            
        Returns:
            店铺信息或 None（失败时）
        """
        return self.query(store_id)
    
    def create_store(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建店铺
        
        Args:
            param: 店铺参数
            
        Returns:
            创建的店铺信息或 None（失败时）
        """
        return self.create(param)
    
    def update_store(self, store_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新店铺
        
        Args:
            store_id: 店铺ID
            param: 更新参数
            
        Returns:
            更新的店铺信息或 None（失败时）
        """
        return self.update(store_id, param)
    
    def delete_store(self, store_id: int) -> Optional[Dict[str, Any]]:
        """删除店铺
        
        Args:
            store_id: 店铺ID
            
        Returns:
            删除的店铺信息或 None（失败时）
        """
        return self.delete(store_id)
    
    def count_store(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计店铺数量
        
        Returns:
            店铺数量或 None（失败时）
        """
        return self.count(param)