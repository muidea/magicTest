"""Goods Item SDK

商品条目 SDK 类，提供商品条目实体的 CRUD 操作。
"""

import logging
from typing import Any, Dict, List, Optional

# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class GoodsItemSDK(VMISDKBase):
    """商品条目 SDK 类"""

    def __init__(self, work_session):
        """初始化商品条目 SDK

        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, "/vmi/order/goodsItem")

    def filter_goods_item(
        self, param: Dict[str, Any]
    ) -> Optional[List[Dict[str, Any]]]:
        """过滤商品条目

        Args:
            param: 过滤参数

        Returns:
            商品条目列表或 None（失败时）
        """
        return self.filter(param)

    def query_goods_item(self, goods_item_id: int) -> Optional[Dict[str, Any]]:
        """查询商品条目

        Args:
            goods_item_id: 商品条目ID

        Returns:
            商品条目信息或 None（失败时）
        """
        return self.query(goods_item_id)

    def create_goods_item(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建商品条目

        Args:
            param: 商品条目参数

        Returns:
            创建的商品条目信息或 None（失败时）
        """
        return self.create(param)

    def update_goods_item(
        self, goods_item_id: int, param: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新商品条目

        Args:
            goods_item_id: 商品条目ID
            param: 更新参数

        Returns:
            更新的商品条目信息或 None（失败时）
        """
        return self.update(goods_item_id, param)

    def delete_goods_item(self, goods_item_id: int) -> Optional[Dict[str, Any]]:
        """删除商品条目

        Args:
            goods_item_id: 商品条目ID

        Returns:
            删除的商品条目信息或 None（失败时）
        """
        return self.delete(goods_item_id)

    def count_goods_item(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计商品条目数量

        Returns:
            商品条目数量或 None（失败时）
        """
        return self.count(param)
