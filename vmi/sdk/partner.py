"""Partner SDK

合作伙伴 SDK 类，提供合作伙伴实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class PartnerSDK(VMISDKBase):
    """合作伙伴 SDK 类"""
    
    def __init__(self, work_session):
        """初始化合作伙伴 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/partner')
    
    def filter_partner(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤合作伙伴
        
        Args:
            param: 过滤参数
            
        Returns:
            合作伙伴列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_partner(self, partner_id: int) -> Optional[Dict[str, Any]]:
        """查询合作伙伴
        
        Args:
            partner_id: 合作伙伴ID
            
        Returns:
            合作伙伴信息或 None（失败时）
        """
        return self.query(partner_id)
    
    def create_partner(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建合作伙伴
        
        Args:
            param: 合作伙伴参数
            
        Returns:
            创建的合作伙伴信息或 None（失败时）
        """
        return self.create(param)
    
    def update_partner(self, partner_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新合作伙伴
        
        Args:
            partner_id: 合作伙伴ID
            param: 更新参数
            
        Returns:
            更新的合作伙伴信息或 None（失败时）
        """
        return self.update(partner_id, param)
    
    def delete_partner(self, partner_id: int) -> Optional[Dict[str, Any]]:
        """删除合作伙伴
        
        Args:
            partner_id: 合作伙伴ID
            
        Returns:
            删除的合作伙伴信息或 None（失败时）
        """
        return self.delete(partner_id)
    
    def count_partner(self) -> Optional[int]:
        """统计合作伙伴数量
        
        Returns:
            合作伙伴数量或 None（失败时）
        """
        return self.count()