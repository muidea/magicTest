"""
Product Info 测试用例

基于 VMI实体定义和使用说明.md:165-175 中的 productInfo 实体定义编写。
使用 ProductInfoSDK 进行测试。

包含的测试用例（共12个）：
1. test_create_product_info
2. test_query_product_info
3. test_update_product_info
4. test_delete_product_info
5. test_create_product_info_with_image
6. test_create_product_info_without_product
7. test_create_duplicate_product_info
8. test_query_nonexistent_product_info
9. test_delete_nonexistent_product_info
10. test_auto_generated_fields
11. test_modify_time_auto_update
12. test_product_info_product_validation
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

from mock import common as mock
import logging
import time
import unittest

from sdk import ProductInfoSDK, ProductSDK, StatusSDK
from test_dependency_helper import resolve_status_id
from test_vmi_base import VMITestCase

logger = logging.getLogger(__name__)


class ProductInfoTestCase(VMITestCase):
    namespace = ""
    entity_definition = "product/productInfo.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status_id = resolve_status_id(cls.status_sdk)
        if not cls.status_id:
            raise Exception("无法获取可用状态ID")
        cls.log_suite_start("Product Info 测试开始")

    @classmethod
    def _init_sdk(cls):
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)
        cls.product_sdk = ProductSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)

    def setUp(self):
        self.created_ids = self.build_cleanup_registry("product_info", "product")
        # 创建测试产品
        product_param = {
            "name": f"测试产品-SKU-{int(time.time() * 1000)}",
            "description": "SKU测试用产品",
            "status": {"id": self.status_id},
        }
        try:
            self.test_product = self.product_sdk.create_product(product_param)
            if not self.test_product:
                self.skipTest("无法创建测试产品")
            self._record_entity_for_cleanup("product", self.test_product)
        except Exception as e:
            logger.warning(f"创建测试产品失败: {e}")
            self.skipTest(f"创建测试产品失败: {e}")

    def tearDown(self):
        self.cleanup_registry_entries(
            self.created_ids,
            [
                ("product_info", "product_info_sdk", "产品SKU"),
                ("product", "product_sdk", "产品"),
            ],
            owner=self,
            log_prefix=f"测试 {self._testMethodName}",
        )
        self.clear_cleanup_registry(self.created_ids)

    @classmethod
    def tearDownClass(cls):
        cls.log_suite_end("Product Info 测试结束")
        super().tearDownClass()

    def _record_entity_for_cleanup(self, entity_type, entity):
        if isinstance(entity, dict) and entity.get("id") is not None:
            self.created_ids[entity_type].append(entity["id"])

    def test_create_product_info(self):
        self.log_test_step("测试创建产品SKU")
        product_info_param = {
            "sku": "SKU001",
            "description": "测试SKU描述",
            "product": {"id": self.test_product["id"]},
        }
        product_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(product_info, "创建产品SKU失败")
        required_fields = [
            "id",
            "sku",
            "description",
            "product",
            "creater",
            "createTime",
        ]
        for field in required_fields:
            self.assertIn(field, product_info, f"产品SKU缺少必填字段: {field}")
        self.assert_entity_matches_definition(product_info, context="创建产品SKU返回")
        self._record_entity_for_cleanup("product_info", product_info)
        self.log_test_success(
            f"✓ 产品SKU创建成功: ID={product_info.get('id')}, SKU={product_info.get('sku')}"
        )

    def test_query_product_info(self):
        self.log_test_step("测试查询产品SKU")
        product_info_param = {
            "sku": "SKU002",
            "description": "查询测试SKU",
            "product": {"id": self.test_product["id"]},
        }
        created_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(created_info, "创建产品SKU失败")
        queried_info = self.product_info_sdk.query_product_info(created_info["id"])
        self.assertIsNotNone(queried_info, "查询产品SKU失败")
        self.assert_entity_round_trip(created_info, queried_info, context="查询产品SKU返回")
        self._record_entity_for_cleanup("product_info", created_info)
        self.log_test_success(f"✓ 产品SKU查询成功: ID={queried_info.get('id')}")

    def test_update_product_info(self):
        self.log_test_step("测试更新产品SKU")
        product_info_param = {
            "sku": "SKU003",
            "description": "更新前描述",
            "product": {"id": self.test_product["id"]},
        }
        created_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(created_info, "创建产品SKU失败")

        # 测试1: 部分更新（只更新description） - 服务器可能要求必填字段
        self.log_test_step("测试部分更新（只更新description）")
        update_param_partial = {"description": "更新后描述"}
        try:
            updated_info = self.product_info_sdk.update_product_info(
                created_info["id"], update_param_partial
            )
            if updated_info:
                self.log_test_success(f"✓ 部分更新成功: ID={updated_info.get('id')}")
            else:
                self.log_test_observation("⚠ 部分更新未返回结果，可能服务器要求必填字段")
        except Exception as e:
            if "错误代码: 6" in str(e):
                self.log_test_success("✓ 服务器正确要求必填字段（错误代码6）")
            else:
                self.log_test_observation(f"⚠ 部分更新失败: {e}")

        # 测试2: 完整更新（包含所有必填字段）
        self.log_test_step("测试完整更新（包含所有必填字段）")
        update_param_full = {
            "sku": "SKU003",  # 必须包含sku字段
            "description": "更新后描述",
            "product": {"id": self.test_product["id"]},  # 必须包含product字段
        }
        updated_info = self.product_info_sdk.update_product_info(
            created_info["id"], update_param_full
        )
        queried_info = self.assert_update_round_trip(
            created_info["id"],
            updated_info,
            expected_updates={
                "sku": "SKU003",
                "description": "更新后描述",
                "product": {"id": self.test_product["id"]},
            },
            original_entity=created_info,
            context="更新产品SKU返回",
        )
        self.log_test_success(f"✓ 完整更新成功: ID={queried_info.get('id')}")
        self._record_entity_for_cleanup("product_info", created_info)

    def test_delete_product_info(self):
        self.log_test_step("测试删除产品SKU")
        product_info_param = {
            "sku": "SKU004",
            "description": "删除测试SKU",
            "product": {"id": self.test_product["id"]},
        }
        created_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(created_info, "创建产品SKU失败")
        deleted_info = self.product_info_sdk.delete_product_info(created_info["id"])
        if deleted_info:
            self.assertEqual(
                deleted_info["id"], created_info["id"], "删除的产品SKUID不匹配"
            )
            self.log_test_success(f"✓ 产品SKU删除成功: ID={deleted_info.get('id')}")
        else:
            self.log_test_observation("⚠ 产品SKU删除未返回结果")

    def test_create_product_info_with_image(self):
        self.log_test_step("测试创建带图片的产品SKU")
        product_info_param = {
            "sku": "SKU005",
            "description": "带图片SKU",
            "product": {"id": self.test_product["id"]},
            "image": ["image1.jpg", "image2.jpg"],
        }
        product_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(product_info, "创建带图片的产品SKU失败")
        self.assertIn("image", product_info, "产品SKU应包含图片字段")
        self.assertIsInstance(product_info["image"], list, "图片字段应为列表")
        self._record_entity_for_cleanup("product_info", product_info)
        self.log_test_success(
            f"✓ 带图片的产品SKU创建成功: 图片数量={len(product_info.get('image', []))}"
        )

    def test_create_product_info_without_product(self):
        self.log_test_step("测试创建无产品的产品SKU")
        product_info_param = {"sku": "SKU006", "description": "无产品SKU"}
        product_info = self.product_info_sdk.create_product_info(product_info_param)
        if product_info is None:
            self.log_test_success("✓ 系统正确拒绝创建无产品的产品SKU")
        else:
            self.assertIn("product", product_info, "产品SKU应包含产品字段")
            self.log_test_observation(f"⚠ 系统允许创建无产品的产品SKU: ID={product_info.get('id')}")
            self._record_entity_for_cleanup("product_info", product_info)

    def test_create_duplicate_product_info(self):
        self.log_test_step("测试创建重复SKU的产品SKU")
        sku = "DUPLICATE001"
        product_info_param1 = {
            "sku": sku,
            "description": "第一个SKU",
            "product": {"id": self.test_product["id"]},
        }
        info1 = self.product_info_sdk.create_product_info(product_info_param1)
        self.assertIsNotNone(info1, "创建第一个产品SKU失败")

        product_info_param2 = {
            "sku": sku,
            "description": "第二个SKU",
            "product": {"id": self.test_product["id"]},
        }
        info2 = self.product_info_sdk.create_product_info(product_info_param2)

        if info2 is None:
            self.log_test_success("✓ 系统正确拒绝创建重复SKU的产品SKU")
        else:
            self.log_test_observation(f"⚠ 系统允许创建重复SKU的产品SKU: ID={info2.get('id')}")
            self._record_entity_for_cleanup("product_info", info2)
        self._record_entity_for_cleanup("product_info", info1)

    def test_query_nonexistent_product_info(self):
        self.log_test_step("测试查询不存在的产品SKU")
        non_existent_id = 999999999
        product_info = self.product_info_sdk.query_product_info(non_existent_id)
        if product_info is None:
            self.log_test_success("✓ 查询不存在的产品SKU返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 查询不存在的产品SKU返回: {product_info}")

    def test_delete_nonexistent_product_info(self):
        self.log_test_step("测试删除不存在的产品SKU")
        non_existent_id = 999999999
        deleted_info = self.product_info_sdk.delete_product_info(non_existent_id)
        if deleted_info is None:
            self.log_test_success("✓ 删除不存在的产品SKU返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 删除不存在的产品SKU返回: {deleted_info}")

    def test_auto_generated_fields(self):
        self.log_test_step("测试系统自动生成字段")
        product_info_param = {
            "sku": "SKU007",
            "description": "自动字段SKU",
            "product": {"id": self.test_product["id"]},
        }
        product_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(product_info, "创建产品SKU失败")
        auto_fields = ["id", "creater", "createTime"]
        for field in auto_fields:
            self.assertIn(field, product_info, f"缺少自动生成字段: {field}")
        self.assert_entity_matches_definition(product_info, context="自动字段产品SKU返回")
        self._record_entity_for_cleanup("product_info", product_info)
        self.log_test_success(f"✓ 系统自动生成字段验证成功: ID={product_info.get('id')}")

    def test_modify_time_auto_update(self):
        self.log_test_step("测试修改时间自动更新")
        product_info_param = {
            "sku": "SKU008",
            "description": "时间测试SKU",
            "product": {"id": self.test_product["id"]},
        }
        created_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(created_info, "创建产品SKU失败")

        if "modifyTime" in created_info:
            original_modify_time = created_info["modifyTime"]

            # 更新时必须包含所有必填字段
            update_param = {
                "sku": "SKU008_UPDATED",
                "description": "时间更新描述",
                "product": {"id": self.test_product["id"]},
            }

            updated_info = self.product_info_sdk.update_product_info(
                created_info["id"], update_param
            )
            queried_info = self.assert_update_round_trip(
                created_info["id"],
                updated_info,
                expected_updates={
                    "sku": "SKU008_UPDATED",
                    "description": "时间更新描述",
                    "product": {"id": self.test_product["id"]},
                },
                original_entity=created_info,
                context="修改时间产品SKU更新返回",
            )

            updated_modify_time = queried_info.get("modifyTime")
            self.assertIsNotNone(updated_modify_time, "更新操作未返回modifyTime字段")
            self.assertNotEqual(
                updated_modify_time,
                original_modify_time,
                "modifyTime字段在更新后未自动刷新",
            )
            self.log_test_success("✓ 修改时间自动更新验证成功")
            self.log_test_success(
                f"✓ 时间戳变化: {original_modify_time} -> {updated_modify_time}"
            )
        else:
            self.fail("创建的数据不包含modifyTime字段")

        self._record_entity_for_cleanup("product_info", created_info)

    def test_product_info_product_validation(self):
        self.log_test_step("测试产品SKU产品关联验证")
        product_info_param = {
            "sku": "SKU009",
            "description": "产品关联测试",
            "product": {"id": self.test_product["id"]},
        }
        product_info = self.product_info_sdk.create_product_info(product_info_param)
        self.assertIsNotNone(product_info, "创建产品SKU失败")
        self.assertEqual(
            product_info["product"]["id"], self.test_product["id"], "产品ID不匹配"
        )
        self._record_entity_for_cleanup("product_info", product_info)
        self.log_test_success(
            f"✓ 产品SKU产品关联验证成功: 产品ID={product_info.get('product', {}).get('id')}"
        )
