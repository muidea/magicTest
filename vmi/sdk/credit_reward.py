"""Credit Reward SDK

积分消费记录 SDK 类，提供积分消费记录实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class CreditRewardSDK(VMISDKBase):
    """积分消费记录 SDK 类"""
    
    def __init__(self, work_session: session.MagicSession):
        """初始化积分消费记录 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/credit/reward')
    
    def filter_credit_reward(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤积分消费记录
        
        Args:
            param: 过滤参数
            
        Returns:
            积分消费记录列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_credit_reward(self, credit_reward_id: int) -> Optional[Dict[str, Any]]:
        """查询积分消费记录
        
        Args:
            credit_reward_id: 积分消费记录ID
            
        Returns:
            积分消费记录信息或 None（失败时）
        """
        return self.query(credit_reward_id)
    
    def create_credit_reward(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建积分消费记录
        
        Args:
            param: 积分消费记录参数
            
        Returns:
            创建的积分消费记录信息或 None（失败时）
        """
        return self.create(param)
    
    def update_credit_reward(self, credit_reward_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新积分消费记录
        
        Args:
            credit_reward_id: 积分消费记录ID
            param: 更新参数
            
        Returns:
            更新的积分消费记录信息或 None（失败时）
        """
        return self.update(credit_reward_id, param)
    
    def delete_credit_reward(self, credit_reward_id: int) -> Optional[Dict[str, Any]]:
        """删除积分消费记录
        
        Args:
            credit_reward_id: 积分消费记录ID
            
        Returns:
            删除的积分消费记录信息或 None（失败时）
        """
        return self.delete(credit_reward_id)
    
    def count_credit_reward(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计积分消费记录数量
        
        Returns:
            积分消费记录数量或 None（失败时）
        """
        return self.count(param)