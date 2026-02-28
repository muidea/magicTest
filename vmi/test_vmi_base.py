#!/usr/bin/env python3
"""
import os
import sys

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(parent_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")
if session_path not in sys.path:
    sys.path.insert(0, session_path)

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")
if cas_dir not in sys.path:
    sys.path.insert(0, cas_dir)

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")
if mock_dir not in sys.path:
    sys.path.insert(0, mock_dir)
VMI 模块测试基类
为所有模块测试提供统一的初始化和清理逻辑

使用方法：
    from test_vmi_base import VMITestCase

    class TestStore(VMITestCase):
        def test_create_store(self):
            # 使用 self.store_sdk
            pass
"""

import os
import sys

# 添加项目根目录到Python路径
# 根据文件所在位置向上查找项目根目录
file_dir = os.path.dirname(os.path.abspath(__file__))
# session模块在 /home/rangh/codespace/magicTest/session
# 测试文件可能在 vmi/ 或 vmi/subdir/ 下
# 需要向上找到 magicTest 目录
project_root = file_dir
while project_root and not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    parent = os.path.dirname(project_root)
    if parent == project_root:  # 到达根目录
        break
    project_root = parent

# 如果没找到，使用默认路径
if not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    # 根据文件位置确定项目根目录
    if os.path.basename(file_dir) in ['credit', 'order', 'partner', 'product', 'status', 'store', 'warehouse']:
        # 在子目录下，向上两级
        project_root = os.path.dirname(os.path.dirname(file_dir))
    else:
        # 在vmi目录下，向上一级
        project_root = os.path.dirname(file_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")
if session_path not in sys.path:
    sys.path.insert(0, session_path)

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")
if cas_dir not in sys.path:
    sys.path.insert(0, cas_dir)

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")
if mock_dir not in sys.path:
    sys.path.insert(0, mock_dir)

# 确保vmi目录在路径中（用于导入sdk模块）
vmi_dir = os.path.join(project_root, "vmi")
if vmi_dir not in sys.path:
    sys.path.insert(0, vmi_dir)



# 添加项目根目录到Python路径
# 根据文件所在位置向上查找项目根目录
file_dir = os.path.dirname(os.path.abspath(__file__))
# session模块在 /home/rangh/codespace/magicTest/session
# 测试文件可能在 vmi/ 或 vmi/subdir/ 下
# 需要向上找到 magicTest 目录
project_root = file_dir
while project_root and not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    parent = os.path.dirname(project_root)
    if parent == project_root:  # 到达根目录
        break
    project_root = parent

# 如果没找到，使用默认路径
if not os.path.exists(os.path.join(project_root, 'session', 'session.py')):
    # 根据文件位置确定项目根目录
    if os.path.basename(file_dir) in ['credit', 'order', 'partner', 'product', 'status', 'store', 'warehouse']:
        # 在子目录下，向上两级
        project_root = os.path.dirname(os.path.dirname(file_dir))
    else:
        # 在vmi目录下，向上一级
        project_root = os.path.dirname(file_dir)

# 确保session模块在路径中
session_path = os.path.join(project_root, "session")

# 确保cas模块在路径中
cas_dir = os.path.join(project_root, "cas")

# 确保mock模块在路径中
mock_dir = os.path.join(project_root, "mock")


from session import MagicSession
from cas.cas import Cas
from mock import common as mock
import logging
import unittest
import warnings
from typing import Any, Dict, List, Optional, Type


logger = logging.getLogger(__name__)


class VMITestCase(unittest.TestCase):
    """VMI 模块测试基类

    提供统一的：
    1. 会话初始化和登录
    2. SDK 实例管理
    3. 测试数据清理
    4. 便捷的断言方法
    """

    namespace = ""

    _cleanup_ids: Dict[str, List[str]] = {}

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        from config_helper import get_credentials, get_server_url

        warnings.simplefilter("ignore", ResourceWarning)

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)

        if not cls.cas_session.login(
            cls.credentials["username"], cls.credentials["password"]
        ):
            logger.error("CAS登录失败")
            raise Exception("CAS登录失败")

        cls.work_session.bind_token(cls.cas_session.get_session_token())

        cls._cleanup_ids = {}
        cls._init_sdk()

        logger.info(f"{cls.__name__}: 初始化完成")

    @classmethod
    def _init_sdk(cls):
        """初始化SDK实例 - 子类可重写"""
        pass

    @classmethod
    def tearDownClass(cls):
        """测试类清理 - 清理测试数据"""
        cls._cleanup_test_data()

        if hasattr(cls, "work_session"):
            try:
                cls.cas_session.logout()
            except:
                pass

        logger.info(f"{cls.__name__}: 清理完成")

    @classmethod
    def _cleanup_test_data(cls):
        """清理测试数据 - 子类可重写"""
        pass

    @classmethod
    def _register_cleanup(cls, entity_type: str, entity_id: str):
        """注册需要清理的实体ID"""
        if entity_type not in cls._cleanup_ids:
            cls._cleanup_ids[entity_type] = []
        cls._cleanup_ids[entity_type].append(entity_id)

    def assertEntityCreated(self, entity: Dict[str, Any], entity_type: str = "实体"):
        """断言实体创建成功"""
        self.assertIsNotNone(entity, f"{entity_type}创建失败：返回None")
        self.assertIn("id", entity, f"{entity_type}创建失败：缺少id字段")
        self._register_cleanup(entity_type, entity["id"])

    def assertEntityField(
        self, entity: Dict[str, Any], field: str, expected_value: Any = None
    ):
        """断言实体字段值"""
        self.assertIn(field, entity, f"实体缺少字段: {field}")
        if expected_value is not None:
            self.assertEqual(
                entity[field],
                expected_value,
                f"字段{field}值不匹配: 期望{expected_value}, 实际{entity[field]}",
            )

    def assertEntityNotEmpty(self, entity: Dict[str, Any], fields: List[str]):
        """断言实体字段非空"""
        for field in fields:
            self.assertIn(field, entity, f"实体缺少字段: {field}")
            self.assertIsNotNone(entity[field], f"字段{field}为空")
            if isinstance(entity[field], str):
                self.assertTrue(len(entity[field]) > 0, f"字段{field}为空字符串")


class StoreTestCase(VMITestCase):
    """Store 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ShelfSDK, StoreSDK

        cls.store_sdk = StoreSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)


class ProductTestCase(VMITestCase):
    """Product 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ProductInfoSDK, ProductSDK

        cls.product_sdk = ProductSDK(cls.work_session)
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)


class WarehouseTestCase(VMITestCase):
    """Warehouse 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import ShelfSDK, WarehouseSDK

        cls.warehouse_sdk = WarehouseSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)


class CreditTestCase(VMITestCase):
    """Credit 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import CreditSDK, PartnerSDK

        cls.credit_sdk = CreditSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)


class OrderTestCase(VMITestCase):
    """Order 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import GoodsItemSDK, OrderSDK

        cls.order_sdk = OrderSDK(cls.work_session)
        cls.goods_item_sdk = GoodsItemSDK(cls.work_session)


class PartnerTestCase(VMITestCase):
    """Partner 模块测试基类"""

    @classmethod
    def _init_sdk(cls):
        from sdk import PartnerSDK

        cls.partner_sdk = PartnerSDK(cls.work_session)


if __name__ == "__main__":
    print("VMI 模块测试基类")
    print("提供 VMITestCase 及各模块专用测试基类")
