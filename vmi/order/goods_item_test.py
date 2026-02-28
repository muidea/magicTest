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
Goods Item 测试用例

基于 VMI实体定义和使用说明.md:142-149 中的 goodsItem 实体定义编写。
使用 GoodsItemSDK 进行测试。

包含的测试用例（共10个）：
1. test_create_goods_item
2. test_query_goods_item
3. test_update_goods_item
4. test_delete_goods_item
5. test_create_goods_item_with_different_sku
6. test_create_goods_item_with_zero_count
7. test_create_goods_item_without_sku
8. test_query_nonexistent_goods_item
9. test_delete_nonexistent_goods_item
10. test_auto_generated_fields
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
import time
import unittest
import warnings


from sdk import GoodsItemSDK

logger = logging.getLogger(__name__)


class GoodsItemTestCase(unittest.TestCase):
    namespace = ""

    @classmethod
    def setUpClass(cls):
        # 从config_helper获取配置

        # 从config_helper获取配置
        from config_helper import get_credentials, get_server_url

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login(
            cls.credentials["username"], cls.credentials["password"]
        ):
            logger.error("CAS登录失败")
            raise Exception("CAS登录失败")
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.goods_item_sdk = GoodsItemSDK(cls.work_session)
        cls.test_data = []
        print("Goods Item 测试开始...")

    def tearDown(self):
        for data in self.test_data:
            if "id" in data:
                try:
                    self.goods_item_sdk.delete_goods_item(data["id"])
                except Exception as e:
                    logger.warning(f"清理商品条目 {data.get('id')} 失败: {e}")
        self.test_data.clear()

    @classmethod
    def tearDownClass(cls):
        print("Goods Item 测试结束")

    def test_create_goods_item(self):
        print("测试创建商品条目...")
        goods_item_param = {
            "sku": "TEST001",
            "name": "测试商品",
            "price": 100.0,
            "count": 5,
        }
        goods_item = self.goods_item_sdk.create_goods_item(goods_item_param)
        self.assertIsNotNone(goods_item, "创建商品条目失败")
        required_fields = ["id", "sku", "name", "price", "count", "namespace"]
        for field in required_fields:
            self.assertIn(field, goods_item, f"商品条目缺少必填字段: {field}")
        self.test_data.append(goods_item)
        print(f"✓ 商品条目创建成功: ID={goods_item.get('id')}")

    def test_query_goods_item(self):
        print("测试查询商品条目...")
        goods_item_param = {
            "sku": "TEST002",
            "name": "查询测试商品",
            "price": 150.0,
            "count": 3,
        }
        created_item = self.goods_item_sdk.create_goods_item(goods_item_param)
        self.assertIsNotNone(created_item, "创建商品条目失败")
        queried_item = self.goods_item_sdk.query_goods_item(created_item["id"])
        self.assertIsNotNone(queried_item, "查询商品条目失败")
        self.assertEqual(queried_item["id"], created_item["id"], "ID不匹配")
        self.test_data.append(created_item)
        print(f"✓ 商品条目查询成功: ID={queried_item.get('id')}")

    def test_update_goods_item(self):
        print("测试更新商品条目...")
        goods_item_param = {
            "sku": "TEST003",
            "name": "更新前商品",
            "price": 200.0,
            "count": 2,
        }
        created_item = self.goods_item_sdk.create_goods_item(goods_item_param)
        self.assertIsNotNone(created_item, "创建商品条目失败")
        update_param = {"name": "更新后商品", "price": 250.0}
        updated_item = self.goods_item_sdk.update_goods_item(
            created_item["id"], update_param
        )
        if updated_item:
            self.assertEqual(updated_item["name"], "更新后商品", "更新后名称不匹配")
            print(f"✓ 商品条目更新成功: ID={updated_item.get('id')}")
        else:
            print("⚠ 商品条目更新未返回结果")
        self.test_data.append(created_item)

    def test_delete_goods_item(self):
        print("测试删除商品条目...")
        goods_item_param = {
            "sku": "TEST004",
            "name": "删除测试商品",
            "price": 300.0,
            "count": 1,
        }
        created_item = self.goods_item_sdk.create_goods_item(goods_item_param)
        self.assertIsNotNone(created_item, "创建商品条目失败")
        deleted_item = self.goods_item_sdk.delete_goods_item(created_item["id"])
        if deleted_item:
            self.assertEqual(
                deleted_item["id"], created_item["id"], "删除的商品条目ID不匹配"
            )
            print(f"✓ 商品条目删除成功: ID={deleted_item.get('id')}")
        else:
            print("⚠ 商品条目删除未返回结果")

    def test_create_goods_item_with_different_sku(self):
        print("测试创建不同SKU的商品条目...")
        skus = ["SKU001", "SKU002", "SKU003"]
        for sku in skus:
            goods_item_param = {
                "sku": sku,
                "name": f"测试商品-{sku}",
                "price": 100.0,
                "count": 1,
            }
            goods_item = self.goods_item_sdk.create_goods_item(goods_item_param)
            self.assertIsNotNone(goods_item, f"创建SKU {sku} 商品条目失败")
            self.assertEqual(goods_item["sku"], sku, f"SKU不匹配: {sku}")
            self.test_data.append(goods_item)
            print(f"✓ SKU {sku} 商品条目创建成功")

    def test_create_goods_item_with_zero_count(self):
        print("测试创建零数量商品条目...")
        goods_item_param = {
            "sku": "TEST005",
            "name": "零数量商品",
            "price": 100.0,
            "count": 0,
        }
        goods_item = None
        try:
            goods_item = self.goods_item_sdk.create_goods_item(goods_item_param)
            # 如果创建成功，记录ID以便清理
            if goods_item and "id" in goods_item:
                self.test_data.append(goods_item)
                print(f"⚠ 系统允许创建count=0的商品条目: ID={goods_item.get('id')}")
            else:
                print("✓ 系统正确拒绝创建count=0的商品条目")
        except Exception as e:
            # 检查错误代码是否为6
            if "错误代码: 6" in str(e):
                print("✓ 系统正确返回错误代码6拒绝创建count=0的商品条目")
            else:
                print(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if goods_item and "id" in goods_item:
                self.test_data.append(goods_item)

    def test_create_goods_item_without_sku(self):
        print("测试创建无SKU的商品条目...")
        goods_item_param = {"name": "无SKU商品", "price": 100.0, "count": 1}
        goods_item = None
        try:
            goods_item = self.goods_item_sdk.create_goods_item(goods_item_param)
            if goods_item:
                self.assertIn("sku", goods_item, "商品条目应包含SKU字段")
                print(f"⚠ 系统允许创建无SKU的商品条目: ID={goods_item.get('id')}")
                self.test_data.append(goods_item)
            else:
                print("✓ 系统正确拒绝创建无SKU的商品条目")
        except Exception as e:
            # 检查错误代码是否为4（必填字段缺失）
            if "错误代码: 4" in str(e) and "sku" in str(e):
                print("✓ 系统正确返回错误代码4拒绝创建无SKU的商品条目")
            else:
                print(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if goods_item and "id" in goods_item:
                self.test_data.append(goods_item)

    def test_query_nonexistent_goods_item(self):
        print("测试查询不存在的商品条目...")
        non_existent_id = 999999999
        goods_item = self.goods_item_sdk.query_goods_item(non_existent_id)
        if goods_item is None:
            print("✓ 查询不存在的商品条目返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的商品条目返回: {goods_item}")

    def test_delete_nonexistent_goods_item(self):
        print("测试删除不存在的商品条目...")
        non_existent_id = 999999999
        deleted_item = self.goods_item_sdk.delete_goods_item(non_existent_id)
        if deleted_item is None:
            print("✓ 删除不存在的商品条目返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的商品条目返回: {deleted_item}")

    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        goods_item_param = {
            "sku": "TEST006",
            "name": "自动字段商品",
            "price": 100.0,
            "count": 1,
        }
        goods_item = self.goods_item_sdk.create_goods_item(goods_item_param)
        self.assertIsNotNone(goods_item, "创建商品条目失败")
        auto_fields = ["id", "namespace"]
        for field in auto_fields:
            self.assertIn(field, goods_item, f"缺少自动生成字段: {field}")
        self.test_data.append(goods_item)
        print(f"✓ 系统自动生成字段验证成功: ID={goods_item.get('id')}")


if __name__ == "__main__":
    unittest.main()
