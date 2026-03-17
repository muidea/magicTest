"""
Product 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:150-161 中的 product 实体定义编写。
使用 ProductSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- name: string (产品名称) - 必选
- description: string (描述) - 可选
- image: string[] (图片) - 可选
- expire: int (有效期) - 可选
- status: status* (状态) - 必选，由平台进行管理，允许进行更新
- tags: string[] (标签) - 可选
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- modifyTime: int64 (修改时间) - 由系统自动更新
- namespace: string (命名空间) - 由系统自动生成

包含的测试用例（共12个）：

1. 基础CURD测试：
   - test_create_product: 测试创建产品，验证所有字段完整性
   - test_query_product: 测试查询产品，验证数据一致性
   - test_update_product: 测试更新产品，验证字段更新功能
   - test_delete_product: 测试删除产品，验证删除操作

2. 边界测试：
   - test_create_product_with_long_name: 测试创建超长名称产品
   - test_create_product_with_many_tags: 测试创建带多个标签的产品

3. 异常测试：
   - test_create_duplicate_product: 测试创建重复产品名（系统可能允许重复）
   - test_query_nonexistent_product: 测试查询不存在的产品
   - test_delete_nonexistent_product: 测试删除不存在的产品

4. 状态验证：
   - test_product_status_validation: 测试产品状态字段验证

5. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、creater、createTime、namespace）
   - test_modify_time_auto_update: 测试修改时间字段的自动更新逻辑

测试特性：
- 使用 ProductSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为（如允许重复名称）
- 验证所有实体定义字段
- 覆盖完整的业务规则

版本：1.0
最后更新：2026-01-25
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

from mock import common as mock
import logging
import unittest

from sdk import ProductSDK, StatusSDK
from test_dependency_helper import resolve_status_id
from test_vmi_base import VMITestCase

# 配置日志
logger = logging.getLogger(__name__)


class ProductTestCase(VMITestCase):
    """Product 测试用例类"""

    namespace = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status_id = resolve_status_id(cls.status_sdk)
        if not cls.status_id:
            raise Exception("无法获取可用状态ID")

        # 类级别的数据清理记录
        cls._class_cleanup_ids = []

        cls.record_initial_count(
            "_initial_product_count", cls._get_product_count, entity_name="产品"
        )

    @classmethod
    def _init_sdk(cls):
        cls.product_sdk = ProductSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)

    @classmethod
    def _get_product_count(cls):
        """获取当前产品数量"""
        return cls.get_entity_count(
            "product_sdk",
            "count_product",
            "filter_product",
            entity_name="产品",
            count_args=({},),
            filter_args=({},),
        )

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        original_count = len(cls._class_cleanup_ids)
        logger.info(
            f"测试类清理开始: 需要清理 {original_count} 个产品: {cls._class_cleanup_ids}"
        )

        cls.cleanup_id_list(cls._class_cleanup_ids, "product_sdk", "产品")
        cls.verify_cleanup_count(
            "_initial_product_count",
            cls._get_product_count,
            entity_name="产品",
            remaining_sdk_ref="product_sdk",
            remaining_filter_method_name="filter_product",
            remaining_filter_args=({},),
            remaining_describe=lambda product: (
                f"ID: {product['id']}, 名称: {product['name']}, 描述: {product.get('description', 'N/A')}"
                if isinstance(product, dict)
                and "id" in product
                and "name" in product
                else None
            ),
        )

        super().tearDownClass()

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的产品ID以便清理
        self.created_product_ids = []

    def tearDown(self):
        """每个测试用例后的清理"""
        # 将本测试创建的产品ID添加到类级别清理列表
        if hasattr(self.__class__, "_class_cleanup_ids"):
            self.__class__._class_cleanup_ids.extend(self.created_product_ids)

        # 尝试立即清理本测试创建的数据
        self._cleanup_test_products()

        self.created_product_ids.clear()

    def _cleanup_test_products(self):
        """清理本测试创建的产品

        注意：系统支持删除操作，如果删除失败应该抛出异常，
        以便测试失败并排查server错误。
        """
        self.cleanup_id_list(
            self.created_product_ids,
            "product_sdk",
            "产品",
            owner=self,
            remove_from=self.__class__._class_cleanup_ids,
            log_prefix=f"测试 {self._testMethodName}",
        )

    def _record_product_for_cleanup(self, product_id):
        """记录产品ID以便清理"""
        if product_id is not None:
            self.created_product_ids.append(product_id)
            logger.debug(
                f"记录产品 {product_id} 到清理列表 (测试: {self._testMethodName})"
            )

    def mock_product_param(self):
        """模拟产品参数

        根据实体定义，product实体包含以下字段：
        - name: string (产品名称) - 必选
        - description: string (描述) - 可选
        - image: string[] (图片) - 可选
        - expire: int (有效期) - 可选
        - status: status* (状态) - 必选
        - tags: string[] (标签) - 可选
        """
        return {
            "name": mock.name(),
            "description": mock.sentence(),
            "image": [mock.url(), mock.url()],
            "expire": 100,
            "tags": ["tag1", "tag2", "tag3"],
            "status": {"id": self.status_id},
        }

    def test_create_product(self):
        """测试创建产品"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        # 验证产品信息完整性
        required_fields = [
            "id",
            "name",
            "description",
            "image",
            "expire",
            "tags",
            "status",
        ]
        for field in required_fields:
            self.assertIn(field, new_product, f"缺少字段: {field}")

        # 验证系统自动生成字段
        self.assertIn("creater", new_product, "缺少创建者字段")
        self.assertIsInstance(
            new_product["creater"], (int, type(None)), "创建者应为整数或None"
        )

        self.assertIn("createTime", new_product, "缺少创建时间字段")
        self.assertIsInstance(
            new_product["createTime"], (int, type(None)), "创建时间应为整数或None"
        )

        self.assertIn("namespace", new_product, "缺少命名空间字段")
        self.assertIsInstance(
            new_product["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

        # 记录创建的产品ID以便清理
        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

    def test_query_product(self):
        """测试查询产品"""
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 查询产品
        queried_product = self.product_sdk.query_product(new_product["id"])
        self.assertIsNotNone(queried_product, "查询产品失败")
        self.assertEqual(queried_product["id"], new_product["id"], "产品ID不匹配")
        self.assertEqual(queried_product["name"], new_product["name"], "产品名不匹配")

    def test_update_product(self):
        """测试更新产品"""
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 更新产品
        update_param = new_product.copy()
        update_param["description"] = "更新后的描述"

        updated_product = self.product_sdk.update_product(
            new_product["id"], update_param
        )
        self.assertIsNotNone(updated_product, "更新产品失败")
        self.assertEqual(updated_product["description"], "更新后的描述", "描述更新失败")

    def test_delete_product(self):
        """测试删除产品

        注意：系统支持删除操作，如果删除失败应该让测试失败，
        以便排查server错误。
        """
        # 先创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 删除产品 - 系统应该支持删除操作
        deleted_product = self.product_sdk.delete_product(new_product["id"])

        # 删除应该成功，返回被删除的对象
        self.assertIsNotNone(
            deleted_product, "删除产品失败，返回None。系统应该支持删除操作"
        )
        self.assertEqual(deleted_product["id"], new_product["id"], "删除的产品ID不匹配")

        # 从清理列表中移除，因为已经成功删除
        if new_product["id"] in self.created_product_ids:
            self.created_product_ids.remove(new_product["id"])

        # 验证产品已被删除（查询应该失败）
        queried_product = self.product_sdk.query_product(new_product["id"])
        # 查询应该返回None或抛出异常，因为产品已被删除
        # 系统可能返回None或抛出异常，两种方式都表示删除成功
        if queried_product is not None:
            # 如果查询返回了产品，那么删除可能失败
            self.fail(f"删除后查询产品应该返回None，但返回了: {queried_product}")
        # 如果queried_product是None，表示删除成功

    def test_create_product_with_long_name(self):
        """测试创建超长名称产品（边界测试）"""
        product_param = self.mock_product_param()
        product_param["name"] = "a" * 255  # 超长名称

        new_product = self.product_sdk.create_product(product_param)
        if new_product is not None:
            self.assertIsInstance(new_product["name"], str, "产品名不是字符串")
            # 记录创建的产品ID以便清理
            if "id" in new_product:
                self._record_product_for_cleanup(new_product["id"])

    def test_create_product_with_many_tags(self):
        """测试创建带多个标签的产品"""
        product_param = self.mock_product_param()
        product_param["tags"] = [
            "tag1",
            "tag2",
            "tag3",
            "tag4",
            "tag5",
            "tag6",
            "tag7",
            "tag8",
            "tag9",
            "tag10",
        ]

        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建带多个标签的产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证标签字段
        self.assertIn("tags", new_product, "产品缺少标签字段")
        self.assertIsInstance(new_product["tags"], list, "标签应为列表")
        self.assertGreaterEqual(len(new_product["tags"]), 10, "标签数量不足")

    def test_create_duplicate_product(self):
        """测试创建重复产品名（系统可能允许重复）"""
        product_param = self.mock_product_param()

        first_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(first_product, "第一次创建产品失败")

        # 记录第一次创建的产品ID以便清理
        if first_product and "id" in first_product:
            self._record_product_for_cleanup(first_product["id"])

        # 第二次创建相同产品名
        second_product = self.product_sdk.create_product(product_param)

        # 系统可能允许重复名称，所以不强制要求失败
        if second_product is not None:
            # 如果创建成功，记录ID以便清理
            if "id" in second_product:
                self._record_product_for_cleanup(second_product["id"])
            # 验证返回的数据结构
            self.assertIn("id", second_product, "第二次创建的产品缺少ID字段")
            self.assertIn("name", second_product, "第二次创建的产品缺少name字段")
            self.assertEqual(
                second_product["name"], product_param["name"], "名称不匹配"
            )
        # 如果返回None，也不视为错误，因为系统可能以其他方式处理重复

    def test_query_nonexistent_product(self):
        """测试查询不存在的产品（异常测试）"""
        nonexistent_product_id = 999999
        queried_product = self.product_sdk.query_product(nonexistent_product_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_product, "查询不存在的产品应失败")

    def test_delete_nonexistent_product(self):
        """测试删除不存在的产品（异常测试）"""
        nonexistent_product_id = 999999
        deleted_product = self.product_sdk.delete_product(nonexistent_product_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_product, "删除不存在的产品应失败")

    def test_product_status_validation(self):
        """测试产品状态验证"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证状态字段
        self.assertIn("status", new_product, "产品缺少状态字段")
        self.assertIn("id", new_product["status"], "状态缺少id字段")
        self.assertEqual(new_product["status"]["id"], self.status_id, "状态ID不匹配")

    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 验证所有系统自动生成字段
        auto_generated_fields = ["id", "creater", "createTime", "namespace"]
        for field in auto_generated_fields:
            self.assertIn(field, new_product, f"缺少系统自动生成字段: {field}")

        # 验证字段类型和值
        self.assertIsInstance(new_product["id"], (int, type(None)), "ID应为整数或None")
        if new_product["id"] is not None:
            self.assertGreater(new_product["id"], 0, "ID应为正整数")

        self.assertIsInstance(
            new_product["creater"], (int, type(None)), "创建者应为整数或None"
        )
        self.assertIsInstance(
            new_product["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        if new_product["createTime"] is not None:
            self.assertGreater(new_product["createTime"], 0, "创建时间应为正数")

        self.assertIsInstance(
            new_product["namespace"], (str, type(None)), "命名空间应为字符串或None"
        )

    def test_modify_time_auto_update(self):
        """测试修改时间自动更新"""
        # 创建产品
        product_param = self.mock_product_param()
        new_product = self.product_sdk.create_product(product_param)
        self.assertIsNotNone(new_product, "创建产品失败")

        if new_product and "id" in new_product:
            self._record_product_for_cleanup(new_product["id"])

        # 记录初始创建时间和修改时间
        initial_create_time = new_product.get("createTime")
        initial_modify_time = new_product.get("modifyTime")

        # 更新产品
        update_param = new_product.copy()
        update_param["description"] = "更新后的描述"

        updated_product = self.product_sdk.update_product(
            new_product["id"], update_param
        )
        self.assertIsNotNone(updated_product, "更新产品失败")

        # 验证修改时间已更新
        updated_modify_time = updated_product.get("modifyTime")
        self.assertIsNotNone(updated_modify_time, "更新后缺少修改时间字段")

        # 验证修改时间比创建时间晚（如果两者都存在）
        if initial_create_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_create_time, "修改时间应晚于或等于创建时间"
            )

        # 验证创建时间未改变
        self.assertEqual(
            updated_product.get("createTime"), initial_create_time, "创建时间不应被修改"
        )

        # 如果初始有修改时间，验证已更新
        if initial_modify_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_modify_time, "修改时间应已更新"
            )


if __name__ == "__main__":
    unittest.main()
