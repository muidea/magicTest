"""Credit SDK

积分信息 SDK 类，提供积分信息实体的 CRUD 操作。
"""

import logging
from typing import Any, Dict, List, Optional

# from session import session  # 已注释，使用base.py中的导入
from .base import VMISDKBase

# 配置日志
logger = logging.getLogger(__name__)


class CreditSDK(VMISDKBase):
    """积分信息 SDK 类"""

    def __init__(self, work_session):
        """初始化积分信息 SDK

        Args:
            work_session: MagicSession 实例
        """
        super().__init__(work_session, "/vmi/credit")

    def filter_credit(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤积分信息

        Args:
            param: 过滤参数

        Returns:
            积分信息列表或 None（失败时）
        """
        return self.filter(param)

    def query_credit(self, credit_id: int) -> Optional[Dict[str, Any]]:
        """查询积分信息

        Args:
            credit_id: 积分信息ID

        Returns:
            积分信息或 None（失败时）
        """
        return self.query(credit_id)

    def create_credit(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建积分信息

        Args:
            param: 积分信息参数

        Returns:
            创建的积分信息或 None（失败时）
        """
        return self.create(param)

    def update_credit(
        self, credit_id: int, param: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """更新积分信息

        Args:
            credit_id: 积分信息ID
            param: 更新参数

        Returns:
            更新的积分信息或 None（失败时）
        """
        return self.update(credit_id, param)

    def delete_credit(self, credit_id: int) -> Optional[Dict[str, Any]]:
        """删除积分信息

        Args:
            credit_id: 积分信息ID

        Returns:
            删除的积分信息或 None（失败时）
        """
        return self.delete(credit_id)

    def count_credit(self, param: Dict[str, Any] = None) -> Optional[int]:
        """统计积分信息数量

        Returns:
            积分信息数量或 None（失败时）
        """
        return self.count(param)
