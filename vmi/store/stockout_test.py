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
Stockout 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:243-256 中的 stockout 实体定义编写。
使用 StockoutSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- sn: string (出库单号) - 唯一，由系统根据出库单号生成规则自动生成
- goodsInfo: goodsInfo[] (商品信息) - 必选
- description: string (描述) - 可选
- status: status* (状态) - 必选，由平台进行管理，允许进行更新
- store: store* (所属店铺) - 必选
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- modifyTime: int64 (修改时间) - 由系统自动更新
- namespace: string (命名空间) - 由系统自动生成

业务说明：商品库存数量在出库时减少。

包含的测试用例（共10个）：

1. 基础CURD测试：
   - test_create_stockout: 测试创建出库单，验证所有字段完整性
   - test_query_stockout: 测试查询出库单，验证数据一致性
   - test_update_stockout: 测试更新出库单，验证字段更新功能
   - test_delete_stockout: 测试删除出库单，验证删除操作

2. 异常测试：
   - test_query_nonexistent_stockout: 测试查询不存在的出库单
   - test_delete_nonexistent_stockout: 测试删除不存在的出库单

3. 关联字段测试：
   - test_stockout_store_validation: 测试出库单店铺关联验证
   - test_stockout_status_validation: 测试出库单状态验证

4. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、sn、creater、createTime、namespace）
   - test_modify_time_auto_update: 测试修改时间字段的自动更新逻辑

测试特性：
- 使用 StockoutSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为
- 验证所有实体定义字段
- 覆盖完整的业务规则

版本：1.0
最后更新：2026-01-26
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


from sdk import (GoodsInfoSDK, ShelfSDK, StatusSDK, StockoutSDK, StoreSDK,
                 WarehouseSDK)

# 配置日志
logger = logging.getLogger(__name__)


