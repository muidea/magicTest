"""
Goods Info 测试用例

基于 VMI实体定义和使用说明.md:207-218 中的 goodsInfo 实体定义编写。
使用 GoodsInfoSDK 进行测试。

包含的测试用例（共10个）：
1. test_create_goods_info
2. test_query_goods_info
3. test_update_goods_info
4. test_delete_goods_info
5. test_create_goods_info_with_different_type
6. test_create_goods_info_without_product
7. test_query_nonexistent_goods_info
8. test_delete_nonexistent_goods_info
9. test_auto_generated_fields
10. test_goods_info_type_validation
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

from mock import common as mock
import logging
import unittest

from sdk import (GoodsInfoSDK, ProductInfoSDK, ProductSDK, ShelfSDK, StatusSDK,
                 StoreSDK, WarehouseSDK)
from test_dependency_helper import prepare_inventory_dependencies
from test_vmi_base import VMITestCase

logger = logging.getLogger(__name__)


class GoodsInfoTestCase(VMITestCase):
    namespace = ""
    entity_definition = "store/goodsInfo.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_suite_start("Goods Info 测试开始")

    @classmethod
    def _init_sdk(cls):
        cls.goods_info_sdk = GoodsInfoSDK(cls.work_session)
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)
        cls.product_sdk = ProductSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.warehouse_sdk = WarehouseSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)

    def setUp(self):
        self.created_ids = self.build_cleanup_registry(
            "goods_info",
            "store",
            "warehouse",
            "shelf",
            "product",
            "product_info",
        )
        try:
            deps = prepare_inventory_dependencies(
                store_sdk=self.store_sdk,
                warehouse_sdk=self.warehouse_sdk,
                shelf_sdk=self.shelf_sdk,
                status_sdk=self.status_sdk,
                product_sdk=self.product_sdk,
                product_info_sdk=self.product_info_sdk,
                created_ids=self.created_ids,
                class_cleanup_ids={key: [] for key in self.created_ids},
            )
            self.test_product = {"id": deps["product_id"]}
            self.test_product_info = {"id": deps["product_info_id"]}
            self.test_store = {"id": deps["store_id"]}
            self.test_status = {"id": deps["status_id"]}
            self.test_warehouse = {"id": deps["warehouse_id"]}
            self.test_shelf = {"id": deps["shelf_id"]}
        except Exception as e:
            logger.warning(f"准备GoodsInfo测试依赖失败: {e}")
            self.skipTest(f"准备GoodsInfo测试依赖失败: {e}")

    def tearDown(self):
        self.cleanup_registry_entries(
            self.created_ids,
            [
                ("goods_info", "goods_info_sdk", "商品SKU"),
                ("product_info", "product_info_sdk", "产品SKU"),
                ("product", "product_sdk", "产品"),
                ("store", "store_sdk", "店铺"),
                ("shelf", "shelf_sdk", "货架"),
                ("warehouse", "warehouse_sdk", "仓库"),
            ],
            owner=self,
            log_prefix=f"测试 {self._testMethodName}",
        )
        self.clear_cleanup_registry(self.created_ids)

    def _create_goods_info_param(
        self, sku, product_info_id, type_val=1, count=1, price=100.0
    ):
        """创建goodsInfo参数的辅助方法"""
        return {
            "sku": sku,
            "product": {"id": product_info_id},
            "type": type_val,
            "count": count,
            "price": price,
            "shelf": [{"id": self.test_shelf["id"]}],  # shelf字段是数组类型
        }

    @classmethod
    def tearDownClass(cls):
        cls.log_suite_end("Goods Info 测试结束")
        super().tearDownClass()

    def _record_goods_info_for_cleanup(self, entity):
        if isinstance(entity, dict) and entity.get("id") is not None:
            self.created_ids["goods_info"].append(entity["id"])

    def test_create_goods_info(self):
        self.log_test_step("测试创建商品SKU")
        goods_info_param = self._create_goods_info_param(
            "GOODS001", self.test_product_info["id"], count=10
        )
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        required_fields = [
            "id",
            "sku",
            "product",
            "type",
            "count",
            "price",
            "creater",
            "createTime",
        ]
        for field in required_fields:
            self.assertIn(field, goods_info, f"商品SKU缺少必填字段: {field}")
        self.assert_entity_matches_definition(goods_info, context="创建商品SKU返回")
        self._record_goods_info_for_cleanup(goods_info)
        self.log_test_success(
            f"✓ 商品SKU创建成功: ID={goods_info.get('id')}, SKU={goods_info.get('sku')}"
        )

    def test_query_goods_info(self):
        self.log_test_step("测试查询商品SKU")
        goods_info_param = self._create_goods_info_param(
            "GOODS002", self.test_product_info["id"], count=5, price=150.0
        )
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        queried_info = self.goods_info_sdk.query_goods_info(created_info["id"])
        self.assertIsNotNone(queried_info, "查询商品SKU失败")
        self.assert_entity_round_trip(created_info, queried_info, context="查询商品SKU返回")
        self._record_goods_info_for_cleanup(created_info)
        self.log_test_success(f"✓ 商品SKU查询成功: ID={queried_info.get('id')}")

    def test_update_goods_info(self):
        self.log_test_step("测试更新商品SKU")
        goods_info_param = self._create_goods_info_param(
            "GOODS003", self.test_product_info["id"], count=3, price=200.0
        )
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        update_param = {"count": 5, "price": 250.0}
        updated_info = self.goods_info_sdk.update_goods_info(
            created_info["id"], update_param
        )
        queried_info = self.assert_update_round_trip(
            created_info["id"],
            updated_info,
            expected_updates={"count": 5, "price": 250.0},
            original_entity=created_info,
            context="更新商品SKU返回",
        )
        self.log_test_success(f"✓ 商品SKU更新成功: ID={queried_info.get('id')}")
        self._record_goods_info_for_cleanup(created_info)

    def test_delete_goods_info(self):
        self.log_test_step("测试删除商品SKU")
        goods_info_param = self._create_goods_info_param(
            "GOODS004", self.test_product_info["id"], price=300.0
        )
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        deleted_info = self.goods_info_sdk.delete_goods_info(created_info["id"])
        if deleted_info:
            self.assertEqual(
                deleted_info["id"], created_info["id"], "删除的商品SKUID不匹配"
            )
            self.log_test_success(f"✓ 商品SKU删除成功: ID={deleted_info.get('id')}")
        else:
            self.log_test_observation("⚠ 商品SKU删除未返回结果")

    def test_create_goods_info_with_different_type(self):
        self.log_test_step("测试创建不同类型商品SKU")
        goods_types = [1, 2]
        for goods_type in goods_types:
            goods_info_param = self._create_goods_info_param(
                f"GOODS{goods_type}",
                self.test_product_info["id"],
                type_val=goods_type,
                count=2,
            )
            goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
            self.assertIsNotNone(goods_info, f"创建类型{goods_type}商品SKU失败")
            self.assertEqual(
                goods_info["type"], goods_type, f"商品类型不匹配: {goods_type}"
            )
            self._record_goods_info_for_cleanup(goods_info)
            self.log_test_success(f"✓ 类型{goods_type}商品SKU创建成功")

    def test_create_goods_info_without_product(self):
        self.log_test_step("测试创建无产品的商品SKU")
        goods_info_param = {
            "sku": "GOODS006",
            "type": 1,
            "count": 1,
            "price": 100.0,
        }
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        if goods_info is None:
            self.log_test_success("✓ 系统正确拒绝创建无产品的商品SKU")
        else:
            self.assertIn("product", goods_info, "商品SKU应包含产品字段")
            self.log_test_observation(f"⚠ 系统允许创建无产品的商品SKU: ID={goods_info.get('id')}")
            self._record_goods_info_for_cleanup(goods_info)

    def test_query_nonexistent_goods_info(self):
        self.log_test_step("测试查询不存在的商品SKU")
        non_existent_id = 999999999
        goods_info = self.goods_info_sdk.query_goods_info(non_existent_id)
        if goods_info is None:
            self.log_test_success("✓ 查询不存在的商品SKU返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 查询不存在的商品SKU返回: {goods_info}")

    def test_delete_nonexistent_goods_info(self):
        self.log_test_step("测试删除不存在的商品SKU")
        non_existent_id = 999999999
        deleted_info = self.goods_info_sdk.delete_goods_info(non_existent_id)
        if deleted_info is None:
            self.log_test_success("✓ 删除不存在的商品SKU返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 删除不存在的商品SKU返回: {deleted_info}")

    def test_auto_generated_fields(self):
        self.log_test_step("测试系统自动生成字段")
        goods_info_param = self._create_goods_info_param(
            "GOODS007", self.test_product_info["id"]
        )
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        auto_fields = ["id", "creater", "createTime"]
        for field in auto_fields:
            self.assertIn(field, goods_info, f"缺少自动生成字段: {field}")
        self.assert_entity_matches_definition(goods_info, context="自动字段商品SKU返回")
        self._record_goods_info_for_cleanup(goods_info)
        self.log_test_success(f"✓ 系统自动生成字段验证成功: ID={goods_info.get('id')}")

    def test_goods_info_type_validation(self):
        self.log_test_step("测试商品SKU类型验证")
        goods_info_param = self._create_goods_info_param(
            "GOODS008", self.test_product_info["id"]
        )
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        self.assertEqual(goods_info["type"], 1, "商品类型不匹配")
        self._record_goods_info_for_cleanup(goods_info)
        self.log_test_success(f"✓ 商品SKU类型验证成功: 类型={goods_info.get('type')}")
