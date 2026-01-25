"""VMI SDK 包

提供 VMI 系统的 SDK 类，用于编写测试用例。
对应 VMI 实体定义中的 18 个核心实体。
"""

from .base import VMISDKBase
from .partner import PartnerSDK
from .store import StoreSDK
from .warehouse import WarehouseSDK
from .product import ProductSDK
from .shelf import ShelfSDK
from .product_info import ProductInfoSDK
from .stockin import StockinSDK
from .stockout import StockoutSDK
from .status import StatusSDK
from .credit import CreditSDK
from .credit_report import CreditReportSDK
from .credit_reward import CreditRewardSDK
from .reward_policy import RewardPolicySDK
from .order import OrderSDK
from .goods_item import GoodsItemSDK
from .goods import GoodsSDK
from .goods_info import GoodsInfoSDK
from .member import MemberSDK

# 导出所有 SDK 类
__all__ = [
    'VMISDKBase',
    'StatusSDK',
    'PartnerSDK',
    'WarehouseSDK',
    'ShelfSDK',
    'ProductSDK',
    'ProductInfoSDK',
    'StoreSDK',
    'MemberSDK',
    'GoodsSDK',
    'StockinSDK',
    'StockoutSDK',
    'GoodsInfoSDK',
    'OrderSDK',
    'GoodsItemSDK',
    'CreditSDK',
    'CreditReportSDK',
    'CreditRewardSDK',
    'RewardPolicySDK',
]