"""Stockout SDK

出库单 SDK 类，提供出库单实体的 CRUD 操作。
"""

import logging
from typing import Any, Dict, List, Optional

# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class StockoutSDK(VMISDKBase):
    """出库单 SDK 类"""

    def __init__(self, work_session):
        """初始化出库单 SDK

        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, "/vmi/store/stockout")

    def filter_stockout(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤出库单

        Args:
            param: 过滤参数

        Returns:
            出库单列表或 None（失败时）
        """
        return self.filter(param)

    def query_stockout(self, stockout_id: int) -> Optional[Dict[str, Any]]:
        """查询出库单

        Args:
            stockout_id: 出库单ID

        Returns:
            出库单信息或 None（失败时）
        """
        return self.query(stockout_id)

    def create_stockout(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建出库单

        Args:
            param: 出库单参数

        Returns:
            创建的出库单信息或 None（失败时）
        """
        return self.create(param)

    def update_stockout(
        self, stockout_id: int, param: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新出库单

        Args:
            stockout_id: 出库单ID
            param: 更新参数

        Returns:
            更新的出库单信息或 None（失败时）
        """
        return self.update(stockout_id, param)

    def delete_stockout(self, stockout_id: int) -> Optional[Dict[str, Any]]:
        """删除出库单

        Args:
            stockout_id: 出库单ID

        Returns:
            删除的出库单信息或 None（失败时）
        """
        return self.delete(stockout_id)

    def count_stockout(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计出库单数量

        Returns:
            出库单数量或 None（失败时）
        """
        return self.count(param)
