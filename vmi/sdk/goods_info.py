"""Goods Info SDK

商品SKU SDK 类，提供商品SKU实体的 CRUD 操作。
"""

import logging
from typing import Any, Dict, List, Optional

# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class GoodsInfoSDK(VMISDKBase):
    """商品SKU SDK 类"""

    def __init__(self, work_session):
        """初始化商品SKU SDK

        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, "/vmi/store/goodsInfo")

    def filter_goods_info(
        self, param: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """过滤商品SKU

        Args:
            param: 过滤参数

        Returns:
            商品SKU列表或 None（失败时）
        """
        return self.filter(param)

    def query_goods_info(self, goods_info_id: int) -> Optional[Dict[str, Any]]:
        """查询商品SKU

        Args:
            goods_info_id: 商品SKUID

        Returns:
            商品SKU信息或 None（失败时）
        """
        return self.query(goods_info_id)

    def create_goods_info(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建商品SKU

        Args:
            param: 商品SKU参数

        Returns:
            创建的商品SKU信息或 None（失败时）
        """
        return self.create(param)

    def update_goods_info(
        self, goods_info_id: int, param: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新商品SKU

        Args:
            goods_info_id: 商品SKUID
            param: 更新参数

        Returns:
            更新的商品SKU信息或 None（失败时）
        """
        return self.update(goods_info_id, param)

    def delete_goods_info(self, goods_info_id: int) -> Optional[Dict[str, Any]]:
        """删除商品SKU

        Args:
            goods_info_id: 商品SKUID

        Returns:
            删除的商品SKU信息或 None（失败时）
        """
        return self.delete(goods_info_id)

    def count_goods_info(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计商品SKU数量

        Returns:
            商品SKU数量或 None（失败时）
        """
        return self.count(param)