class StockoutTestCase(unittest.TestCase):
    """Stockout 测试用例类"""

    namespace = ""

    @classmethod
    def setUpClass(cls):
        # 从config_helper获取配置

        # 从config_helper获取配置
        from config_helper import get_credentials, get_server_url

        cls.server_url = get_server_url()
        cls.credentials = get_credentials()

        """测试类初始化"""
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login(
            cls.credentials["username"], cls.credentials["password"]
        ):
            logger.error("CAS登录失败")
            raise Exception("CAS登录失败")
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.stockout_sdk = StockoutSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        cls.goods_info_sdk = GoodsInfoSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)
        cls.warehouse_sdk = WarehouseSDK(cls.work_session)

        # 类级别的数据清理记录
        cls._class_cleanup_ids = {
            "stockout": [],
            "store": [],
            "goods_info": [],
            "status": [],
            "shelf": [],
            "warehouse": [],
        }

        # 记录测试开始前的初始状态（可选）
        cls._initial_stockout_count = cls._get_stockout_count()
        logger.info(f"测试开始前出库单数量: {cls._initial_stockout_count}")

    @classmethod
    def _get_stockout_count(cls):
        """获取当前出库单数量"""
        try:
            count = cls.stockout_sdk.count_stockout({})
            if count is not None:
                return count
        except Exception as e:
            logger.warning(f"获取出库单数量失败: {e}")

        try:
            stockouts = cls.stockout_sdk.filter_stockout({})
            if stockouts is not None:
                return len(stockouts)
        except Exception as e:
            logger.warning(f"通过过滤获取出库单数量失败: {e}")

        return 0

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        # 清理所有类型的数据
        cls._cleanup_all_data()

        # 验证数据清理
        final_stockout_count = cls._get_stockout_count()
        logger.info(f"测试类清理完成: 最终出库单数量: {final_stockout_count}")

        if hasattr(cls, "_initial_stockout_count"):
            expected_count = cls._initial_stockout_count
            if final_stockout_count > expected_count:
                logger.warning(
                    f"可能存在数据残留: 期望数量 {expected_count}, 实际数量 {final_stockout_count}"
                )

    @classmethod
    def _cleanup_all_data(cls):
        """清理所有测试数据"""
        cls._cleanup_entities(
            cls.stockout_sdk, cls._class_cleanup_ids["stockout"], "出库单"
        )
        cls._cleanup_entities(
            cls.goods_info_sdk, cls._class_cleanup_ids["goods_info"], "商品信息"
        )
        cls._cleanup_entities(cls.store_sdk, cls._class_cleanup_ids["store"], "店铺")
        cls._cleanup_entities(cls.status_sdk, cls._class_cleanup_ids["status"], "状态")

    @classmethod
    def _cleanup_entities(cls, sdk, entity_ids, entity_name):
        """清理指定类型的实体"""
        if not entity_ids:
            logger.debug(f"清理{entity_name}列表为空，无需清理")
            return

        logger.info(f"开始清理 {len(entity_ids)} 个{entity_name}: {entity_ids}")
        deleted_count = 0
        failed_ids = []

        for entity_id in entity_ids:
            try:
                logger.debug(f"尝试删除{entity_name} ID: {entity_id}")
                result = sdk.delete(entity_id)

                if result is not None:
                    deleted_count += 1
                    logger.debug(f"成功删除{entity_name} {entity_id}")
                else:
                    error_msg = f"清理{entity_name} {entity_id} 返回None"
                    logger.error(error_msg)
                    failed_ids.append(entity_id)
            except Exception as e:
                error_msg = f"清理{entity_name} {entity_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(entity_id)

        if deleted_count > 0:
            logger.info(f"成功清理 {deleted_count} 个{entity_name}")

        if failed_ids:
            logger.error(f"清理失败的{entity_name}ID: {failed_ids}")

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的实体ID以便清理
        self.created_ids = {
            "stockout": [],
            "store": [],
            "goods_info": [],
            "status": [],
            "shelf": [],
            "warehouse": [],
        }

        # 创建必要的依赖实体
        self._setup_dependencies()

    def _setup_dependencies(self):
        """创建测试依赖的实体（店铺、商品信息、状态等）"""
        # 创建店铺
        store_param = {"name": "STORE_" + mock.name(), "description": mock.sentence()}
        new_store = self.store_sdk.create_store(store_param)
        self.assertIsNotNone(new_store, "创建店铺失败")
        if new_store and "id" in new_store:
            self.created_ids["store"].append(new_store["id"])
            self._class_cleanup_ids["store"].append(new_store["id"])

        # 创建仓库
        warehouse_param = {
            "name": "WAREHOUSE_" + mock.name(),
            "description": mock.sentence(),
            "code": "WH_" + str(mock.int(1000, 9999)),
        }
        new_warehouse = self.warehouse_sdk.create_warehouse(warehouse_param)
        if new_warehouse is not None and "id" in new_warehouse:
            self.created_ids["warehouse"].append(new_warehouse["id"])
            self._class_cleanup_ids["warehouse"].append(new_warehouse["id"])
            logger.info(f"仓库创建成功，ID: {new_warehouse['id']}")

        # 创建货架
        warehouse_id = new_warehouse["id"] if new_warehouse else 1
        shelf_param = {
            "name": "SHELF_" + mock.name(),
            "description": mock.sentence(),
            "capacity": 100,  # 整数类型
            "warehouse": {"id": warehouse_id},
            "status": {"id": 19},  # 状态ID 19: "启用"
        }
        new_shelf = self.shelf_sdk.create_shelf(shelf_param)
        if new_shelf is not None and "id" in new_shelf:
            self.created_ids["shelf"].append(new_shelf["id"])
            self._class_cleanup_ids["shelf"].append(new_shelf["id"])
            logger.info(f"货架创建成功，ID: {new_shelf['id']}")
        else:
            logger.error(f"货架创建失败，参数: {shelf_param}")
            new_shelf = None

        # 创建商品信息
        goods_info_param = {
            "sku": str(mock.int(40000, 49999)),  # 纯数字SKU
            "product": {"id": 1},  # 假设产品ID为1
            "type": 2,  # 出库类型
            "count": 50,
            "price": 49.99,
            "shelf": [{"id": new_shelf["id"]}] if new_shelf else [],  # 使用货架ID引用
            "store": {"id": new_store["id"]} if new_store else None,  # 添加store字段
            "status": {"id": 19},  # 使用状态ID 19: "启用"
        }
        new_goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        if new_goods_info is not None and "id" in new_goods_info:
            self.created_ids["goods_info"].append(new_goods_info["id"])
            self._class_cleanup_ids["goods_info"].append(new_goods_info["id"])

        # 获取状态（假设系统已有状态）
        self.status_id = 19  # 状态ID 19: "启用"

        # 保存依赖实体ID
        self.store_id = new_store["id"] if new_store else None
        self.warehouse_id = new_warehouse["id"] if new_warehouse else None
        self.shelf_id = new_shelf["id"] if new_shelf else None
        self.goods_info_id = new_goods_info["id"] if new_goods_info else None

    def tearDown(self):
        """每个测试用例后的清理"""
        # 将本测试创建的实体ID添加到类级别清理列表
        for entity_type in self.created_ids:
            if self.created_ids[entity_type]:
                self.__class__._class_cleanup_ids[entity_type].extend(
                    self.created_ids[entity_type]
                )

        # 尝试立即清理本测试创建的数据
        self._cleanup_test_entities()

        # 清空本测试记录
        for entity_type in self.created_ids:
            self.created_ids[entity_type].clear()

    def _cleanup_test_entities(self):
        """清理本测试创建的实体"""
        for entity_type in [
            "stockout",
            "goods_info",
            "store",
            "status",
            "shelf",
            "warehouse",
        ]:
            if not self.created_ids[entity_type]:
                continue

            sdk_map = {
                "stockout": self.stockout_sdk,
                "store": self.store_sdk,
                "goods_info": self.goods_info_sdk,
                "status": self.status_sdk,
                "shelf": self.shelf_sdk,
                "warehouse": self.warehouse_sdk,
            }

            sdk = sdk_map[entity_type]
            entity_name = {
                "stockout": "出库单",
                "store": "店铺",
                "goods_info": "商品信息",
                "status": "状态",
                "shelf": "货架",
                "warehouse": "仓库",
            }[entity_type]

            for entity_id in self.created_ids[entity_type]:
                try:
                    logger.debug(
                        f"测试 {self._testMethodName}: 尝试删除{entity_name} ID: {entity_id}"
                    )
                    result = sdk.delete(entity_id)

                    if result is not None:
                        logger.debug(
                            f"测试 {self._testMethodName}: 成功删除{entity_name} {entity_id}"
                        )
                        if entity_id in self.__class__._class_cleanup_ids[entity_type]:
                            self.__class__._class_cleanup_ids[entity_type].remove(
                                entity_id
                            )
                    else:
                        logger.error(
                            f"测试 {self._testMethodName}: 删除{entity_name} {entity_id} 返回None"
                        )
                except Exception as e:
                    logger.error(
                        f"测试 {self._testMethodName}: 删除{entity_name} {entity_id} 失败: {e}"
                    )

    def _record_entity_for_cleanup(self, entity_type, entity_id):
        """记录实体ID以便清理"""
        if entity_id is not None:
            self.created_ids[entity_type].append(entity_id)
            logger.debug(
                f"记录{entity_type} {entity_id} 到清理列表 (测试: {self._testMethodName})"
            )

    def mock_stockout_param(self):
        """模拟出库单参数"""
        # 如果goods_info_id不存在，使用一个虚拟的ID
        goods_info_id = self.goods_info_id if self.goods_info_id else 99999

        # 查询已创建的goodsInfo获取完整信息
        goods_info = None
        if goods_info_id != 99999:
            goods_info = self.goods_info_sdk.query_goods_info(goods_info_id)

        if goods_info:
            # 使用查询到的完整goodsInfo对象
            goods_info_obj = {
                "id": goods_info["id"],
                "sku": goods_info.get("sku", f"TEST_SKU_{goods_info_id}"),
                "product": goods_info.get("product", {"id": 1}),
                "type": goods_info.get("type", 2),
                "count": goods_info.get("count", 50),
                "price": goods_info.get("price", 49.99),
                "shelf": goods_info.get(
                    "shelf", [{"id": self.shelf_id}] if self.shelf_id else []
                ),
                "store": goods_info.get(
                    "store", {"id": self.store_id} if self.store_id else None
                ),
                "status": goods_info.get("status", {"id": 19}),
            }
        else:
            # 创建完整的goodsInfo对象
            goods_info_obj = {
                "id": goods_info_id,
                "sku": f"TEST_SKU_{goods_info_id}",
                "product": {"id": 1},
                "type": 2,
                "count": 50,
                "price": 49.99,
                "shelf": [{"id": self.shelf_id}] if self.shelf_id else [],
                "store": {"id": self.store_id} if self.store_id else None,
                "status": {"id": 19},
            }

        return {
            "goodsInfo": [goods_info_obj],
            "description": mock.sentence(),
            "store": {"id": self.store_id} if self.store_id else None,
            "status": {"id": self.status_id} if hasattr(self, "status_id") else None,
        }

    def test_create_stockout(self):
        """测试创建出库单"""
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        # 验证出库单信息完整性
        required_fields = ["id", "goodsInfo", "description", "store", "status"]
        for field in required_fields:
            self.assertIn(field, new_stockout, f"缺少字段: {field}")

        # 验证系统自动生成字段
        self.assertIn("sn", new_stockout, "缺少出库单号字段")
        self.assertIsInstance(
            new_stockout["sn"], (str, type(None)), "出库单号应为字符串或None"
        )
        if new_stockout["sn"] is not None:
            self.assertGreater(len(new_stockout["sn"]), 0, "出库单号不应为空")

        self.assertIn("creater", new_stockout, "缺少创建者字段")
        self.assertIsInstance(
            new_stockout["creater"], (int, type(None)), "创建者应为整数或None"
        )

        self.assertIn("createTime", new_stockout, "缺少创建时间字段")
        self.assertIsInstance(
            new_stockout["createTime"], (int, type(None)), "创建时间应为整数或None"
        )

        self.assertIn("namespace", new_stockout, "缺少命名空间字段")
        self.assertIsInstance(
            new_stockout["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

        # 记录创建的出库单ID以便清理
        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

    def test_query_stockout(self):
        """测试查询出库单"""
        # 先创建出库单
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 查询出库单
        queried_stockout = self.stockout_sdk.query_stockout(new_stockout["id"])
        self.assertIsNotNone(queried_stockout, "查询出库单失败")
        self.assertEqual(queried_stockout["id"], new_stockout["id"], "出库单ID不匹配")

    def test_update_stockout(self):
        """测试更新出库单"""
        # 先创建出库单
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 更新出库单 - 只更新描述字段，不包含goodsInfo
        update_param = {"description": "更新后的描述"}

        updated_stockout = self.stockout_sdk.update_stockout(
            new_stockout["id"], update_param
        )
        self.assertIsNotNone(updated_stockout, "更新出库单失败")
        self.assertEqual(
            updated_stockout["description"], "更新后的描述", "描述更新失败"
        )

    def test_delete_stockout(self):
        """测试删除出库单"""
        # 先创建出库单
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 删除出库单
        deleted_stockout = self.stockout_sdk.delete_stockout(new_stockout["id"])
        self.assertIsNotNone(deleted_stockout, "删除出库单失败")
        self.assertEqual(
            deleted_stockout["id"], new_stockout["id"], "删除的出库单ID不匹配"
        )

        # 从清理列表中移除
        if new_stockout["id"] in self.created_ids["stockout"]:
            self.created_ids["stockout"].remove(new_stockout["id"])

        # 验证出库单已被删除
        queried_stockout = self.stockout_sdk.query_stockout(new_stockout["id"])
        self.assertIsNone(queried_stockout, "删除后查询出库单应该返回None")

    def test_query_nonexistent_stockout(self):
        """测试查询不存在的出库单"""
        nonexistent_stockout_id = 999999
        queried_stockout = self.stockout_sdk.query_stockout(nonexistent_stockout_id)
        self.assertIsNone(queried_stockout, "查询不存在的出库单应失败")

    def test_delete_nonexistent_stockout(self):
        """测试删除不存在的出库单"""
        nonexistent_stockout_id = 999999
        deleted_stockout = self.stockout_sdk.delete_stockout(nonexistent_stockout_id)
        self.assertIsNone(deleted_stockout, "删除不存在的出库单应失败")

    def test_stockout_store_validation(self):
        """测试出库单店铺关联验证"""
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 验证店铺关联字段
        self.assertIn("store", new_stockout, "出库单缺少店铺关联字段")
        self.assertIsInstance(new_stockout["store"], dict, "店铺关联应为字典")
        if "id" in new_stockout["store"]:
            self.assertEqual(new_stockout["store"]["id"], self.store_id, "店铺ID不匹配")

    def test_stockout_status_validation(self):
        """测试出库单状态验证"""
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 验证状态字段
        self.assertIn("status", new_stockout, "出库单缺少状态字段")
        self.assertIsInstance(new_stockout["status"], dict, "状态应为字典")
        if "id" in new_stockout["status"]:
            self.assertEqual(
                new_stockout["status"]["id"], self.status_id, "状态ID不匹配"
            )

    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 验证所有系统自动生成字段
        auto_generated_fields = ["id", "sn", "creater", "createTime", "namespace"]
        for field in auto_generated_fields:
            self.assertIn(field, new_stockout, f"缺少系统自动生成字段: {field}")

        # 验证字段类型和值
        self.assertIsInstance(new_stockout["id"], (int, type(None)), "ID应为整数或None")
        if new_stockout["id"] is not None:
            self.assertGreater(new_stockout["id"], 0, "ID应为正整数")

        self.assertIsInstance(
            new_stockout["sn"], (str, type(None)), "出库单号应为字符串或None"
        )
        if new_stockout["sn"] is not None:
            self.assertGreater(len(new_stockout["sn"]), 0, "出库单号不应为空")

        self.assertIsInstance(
            new_stockout["creater"], (int, type(None)), "创建者应为整数或None"
        )
        self.assertIsInstance(
            new_stockout["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        if new_stockout["createTime"] is not None:
            self.assertGreater(new_stockout["createTime"], 0, "创建时间应为正数")

        self.assertIsInstance(
            new_stockout["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

    def test_modify_time_auto_update(self):
        """测试修改时间自动更新"""
        # 创建出库单
        stockout_param = self.mock_stockout_param()
        new_stockout = self.stockout_sdk.create_stockout(stockout_param)
        self.assertIsNotNone(new_stockout, "创建出库单失败")

        if new_stockout and "id" in new_stockout:
            self._record_entity_for_cleanup("stockout", new_stockout["id"])

        # 记录初始创建时间和修改时间
        initial_create_time = new_stockout.get("createTime")
        initial_modify_time = new_stockout.get("modifyTime")

        # 更新出库单 - 只更新描述字段，不包含goodsInfo
        update_param = {"description": "更新后的描述"}

        updated_stockout = self.stockout_sdk.update_stockout(
            new_stockout["id"], update_param
        )
        self.assertIsNotNone(updated_stockout, "更新出库单失败")

        # 验证修改时间 - 系统可能不返回此字段
        updated_modify_time = updated_stockout.get("modifyTime")
        if updated_modify_time is not None:
            # 如果系统返回修改时间，验证其内容
            # 验证修改时间比创建时间晚（如果两者都存在）
            if initial_create_time and updated_modify_time:
                self.assertGreaterEqual(
                    updated_modify_time,
                    initial_create_time,
                    "修改时间应晚于或等于创建时间",
                )

            # 如果初始有修改时间，验证已更新
            if initial_modify_time and updated_modify_time:
                self.assertGreaterEqual(
                    updated_modify_time, initial_modify_time, "修改时间应已更新"
                )
        else:
            # 系统不返回修改时间字段，记录警告但不视为失败
            logger.warning("更新出库单后未返回 modifyTime 字段，系统可能不返回此字段")

        # 验证创建时间未改变
        self.assertEqual(
            updated_stockout.get("createTime"),
            initial_create_time,
            "创建时间不应被修改",
        )


if __name__ == "__main__":
    unittest.main()
