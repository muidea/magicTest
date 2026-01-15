"""Warehouse SDK

仓库 SDK 类，提供仓库实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class WarehouseSDK(VMISDKBase):
    """仓库 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化仓库 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/warehouse')
    
    def filter_warehouse(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤仓库
        
        Args:
            param: 过滤参数
            
        Returns:
            仓库列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_warehouse(self, warehouse_id: int) -> Optional[Dict[str, Any]]:
        """查询仓库
        
        Args:
            warehouse_id: 仓库ID
            
        Returns:
            仓库信息或 None（失败时）
        """
        return self.query(warehouse_id)
    
    def create_warehouse(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建仓库
        
        Args:
            param: 仓库参数
            
        Returns:
            创建的仓库信息或 None（失败时）
        """
        return self.create(param)
    
    def update_warehouse(self, warehouse_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新仓库
        
        Args:
            warehouse_id: 仓库ID
            param: 更新参数
            
        Returns:
            更新的仓库信息或 None（失败时）
        """
        return self.update(warehouse_id, param)
    
    def delete_warehouse(self, warehouse_id: int) -> Optional[Dict[str, Any]]:
        """删除仓库
        
        Args:
            warehouse_id: 仓库ID
            
        Returns:
            删除的仓库信息或 None（失败时）
        """
        return self.delete(warehouse_id)
    
    def count_warehouse(self) -> Optional[int]:
        """统计仓库数量
        
        Returns:
            仓库数量或 None（失败时）
        """
        return self.count()