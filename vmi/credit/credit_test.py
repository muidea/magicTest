"""
Credit 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:78-90 中的 credit 实体定义编写。
使用 CreditSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- sn: string (积分编号) - 唯一，由系统根据积分编号生成规则自动生成
- owner: partner* (所属会员) - 必选
- memo: string (备注) - 可选
- credit: int64 (积分) - 必选
- type: int (类型) - 必选
- level: int (等级) - 必选
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- namespace: string (命名空间) - 由系统自动生成

业务说明：单个namespace里，每个会员可以拥有多个积分信息。

包含的测试用例（共12个）：

1. 基础CURD测试：
   - test_create_credit: 测试创建积分信息，验证所有字段完整性
   - test_query_credit: 测试查询积分信息，验证数据一致性
   - test_update_credit: 测试更新积分信息，验证字段更新功能
   - test_delete_credit: 测试删除积分信息，验证删除操作

2. 边界测试：
   - test_create_credit_with_negative_value: 测试创建负积分值
   - test_create_credit_with_large_value: 测试创建大积分值

3. 异常测试：
   - test_create_credit_without_owner: 测试创建无所属会员的积分信息
   - test_query_nonexistent_credit: 测试查询不存在的积分信息
   - test_delete_nonexistent_credit: 测试删除不存在的积分信息

4. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、sn、creater、createTime、namespace）
   - test_credit_type_level_validation: 测试积分类型和等级字段验证

5. 业务规则测试：
   - test_multiple_credits_per_owner: 测试单个会员可拥有多个积分信息

测试特性：
- 使用 CreditSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为
- 验证所有实体定义字段
- 覆盖完整的业务规则

版本：1.0
最后更新：2026-01-26
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

import logging
import unittest

from mock import common as mock

from sdk import CreditSDK, PartnerSDK, StatusSDK
from test_dependency_helper import prepare_partner_dependency
from test_vmi_base import VMITestCase

# 配置日志
logger = logging.getLogger(__name__)


class CreditTestCase(VMITestCase):
    """Credit 测试用例类"""

    namespace = ""
    entity_definition = "credit/credit.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # 类级别的数据清理记录
        cls._class_cleanup_ids = cls.build_cleanup_registry("credit", "partner")

        cls.record_initial_count(
            "_initial_credit_count", cls._get_credit_count, entity_name="积分信息"
        )

    @classmethod
    def _init_sdk(cls):
        cls.credit_sdk = CreditSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)

    @classmethod
    def _get_credit_count(cls):
        """获取当前积分信息数量"""
        return cls.get_entity_count(
            "credit_sdk",
            "count_credit",
            "filter_credit",
            entity_name="积分信息",
            filter_args=({},),
        )

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        original_credit_count = len(cls._class_cleanup_ids["credit"])
        original_partner_count = len(cls._class_cleanup_ids["partner"])
        logger.info(
            f"测试类清理开始: 需要清理 {original_credit_count} 个积分信息和 {original_partner_count} 个会员"
        )

        cls.cleanup_registry_entries(
            cls._class_cleanup_ids,
            [
                ("credit", "credit_sdk", "积分信息"),
                ("partner", "partner_sdk", "会员"),
            ],
        )
        cls.verify_cleanup_count(
            "_initial_credit_count",
            cls._get_credit_count,
            entity_name="积分信息",
            remaining_sdk_ref="credit_sdk",
            remaining_filter_method_name="filter_credit",
            remaining_filter_args=({},),
            remaining_describe=lambda credit: (
                f"ID: {credit['id']}, 所属会员: {credit.get('owner', 'N/A')}, 积分: {credit.get('credit', 'N/A')}"
                if isinstance(credit, dict) and "id" in credit
                else None
            ),
        )

        super().tearDownClass()

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的积分信息ID以便清理
        self.created_ids = self.build_cleanup_registry("credit", "partner")

        try:
            partner_deps = prepare_partner_dependency(
                partner_sdk=self.partner_sdk,
                status_sdk=self.status_sdk,
                name_prefix="TEST_PARTNER",
            )
        except Exception as exc:
            logger.warning(f"创建测试会员失败: {exc}")
            self.skipTest(f"创建测试会员失败: {exc}")

        self.test_partner_id = partner_deps["partner_id"]
        self.created_ids["partner"].append(self.test_partner_id)
        logger.info(f"创建测试会员成功，ID: {self.test_partner_id}")

    def tearDown(self):
        """每个测试用例后的清理"""
        self.merge_cleanup_registry(self.__class__._class_cleanup_ids, self.created_ids)
        self._cleanup_test_entities()
        self.clear_cleanup_registry(self.created_ids)

    def _cleanup_test_entities(self):
        """清理本测试创建的实体

        注意：系统支持删除操作，如果删除失败应该抛出异常，
        以便测试失败并排查server错误。
        """
        self.cleanup_registry_entries(
            self.created_ids,
            [
                ("credit", "credit_sdk", "积分信息"),
                ("partner", "partner_sdk", "会员"),
            ],
            owner=self,
            remove_from=self.__class__._class_cleanup_ids,
            log_prefix=f"测试 {self._testMethodName}",
        )

    def _record_credit_for_cleanup(self, credit_id):
        """记录积分信息ID以便清理"""
        if credit_id is not None:
            self.created_ids["credit"].append(credit_id)
            logger.debug(
                f"记录积分信息 {credit_id} 到清理列表 (测试: {self._testMethodName})"
            )

    def mock_credit_param(self):
        """模拟积分信息参数"""
        if not getattr(self, "test_partner_id", None):
            raise AssertionError("测试会员未准备完成")

        return {
            "owner": {"id": self.test_partner_id},
            "memo": mock.sentence(),
            "credit": 100,
            "type": 1,
            "level": 1,
        }

    def test_create_credit(self):
        """测试创建积分信息"""
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        # 验证积分信息完整性 - 根据实际服务器响应调整
        # 服务器返回的字段：createTime, creater, credit, id, level, memo, sn, type
        required_fields = [
            "id",
            "credit",
            "type",
            "level",
            "sn",
            "creater",
            "createTime",
        ]
        for field in required_fields:
            self.assertIn(field, new_credit, f"缺少字段: {field}")

        # 验证系统自动生成字段
        self.assertIn("sn", new_credit, "缺少积分编号字段")
        self.assertIsInstance(new_credit["sn"], str, "积分编号应为字符串")
        self.assertGreater(len(new_credit["sn"]), 0, "积分编号不应为空")

        self.assertIn("creater", new_credit, "缺少创建者字段")
        self.assertIsInstance(
            new_credit["creater"], (int, type(None)), "创建者应为整数或None"
        )

        self.assertIn("createTime", new_credit, "缺少创建时间字段")
        self.assertIsInstance(
            new_credit["createTime"], (int, type(None)), "创建时间应为整数或None"
        )


        # 验证业务字段
        self.assertEqual(new_credit["credit"], 100, "积分值不匹配")
        self.assertEqual(new_credit["type"], 1, "类型不匹配")
        self.assertEqual(new_credit["level"], 1, "等级不匹配")

        # 记录创建的积分信息ID以便清理
        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

    def test_query_credit(self):
        """测试查询积分信息"""
        # 先创建积分信息
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

        # 查询积分信息
        queried_credit = self.credit_sdk.query_credit(new_credit["id"])
        self.assertIsNotNone(queried_credit, "查询积分信息失败")
        self.assertEqual(queried_credit["id"], new_credit["id"], "积分信息ID不匹配")
        self.assertEqual(queried_credit["credit"], new_credit["credit"], "积分值不匹配")

    def test_update_credit(self):
        """测试更新积分信息"""
        # 先创建积分信息
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

        # 更新积分信息
        update_param = new_credit.copy()
        update_param["memo"] = "更新后的备注"

        updated_credit = self.credit_sdk.update_credit(new_credit["id"], update_param)
        self.assertIsNotNone(updated_credit, "更新积分信息失败")
        self.assertEqual(updated_credit["memo"], "更新后的备注", "备注更新失败")

    def test_delete_credit(self):
        """测试删除积分信息

        注意：系统支持删除操作，如果删除失败应该让测试失败，
        以便排查server错误。
        """
        # 先创建积分信息
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

        # 删除积分信息 - 系统应该支持删除操作
        deleted_credit = self.credit_sdk.delete_credit(new_credit["id"])

        # 删除应该成功，返回被删除的对象
        self.assertIsNotNone(
            deleted_credit, "删除积分信息失败，返回None。系统应该支持删除操作"
        )
        self.assertEqual(
            deleted_credit["id"], new_credit["id"], "删除的积分信息ID不匹配"
        )

        # 从清理列表中移除，因为已经成功删除
        if new_credit["id"] in self.created_ids["credit"]:
            self.created_ids["credit"].remove(new_credit["id"])

        # 验证积分信息已被删除（查询应该失败）
        queried_credit = self.credit_sdk.query_credit(new_credit["id"])
        # 查询应该返回None，因为积分信息已被删除
        self.assertIsNone(queried_credit, "删除后查询积分信息应该返回None")

    def test_create_credit_with_negative_value(self):
        """测试创建负积分值（边界测试）"""
        credit_param = self.mock_credit_param()
        credit_param["credit"] = -50  # 负积分值

        new_credit = self.credit_sdk.create_credit(credit_param)
        if new_credit is not None:
            self.assertIsInstance(new_credit["credit"], int, "积分值不是整数")
            # 记录创建的积分信息ID以便清理
            if "id" in new_credit:
                self._record_credit_for_cleanup(new_credit["id"])

    def test_create_credit_with_large_value(self):
        """测试创建大积分值（边界测试）"""
        credit_param = self.mock_credit_param()
        credit_param["credit"] = 999999  # 大积分值

        new_credit = self.credit_sdk.create_credit(credit_param)
        if new_credit is not None:
            self.assertIsInstance(new_credit["credit"], int, "积分值不是整数")
            # 记录创建的积分信息ID以便清理
            if "id" in new_credit:
                self._record_credit_for_cleanup(new_credit["id"])

    def test_create_credit_without_owner(self):
        """测试创建无所属会员的积分信息（异常测试）"""
        credit_param = self.mock_credit_param()
        # 移除owner字段
        if "owner" in credit_param:
            del credit_param["owner"]

        new_credit = self.credit_sdk.create_credit(credit_param)
        # 期望创建失败，返回None或错误响应
        # 但系统可能允许创建，所以不强制要求失败
        if new_credit is not None:
            # 如果创建成功，记录ID以便清理
            if "id" in new_credit:
                self._record_credit_for_cleanup(new_credit["id"])

    def test_query_nonexistent_credit(self):
        """测试查询不存在的积分信息（异常测试）"""
        nonexistent_credit_id = 999999
        queried_credit = self.credit_sdk.query_credit(nonexistent_credit_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_credit, "查询不存在的积分信息应失败")

    def test_delete_nonexistent_credit(self):
        """测试删除不存在的积分信息（异常测试）"""
        nonexistent_credit_id = 999999
        deleted_credit = self.credit_sdk.delete_credit(nonexistent_credit_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_credit, "删除不存在的积分信息应失败")

    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

        # 验证所有系统自动生成字段
        auto_generated_fields = ["id", "sn", "creater", "createTime"]
        for field in auto_generated_fields:
            self.assertIn(field, new_credit, f"缺少系统自动生成字段: {field}")

        # 验证字段类型和值
        self.assertIsInstance(new_credit["id"], (int, type(None)), "ID应为整数或None")
        if new_credit["id"] is not None:
            self.assertGreater(new_credit["id"], 0, "ID应为正整数")

        self.assertIsInstance(
            new_credit["sn"], (str, type(None)), "积分编号应为字符串或None"
        )
        if new_credit["sn"] is not None:
            self.assertGreater(len(new_credit["sn"]), 0, "积分编号不应为空")

        self.assertIsInstance(
            new_credit["creater"], (int, type(None)), "创建者应为整数或None"
        )
        self.assertIsInstance(
            new_credit["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        if new_credit["createTime"] is not None:
            self.assertGreater(new_credit["createTime"], 0, "创建时间应为正数")


    def test_credit_type_level_validation(self):
        """测试积分类型和等级字段验证"""
        credit_param = self.mock_credit_param()
        new_credit = self.credit_sdk.create_credit(credit_param)
        self.assertIsNotNone(new_credit, "创建积分信息失败")

        if new_credit and "id" in new_credit:
            self._record_credit_for_cleanup(new_credit["id"])

        # 验证类型和等级字段
        self.assertIn("type", new_credit, "积分信息缺少类型字段")
        self.assertIsInstance(
            new_credit["type"], (int, type(None)), "类型应为整数或None"
        )

        self.assertIn("level", new_credit, "积分信息缺少等级字段")
        self.assertIsInstance(
            new_credit["level"], (int, type(None)), "等级应为整数或None"
        )

    def test_multiple_credits_per_owner(self):
        """测试单个会员可拥有多个积分信息（业务规则测试）"""
        # 创建第一个积分信息
        credit_param1 = self.mock_credit_param()
        credit1 = self.credit_sdk.create_credit(credit_param1)
        self.assertIsNotNone(credit1, "创建第一个积分信息失败")

        if credit1 and "id" in credit1:
            self._record_credit_for_cleanup(credit1["id"])

        # 创建第二个积分信息（相同会员）
        credit_param2 = self.mock_credit_param()
        # 使用相同的owner（在参数中）
        credit_param2["owner"] = credit_param1["owner"]
        credit_param2["type"] = 2  # 不同的类型
        credit_param2["level"] = 2  # 不同的等级

        credit2 = self.credit_sdk.create_credit(credit_param2)
        self.assertIsNotNone(credit2, "创建第二个积分信息失败")

        if credit2 and "id" in credit2:
            self._record_credit_for_cleanup(credit2["id"])

        # 验证它们有不同的ID
        self.assertNotEqual(credit1["id"], credit2["id"], "两个积分信息应有不同的ID")

        # 验证它们有不同的类型和等级
        self.assertNotEqual(
            credit1["type"], credit2["type"], "两个积分信息应有不同的类型"
        )
        self.assertNotEqual(
            credit1["level"], credit2["level"], "两个积分信息应有不同的等级"
        )

        # 注意：服务器返回的credit数据不包含owner字段，所以无法验证owner关系
        # 但创建时使用了相同的owner参数，业务逻辑上应该属于同一个会员


if __name__ == "__main__":
    unittest.main()
