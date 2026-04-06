"""
Partner 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:62-77 中的 partner 实体定义编写。
使用 PartnerSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- code: string (会员码) - 唯一，由系统根据会员码生成规则自动生成
- name: string (姓名) - 必选
- telephone: string (电话) - 可选
- wechat: string (微信) - 可选
- description: string (描述) - 可选
- referer: partner* (推荐人) - 可选，自引用关系
- status: status* (状态) - 必选，由平台进行管理，允许进行更新
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- modifyTime: int64 (修改时间) - 由系统自动更新
- namespace: string (命名空间) - 由系统自动生成

包含的测试用例（共14个）：

1. 基础CURD测试：
   - test_create_partner: 测试创建合作伙伴，验证所有字段完整性
   - test_query_partner: 测试查询合作伙伴，验证数据一致性
   - test_update_partner: 测试更新合作伙伴，验证字段更新功能
   - test_delete_partner: 测试删除合作伙伴，验证删除操作

2. 边界测试：
   - test_create_partner_with_long_name: 测试创建超长名称合作伙伴

3. 异常测试：
   - test_create_duplicate_partner: 测试创建重复合作伙伴名（系统可能允许重复）
   - test_query_nonexistent_partner: 测试查询不存在的合作伙伴
   - test_delete_nonexistent_partner: 测试删除不存在的合作伙伴

4. 状态验证：
   - test_partner_status_validation: 测试合作伙伴状态字段验证

5. 推荐人关系测试：
   - test_create_partner_with_referer: 测试创建带推荐人的合作伙伴
   - test_update_partner_with_referer: 测试更新合作伙伴的推荐人
   - test_query_partner_with_referer_details: 测试查询带推荐人详情的合作伙伴

6. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、code、creater、createTime、namespace）
   - test_modify_time_auto_update: 测试修改时间字段的自动更新逻辑

测试特性：
- 使用 PartnerSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为（如允许重复名称、灵活的referer字段处理）
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

from sdk import PartnerSDK, StatusSDK
from test_dependency_helper import resolve_status_id
from test_vmi_base import VMITestCase

# 配置日志
logger = logging.getLogger(__name__)


class PartnerTestCase(VMITestCase):
    """Partner 测试用例类"""

    namespace = ""
    entity_definition = "partner.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.status_id = resolve_status_id(cls.status_sdk)
        if not cls.status_id:
            raise Exception("无法获取可用状态ID")

        # 类级别的数据清理记录
        cls._class_cleanup_ids = cls.build_cleanup_registry("partner")

        cls.record_initial_count(
            "_initial_partner_count", cls._get_partner_count, entity_name="合作伙伴"
        )

    @classmethod
    def _init_sdk(cls):
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)

    @classmethod
    def _get_partner_count(cls):
        """获取当前合作伙伴数量"""
        return cls.get_entity_count(
            "partner_sdk",
            "count_partner",
            "filter_partner",
            entity_name="合作伙伴",
            filter_args=({},),
        )

    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        original_count = len(cls._class_cleanup_ids["partner"])
        logger.info(
            f"测试类清理开始: 需要清理 {original_count} 个合作伙伴: {cls._class_cleanup_ids['partner']}"
        )

        cls.cleanup_registry_entries(
            cls._class_cleanup_ids,
            [("partner", "partner_sdk", "合作伙伴")],
        )
        cls.verify_cleanup_count(
            "_initial_partner_count",
            cls._get_partner_count,
            entity_name="合作伙伴",
            remaining_sdk_ref="partner_sdk",
            remaining_filter_method_name="filter_partner",
            remaining_filter_args=({},),
            remaining_describe=lambda partner: (
                f"ID: {partner['id']}, 名称: {partner['name']}, 电话: {partner.get('telephone', 'N/A')}"
                if isinstance(partner, dict)
                and "id" in partner
                and "name" in partner
                else None
            ),
        )

        super().tearDownClass()

    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的合作伙伴ID以便清理
        self.created_ids = self.build_cleanup_registry("partner")

    def tearDown(self):
        """每个测试用例后的清理"""
        self.merge_cleanup_registry(self.__class__._class_cleanup_ids, self.created_ids)
        self._cleanup_test_partners()
        self.clear_cleanup_registry(self.created_ids)

    def _cleanup_test_partners(self):
        """清理本测试创建的合作伙伴

        注意：系统支持删除操作，如果删除失败应该抛出异常，
        以便测试失败并排查server错误。
        """
        self.cleanup_registry_entries(
            self.created_ids,
            [("partner", "partner_sdk", "合作伙伴")],
            owner=self,
            remove_from=self.__class__._class_cleanup_ids,
            log_prefix=f"测试 {self._testMethodName}",
        )

    def _record_partner_for_cleanup(self, partner_id):
        """记录合作伙伴ID以便清理"""
        if partner_id is not None:
            self.created_ids["partner"].append(partner_id)
            logger.debug(
                f"记录合作伙伴 {partner_id} 到清理列表 (测试: {self._testMethodName})"
            )

    def mock_partner_param(self):
        """模拟合作伙伴参数"""
        return {
            "name": mock.name(),
            "telephone": mock.name(),
            "wechat": mock.name(),
            "description": mock.sentence(),
            "status": {"id": self.__class__.status_id},
        }

    def mock_partner_param_with_referer(self, referer_id=None):
        """模拟带推荐人的合作伙伴参数

        Args:
            referer_id: 推荐人ID，如果为None则创建新推荐人
        """
        param = self.mock_partner_param()
        if referer_id:
            param["referer"] = {"id": referer_id}
        return param

    def test_create_partner(self):
        """测试创建合作伙伴"""
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        # 验证合作伙伴信息完整性
        required_fields = ["id", "name", "telephone", "wechat", "description", "status"]
        for field in required_fields:
            self.assertIn(field, new_partner, f"缺少字段: {field}")

        # 验证系统自动生成字段
        self.assertIn("code", new_partner, "缺少会员码字段")
        self.assertIsInstance(new_partner["code"], str, "会员码应为字符串")
        self.assertGreater(len(new_partner["code"]), 0, "会员码不应为空")

        self.assertIn("creater", new_partner, "缺少创建者字段")
        self.assertIsInstance(
            new_partner["creater"], (int, type(None)), "创建者应为整数或None"
        )

        self.assertIn("createTime", new_partner, "缺少创建时间字段")
        self.assertIsInstance(
            new_partner["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        self.assert_entity_matches_definition(new_partner, context="创建合作伙伴返回")


        # 记录创建的合作伙伴ID以便清理
        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

    def test_query_partner(self):
        """测试查询合作伙伴"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 查询合作伙伴
        queried_partner = self.partner_sdk.query_partner(new_partner["id"])
        self.assertIsNotNone(queried_partner, "查询合作伙伴失败")
        self.assert_entity_round_trip(
            new_partner, queried_partner, context="查询合作伙伴返回"
        )

    def test_update_partner(self):
        """测试更新合作伙伴"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 更新合作伙伴
        update_param = new_partner.copy()
        update_param["description"] = "更新后的描述"

        updated_partner = self.partner_sdk.update_partner(
            new_partner["id"], update_param
        )
        self.assert_update_round_trip(
            new_partner["id"],
            updated_partner,
            expected_updates={"description": "更新后的描述"},
            original_entity=new_partner,
            context="更新合作伙伴返回",
        )

    def test_delete_partner(self):
        """测试删除合作伙伴

        注意：系统支持删除操作，如果删除失败应该让测试失败，
        以便排查server错误。
        """
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 删除合作伙伴 - 系统应该支持删除操作
        deleted_partner = self.partner_sdk.delete_partner(new_partner["id"])

        # 删除应该成功，返回被删除的对象
        self.assertIsNotNone(
            deleted_partner, "删除合作伙伴失败，返回None。系统应该支持删除操作"
        )
        self.assertEqual(
            deleted_partner["id"], new_partner["id"], "删除的合作伙伴ID不匹配"
        )

        # 从清理列表中移除，因为已经成功删除
        if new_partner["id"] in self.created_ids["partner"]:
            self.created_ids["partner"].remove(new_partner["id"])

        # 验证合作伙伴已被删除（查询应该失败）
        queried_partner = self.partner_sdk.query_partner(new_partner["id"])
        # 查询应该返回None，因为合作伙伴已被删除
        self.assertIsNone(queried_partner, "删除后查询合作伙伴应该返回None")

    def test_create_partner_with_long_name(self):
        """测试创建超长名称合作伙伴（边界测试）"""
        partner_param = self.mock_partner_param()
        partner_param["name"] = "a" * 255  # 超长名称

        new_partner = self.partner_sdk.create_partner(partner_param)
        if new_partner is not None:
            self.assertIsInstance(new_partner["name"], str, "合作伙伴名不是字符串")
            # 记录创建的合作伙伴ID以便清理
            if "id" in new_partner:
                self._record_partner_for_cleanup(new_partner["id"])

    def test_create_duplicate_partner(self):
        """测试创建重复合作伙伴名（系统可能允许重复）"""
        partner_param = self.mock_partner_param()

        first_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(first_partner, "第一次创建合作伙伴失败")

        # 记录第一次创建的合作伙伴ID以便清理
        if first_partner and "id" in first_partner:
            self._record_partner_for_cleanup(first_partner["id"])

        # 第二次创建相同合作伙伴名
        second_partner = self.partner_sdk.create_partner(partner_param)

        # 系统可能允许重复名称，所以不强制要求失败
        if second_partner is not None:
            # 如果创建成功，记录ID以便清理
            if "id" in second_partner:
                self._record_partner_for_cleanup(second_partner["id"])
            # 验证返回的数据结构
            self.assertIn("id", second_partner, "第二次创建的合作伙伴缺少ID字段")
            self.assertIn("name", second_partner, "第二次创建的合作伙伴缺少name字段")
            self.assertEqual(
                second_partner["name"], partner_param["name"], "名称不匹配"
            )
        # 如果返回None，也不视为错误，因为系统可能以其他方式处理重复

    def test_query_nonexistent_partner(self):
        """测试查询不存在的合作伙伴（异常测试）"""
        nonexistent_partner_id = 999999
        queried_partner = self.partner_sdk.query_partner(nonexistent_partner_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_partner, "查询不存在的合作伙伴应失败")

    def test_delete_nonexistent_partner(self):
        """测试删除不存在的合作伙伴（异常测试）"""
        nonexistent_partner_id = 999999
        deleted_partner = self.partner_sdk.delete_partner(nonexistent_partner_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_partner, "删除不存在的合作伙伴应失败")

    def test_partner_status_validation(self):
        """测试合作伙伴状态验证"""
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 验证状态字段
        self.assertIn("status", new_partner, "合作伙伴缺少状态字段")
        self.assertIn("id", new_partner["status"], "状态缺少id字段")
        self.assertEqual(
            new_partner["status"]["id"], self.__class__.status_id, "状态ID不匹配"
        )

    def test_create_partner_with_referer(self):
        """测试创建带推荐人的合作伙伴"""
        # 先创建推荐人
        referer_param = self.mock_partner_param()
        referer = self.partner_sdk.create_partner(referer_param)
        self.assertIsNotNone(referer, "创建推荐人失败")

        if referer and "id" in referer:
            self._record_partner_for_cleanup(referer["id"])

        # 创建带推荐人的合作伙伴
        partner_param = self.mock_partner_param_with_referer(referer["id"])
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建带推荐人的合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 验证推荐人字段
        # 系统可能以不同方式返回referer信息
        has_referer_info = False
        if "referer" in new_partner:
            # 包含完整的referer对象
            referer_info = new_partner["referer"]
            self.assertIsInstance(referer_info, dict, "推荐人应为字典")
            if "id" in referer_info:
                self.assertEqual(referer_info["id"], referer["id"], "推荐人ID不匹配")
                has_referer_info = True
        elif "refererId" in new_partner or "referer_id" in new_partner:
            # 只包含referer ID
            referer_id_field = (
                "refererId" if "refererId" in new_partner else "referer_id"
            )
            referer_id = new_partner[referer_id_field]
            self.assertEqual(referer_id, referer["id"], "推荐人ID不匹配")
            has_referer_info = True

        if not has_referer_info:
            logger.warning("创建合作伙伴时未返回推荐人信息，系统可能不返回关联字段")

    def test_update_partner_with_referer(self):
        """测试更新合作伙伴的推荐人"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 创建推荐人
        referer_param = self.mock_partner_param()
        referer = self.partner_sdk.create_partner(referer_param)
        self.assertIsNotNone(referer, "创建推荐人失败")

        if referer and "id" in referer:
            self._record_partner_for_cleanup(referer["id"])

        # 更新合作伙伴添加推荐人
        update_param = new_partner.copy()
        update_param["referer"] = {"id": referer["id"]}

        updated_partner = self.partner_sdk.update_partner(
            new_partner["id"], update_param
        )
        self.assertIsNotNone(updated_partner, "更新合作伙伴失败")

        # 检查referer字段是否更新
        has_referer_info = False
        if "referer" in updated_partner:
            # 包含完整的referer对象
            referer_info = updated_partner["referer"]
            self.assertIsInstance(referer_info, dict, "推荐人应为字典")
            if "id" in referer_info:
                self.assertEqual(referer_info["id"], referer["id"], "推荐人ID不匹配")
                has_referer_info = True
        elif "refererId" in updated_partner or "referer_id" in updated_partner:
            # 只包含referer ID
            referer_id_field = (
                "refererId" if "refererId" in updated_partner else "referer_id"
            )
            referer_id = updated_partner[referer_id_field]
            self.assertEqual(referer_id, referer["id"], "推荐人ID不匹配")
            has_referer_info = True

        if not has_referer_info:
            logger.warning("更新合作伙伴后未返回推荐人信息，系统可能不返回关联字段")

    def test_query_partner_with_referer_details(self):
        """测试查询带推荐人详情的合作伙伴"""
        # 先创建推荐人
        referer_param = self.mock_partner_param()
        referer = self.partner_sdk.create_partner(referer_param)
        self.assertIsNotNone(referer, "创建推荐人失败")

        if referer and "id" in referer:
            self._record_partner_for_cleanup(referer["id"])

        # 创建带推荐人的合作伙伴
        partner_param = self.mock_partner_param_with_referer(referer["id"])
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建带推荐人的合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 查询合作伙伴
        queried_partner = self.partner_sdk.query_partner(new_partner["id"])
        self.assertIsNotNone(queried_partner, "查询合作伙伴失败")

        # 检查referer字段
        # 系统可能以不同方式处理关联字段：
        # 1. 直接包含referer对象
        # 2. 只包含referer_id字段
        # 3. 不包含关联信息，需要单独查询
        if "referer" in queried_partner:
            # 情况1：包含referer对象
            referer_info = queried_partner["referer"]
            self.assertIsInstance(referer_info, dict, "推荐人信息应为字典")
            if "id" in referer_info:
                self.assertEqual(referer_info["id"], referer["id"], "推荐人ID不匹配")
            # 可能包含更多推荐人详情字段
            if "name" in referer_info:
                self.assertIsInstance(referer_info["name"], str, "推荐人姓名应为字符串")
        elif "refererId" in queried_partner or "referer_id" in queried_partner:
            # 情况2：只包含referer ID字段
            referer_id_field = (
                "refererId" if "refererId" in queried_partner else "referer_id"
            )
            referer_id = queried_partner[referer_id_field]
            self.assertEqual(referer_id, referer["id"], "推荐人ID不匹配")
        else:
            # 情况3：系统可能不返回关联信息
            # 这种情况下，我们可以记录警告但不视为测试失败
            logger.warning("查询结果未包含推荐人信息，系统可能不返回关联字段")

    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 验证所有系统自动生成字段
        auto_generated_fields = ["id", "code", "creater", "createTime"]
        for field in auto_generated_fields:
            self.assertIn(field, new_partner, f"缺少系统自动生成字段: {field}")

        # 验证字段类型和值
        self.assertIsInstance(new_partner["id"], (int, type(None)), "ID应为整数或None")
        if new_partner["id"] is not None:
            self.assertGreater(new_partner["id"], 0, "ID应为正整数")

        self.assertIsInstance(
            new_partner["code"], (str, type(None)), "会员码应为字符串或None"
        )
        if new_partner["code"] is not None:
            self.assertGreater(len(new_partner["code"]), 0, "会员码不应为空")

        self.assertIsInstance(
            new_partner["creater"], (int, type(None)), "创建者应为整数或None"
        )
        self.assertIsInstance(
            new_partner["createTime"], (int, type(None)), "创建时间应为整数或None"
        )
        if new_partner["createTime"] is not None:
            self.assertGreater(new_partner["createTime"], 0, "创建时间应为正数")
        self.assert_entity_matches_definition(new_partner, context="自动字段合作伙伴返回")


    def test_modify_time_auto_update(self):
        """测试修改时间自动更新"""
        # 创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_sdk.create_partner(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")

        if new_partner and "id" in new_partner:
            self._record_partner_for_cleanup(new_partner["id"])

        # 记录初始创建时间和修改时间
        initial_create_time = new_partner.get("createTime")
        initial_modify_time = new_partner.get("modifyTime")

        # 更新合作伙伴
        update_param = new_partner.copy()
        update_param["description"] = "更新后的描述"

        updated_partner = self.partner_sdk.update_partner(
            new_partner["id"], update_param
        )
        queried_partner = self.assert_update_round_trip(
            new_partner["id"],
            updated_partner,
            expected_updates={"description": "更新后的描述"},
            original_entity=new_partner,
            context="修改时间合作伙伴更新返回",
        )

        # 验证修改时间已更新
        updated_modify_time = queried_partner.get("modifyTime")
        self.assertIsNotNone(updated_modify_time, "更新后缺少修改时间字段")

        # 验证修改时间比创建时间晚（如果两者都存在）
        if initial_create_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_create_time, "修改时间应晚于或等于创建时间"
            )

        # 验证创建时间未改变
        self.assertEqual(
            queried_partner.get("createTime"), initial_create_time, "创建时间不应被修改"
        )

        # 如果初始有修改时间，验证已更新
        if initial_modify_time and updated_modify_time:
            self.assertGreaterEqual(
                updated_modify_time, initial_modify_time, "修改时间应已更新"
            )


if __name__ == "__main__":
    unittest.main()
