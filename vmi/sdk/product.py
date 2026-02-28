"""Product SDK

产品 SDK 类，提供产品实体的 CRUD 操作。
"""

import logging
from typing import Any, Dict, List, Optional

# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class ProductSDK(VMISDKBase):
    """产品 SDK 类"""

    def __init__(self, work_session):
        """初始化产品 SDK

        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, "/vmi/product")

    def filter_product(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤产品

        Args:
            param: 过滤参数

        Returns:
            产品列表或 None（失败时）
        """
        return self.filter(param)

    def query_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """查询产品

        Args:
            product_id: 产品ID

        Returns:
            产品信息或 None（失败时）
        """
        return self.query(product_id)

    def create_product(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建产品

        Args:
            param: 产品参数

        Returns:
            创建的产品信息或 None（失败时）
        """
        return self.create(param)

    def update_product(
        self, product_id: int, param: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新产品

        Args:
            product_id: 产品ID
            param: 更新参数

        Returns:
            更新的产品信息或 None（失败时）
        """
        return self.update(product_id, param)

    def delete_product(self, product_id: int) -> Optional[Dict[str, Any]]:
        """删除产品

        Args:
            product_id: 产品ID

        Returns:
            删除的产品信息或 None（失败时）
        """
        return self.delete(product_id)

    def count_product(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计产品数量

        Returns:
            产品数量或 None（失败时）
        """
        return self.count(param)
