"""Member SDK

店铺成员 SDK 类，提供店铺成员实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class MemberSDK(VMISDKBase):
    """店铺成员 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化店铺成员 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/store/member')
    
    def filter_member(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤店铺成员
        
        Args:
            param: 过滤参数
            
        Returns:
            店铺成员列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_member(self, member_id: int) -> Optional[Dict[str, Any]]:
        """查询店铺成员
        
        Args:
            member_id: 店铺成员ID
            
        Returns:
            店铺成员信息或 None（失败时）
        """
        return self.query(member_id)
    
    def create_member(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建店铺成员
        
        Args:
            param: 店铺成员参数
            
        Returns:
            创建的店铺成员信息或 None（失败时）
        """
        return self.create(param)
    
    def update_member(self, member_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新店铺成员
        
        Args:
            member_id: 店铺成员ID
            param: 更新参数
            
        Returns:
            更新的店铺成员信息或 None（失败时）
        """
        return self.update(member_id, param)
    
    def delete_member(self, member_id: int) -> Optional[Dict[str, Any]]:
        """删除店铺成员
        
        Args:
            member_id: 店铺成员ID
            
        Returns:
            删除的店铺成员信息或 None（失败时）
        """
        return self.delete(member_id)
    
    def count_member(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计店铺成员数量
        
        Returns:
            店铺成员数量或 None（失败时）
        """
        return self.count(param)