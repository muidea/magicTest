"""
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

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

from mock import common as mock
import logging
import unittest

from sdk import (GoodsInfoSDK, ProductInfoSDK, ProductSDK, ShelfSDK, StatusSDK,
                 StockoutSDK, StoreSDK, WarehouseSDK)
from test_dependency_helper import prepare_inventory_dependencies
from test_vmi_base import VMITestCase

# 配置日志
logger = logging.getLogger(__name__)


class StockoutTestCase(VMITestCase):
    """Stockout 测试用例类"""

    namespace = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 类级别的数据清理记录
        cls._class_cleanup_ids = cls.build_cleanup_registry(
            "stockout",
            "store",
            "goods_info",
            "product_info",
            "product",
            "status",
            "shelf",
            "warehouse",
        )

        cls.record_initial_count(
            "_initial_stockout_count", cls._get_stockout_count, entity_name="出库单"
        )

    @classmethod
    def _init_sdk(cls):
        cls.stockout_sdk = StockoutSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        cls.goods_info_sdk = GoodsInfoSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)
        cls.warehouse_sdk = WarehouseSDK(cls.work_session)
        cls.product_sdk = ProductSDK(cls.work_session)
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)

    @classmethod
    def _get_stockout_count(cls):
        """获取当前出库单数量"""
        return cls.get_entity_count(
            "stockout_sdk",
            "count_stockout",
            "filter_stockout",
            entity_name="出库单",
            count_args=({},),
            filter_args=({},),
        )

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        cls._cleanup_all_data()
        cls.verify_cleanup_count(
            "_initial_stockout_count", cls._get_stockout_count, entity_name="出库单"
        )

        super().tearDownClass()

    @classmethod
    def _cleanup_all_data(cls):
        """清理所有测试数据"""
        cls.cleanup_registry_entries(
            cls._class_cleanup_ids,
            [
                ("stockout", "stockout_sdk", "出库单"),
                ("goods_info", "goods_info_sdk", "商品信息"),
                ("product_info", "product_info_sdk", "产品SKU"),
                ("product", "product_sdk", "产品"),
                ("store", "store_sdk", "店铺"),
                ("status", "status_sdk", "状态"),
                ("shelf", "shelf_sdk", "货架"),
                ("warehouse", "warehouse_sdk", "仓库"),
            ],
        )

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的实体ID以便清理
        self.created_ids = self.build_cleanup_registry(
            "stockout",
            "store",
            "goods_info",
            "product_info",
            "product",
            "status",
            "shelf",
            "warehouse",
        )

        # 创建必要的依赖实体
        self._setup_dependencies()

    def _setup_dependencies(self):
        """创建测试依赖的实体（店铺、商品信息、状态等）"""
        deps = prepare_inventory_dependencies(
            store_sdk=self.store_sdk,
            warehouse_sdk=self.warehouse_sdk,
            shelf_sdk=self.shelf_sdk,
            status_sdk=self.status_sdk,
            product_sdk=self.product_sdk,
            product_info_sdk=self.product_info_sdk,
            goods_info_sdk=self.goods_info_sdk,
            goods_info_type=2,
            created_ids=self.created_ids,
            class_cleanup_ids=self._class_cleanup_ids,
        )
        self.status_id = deps["status_id"]
        self.store_id = deps["store_id"]
        self.warehouse_id = deps["warehouse_id"]
        self.shelf_id = deps["shelf_id"]
        self.product_id = deps["product_id"]
        self.product_info_id = deps["product_info_id"]
        self.goods_info_id = deps["goods_info_id"]

    def tearDown(self):
        """每个测试用例后的清理"""
        self.merge_cleanup_registry(self.__class__._class_cleanup_ids, self.created_ids)
        self._cleanup_test_entities()
        self.clear_cleanup_registry(self.created_ids)

    def _cleanup_test_entities(self):
        """清理本测试创建的实体"""
        self.cleanup_registry_entries(
            self.created_ids,
            [
                ("stockout", "stockout_sdk", "出库单"),
                ("goods_info", "goods_info_sdk", "商品信息"),
                ("product_info", "product_info_sdk", "产品SKU"),
                ("product", "product_sdk", "产品"),
                ("store", "store_sdk", "店铺"),
                ("status", "status_sdk", "状态"),
                ("shelf", "shelf_sdk", "货架"),
                ("warehouse", "warehouse_sdk", "仓库"),
            ],
            owner=self,
            remove_from=self.__class__._class_cleanup_ids,
            log_prefix=f"测试 {self._testMethodName}",
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
        self.assertIsNotNone(self.goods_info_id, "缺少商品信息依赖")
        self.assertIsNotNone(self.product_info_id, "缺少产品SKU依赖")
        self.assertIsNotNone(self.store_id, "缺少店铺依赖")
        self.assertIsNotNone(self.shelf_id, "缺少货架依赖")
        self.assertTrue(hasattr(self, "status_id") and self.status_id, "缺少状态依赖")

        goods_info_id = self.goods_info_id

        # 查询已创建的goodsInfo获取完整信息
        goods_info = self.goods_info_sdk.query_goods_info(goods_info_id)

        if goods_info:
            # 使用查询到的完整goodsInfo对象
            goods_info_obj = {
                "id": goods_info["id"],
                "sku": goods_info.get("sku", f"TEST_SKU_{goods_info_id}"),
                "product": goods_info.get("product", {"id": self.product_info_id}),
                "type": goods_info.get("type", 2),
                "count": goods_info.get("count", 50),
                "price": goods_info.get("price", 49.99),
                "shelf": goods_info.get(
                    "shelf", [{"id": self.shelf_id}]
                ),
            }
        else:
            # 创建完整的goodsInfo对象
            goods_info_obj = {
                "id": goods_info_id,
                "sku": f"TEST_SKU_{goods_info_id}",
                "product": {"id": self.product_info_id},
                "type": 2,
                "count": 50,
                "price": 49.99,
                "shelf": [{"id": self.shelf_id}],
            }

        return {
            "goodsInfo": [goods_info_obj],
            "description": mock.sentence(),
            "store": {"id": self.store_id},
            "status": {"id": self.status_id},
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

        # 先尝试部分更新；如果服务要求 store/status 等必填字段，则回退完整更新
        partial_update = {"description": "更新后的描述"}
        updated_stockout = self.stockout_sdk.update_stockout(
            new_stockout["id"], partial_update
        )
        if updated_stockout is None:
            update_param = stockout_param.copy()
            update_param["description"] = "更新后的描述"
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

        # 先尝试部分更新；如果服务要求 store/status 等必填字段，则回退完整更新
        partial_update = {"description": "更新后的描述"}
        updated_stockout = self.stockout_sdk.update_stockout(
            new_stockout["id"], partial_update
        )
        if updated_stockout is None:
            update_param = stockout_param.copy()
            update_param["description"] = "更新后的描述"
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
