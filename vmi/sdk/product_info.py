"""Product Info SDK

产品 SKU 信息 SDK 类，提供产品 SKU 信息实体的 CRUD 操作。
对应实体定义中的 productInfo 实体。
"""

import logging
from typing import Optional, Dict, Any, List
# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class ProductInfoSDK(VMISDKBase):
    """产品 SKU 信息 SDK 类"""
    
    def __init__(self, work_session):
        """初始化产品 SKU 信息 SDK
        
        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, '/vmi/product/productInfo')  # 正确的路径：/vmi/product/productInfo
    
    def filter_product_info(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤产品 SKU 信息
        
        Args:
            param: 过滤参数
            
        Returns:
            产品 SKU 信息列表或 None（失败时）
        """
        return self.filter(param)
    
    def query_product_info(self, product_info_id: int) -> Optional[Dict[str, Any]]:
        """查询产品 SKU 信息
        
        Args:
            product_info_id: 产品 SKU 信息ID
            
        Returns:
            产品 SKU 信息或 None（失败时）
        """
        return self.query(product_info_id)
    
    def create_product_info(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建产品 SKU 信息
        
        Args:
            param: 产品 SKU 信息参数
            
        Returns:
            创建的产品 SKU 信息或 None（失败时）
        """
        return self.create(param)
    
    def update_product_info(self, product_info_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新产品 SKU 信息
        
        Args:
            product_info_id: 产品 SKU 信息ID
            param: 更新参数
            
        Returns:
            更新的产品 SKU 信息或 None（失败时）
        """
        return self.update(product_info_id, param)
    
    def delete_product_info(self, product_info_id: int) -> Optional[Dict[str, Any]]:
        """删除产品 SKU 信息
        
        Args:
            product_info_id: 产品 SKU 信息ID
            
        Returns:
            删除的产品 SKU 信息或 None（失败时）
        """
        return self.delete(product_info_id)
    
    def count_product_info(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计产品 SKU 信息数量
        
        Returns:
            产品 SKU 信息数量或 None（失败时）
        """
        return self.count(param)