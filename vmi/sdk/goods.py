"""Goods SDK

商品信息 SDK 类，提供商品信息实体的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List
# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class GoodsSDK(VMISDKBase):
    """商品信息 SDK 类"""
    
    def __init__(self, work_session):
        """初始化商品信息 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/store/goods')
    
    def filter_goods(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤商品信息
        
        Args:
            param: 过滤参数
            
        Returns:
            商品信息列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_goods(self, goods_id: int) -> Optional[Dict[str, Any]]:
        """查询商品信息
        
        Args:
            goods_id: 商品信息ID
            
        Returns:
            商品信息或 None（失败时）
        """
        return self.query(goods_id)
    
    def create_goods(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建商品信息
        
        Args:
            param: 商品信息参数
            
        Returns:
            创建的商品信息或 None（失败时）
        """
        return self.create(param)
    
    def update_goods(self, goods_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新商品信息
        
        Args:
            goods_id: 商品信息ID
            param: 更新参数
            
        Returns:
            更新的商品信息或 None（失败时）
        """
        return self.update(goods_id, param)
    
    def delete_goods(self, goods_id: int) -> Optional[Dict[str, Any]]:
        """删除商品信息
        
        Args:
            goods_id: 商品信息ID
            
        Returns:
            删除的商品信息或 None（失败时）
        """
        return self.delete(goods_id)
    
    def count_goods(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计商品信息数量
        
        Returns:
            商品信息数量或 None（失败时）
        """
        return self.count(param)