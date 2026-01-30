"""Reward Policy SDK

积分策略 SDK 类，提供积分策略实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class RewardPolicySDK(VMISDKBase):
    """积分策略 SDK 类"""
    
    def __init__(self, work_session):
        """初始化积分策略 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/credit/rewardPolicy')
    
    def filter_reward_policy(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤积分策略
        
        Args:
            param: 过滤参数
            
        Returns:
            积分策略列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_reward_policy(self, reward_policy_id: int) -> Optional[Dict[str, Any]]:
        """查询积分策略
        
        Args:
            reward_policy_id: 积分策略ID
            
        Returns:
            积分策略信息或 None（失败时）
        """
        return self.query(reward_policy_id)
    
    def create_reward_policy(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建积分策略
        
        Args:
            param: 积分策略参数
            
        Returns:
            创建的积分策略信息或 None（失败时）
        """
        return self.create(param)
    
    def update_reward_policy(self, reward_policy_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新积分策略
        
        Args:
            reward_policy_id: 积分策略ID
            param: 更新参数
            
        Returns:
            更新的积分策略信息或 None（失败时）
        """
        return self.update(reward_policy_id, param)
    
    def delete_reward_policy(self, reward_policy_id: int) -> Optional[Dict[str, Any]]:
        """删除积分策略
        
        Args:
            reward_policy_id: 积分策略ID
            
        Returns:
            删除的积分策略信息或 None（失败时）
        """
        return self.delete(reward_policy_id)
    
    def count_reward_policy(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计积分策略数量
        
        Returns:
            积分策略数量或 None（失败时）
        """
        return self.count(param)