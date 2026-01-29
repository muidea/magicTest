"""Credit Report SDK

积分报表 SDK 类，提供积分报表实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class CreditReportSDK(VMISDKBase):
    """积分报表 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化积分报表 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/credit/creditReport')
    
    def filter_credit_report(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤积分报表
        
        Args:
            param: 过滤参数
            
        Returns:
            积分报表列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_credit_report(self, credit_report_id: int) -> Optional[Dict[str, Any]]:
        """查询积分报表
        
        Args:
            credit_report_id: 积分报表ID
            
        Returns:
            积分报表信息或 None（失败时）
        """
        return self.query(credit_report_id)
    
    def create_credit_report(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建积分报表
        
        Args:
            param: 积分报表参数
            
        Returns:
            创建的积分报表信息或 None（失败时）
        """
        return self.create(param)
    
    def update_credit_report(self, credit_report_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新积分报表
        
        Args:
            credit_report_id: 积分报表ID
            param: 更新参数
            
        Returns:
            更新的积分报表信息或 None（失败时）
        """
        return self.update(credit_report_id, param)
    
    def delete_credit_report(self, credit_report_id: int) -> Optional[Dict[str, Any]]:
        """删除积分报表
        
        Args:
            credit_report_id: 积分报表ID
            
        Returns:
            删除的积分报表信息或 None（失败时）
        """
        return self.delete(credit_report_id)
    
    def count_credit_report(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计积分报表数量
        
        Returns:
            积分报表数量或 None（失败时）
        """
        return self.count(param)