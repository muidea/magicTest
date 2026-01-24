"""Status SDK

状态 SDK 类，提供状态实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class StatusSDK(VMISDKBase):
    """状态 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化状态 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/status')
    
    def filter_status(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤状态
        
        Args:
            param: 过滤参数
            
        Returns:
            状态列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_status(self, status_id: int) -> Optional[Dict[str, Any]]:
        """查询状态
        
        Args:
            status_id: 状态ID
            
        Returns:
            状态信息或 None（失败时）
        """
        return self.query(status_id)
    
    def create_status(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建状态
        
        Args:
            param: 状态参数
            
        Returns:
            创建的状态信息或 None（失败时）
        """
        return self.create(param)
    
    def update_status(self, status_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新状态
        
        Args:
            status_id: 状态ID
            param: 更新参数
            
        Returns:
            更新的状态信息或 None（失败时）
        """
        return self.update(status_id, param)
    
    def delete_status(self, status_id: int) -> Optional[Dict[str, Any]]:
        """删除状态
        
        Args:
            status_id: 状态ID
            
        Returns:
            删除的状态信息或 None（失败时）
        """
        return self.delete(status_id)
    
    def count_status(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计状态数量
        
        Returns:
            状态数量或 None（失败时）
        """
        return self.count(param)