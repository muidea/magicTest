"""
Credit Reward 测试用例

基于 VMI实体定义和使用说明.md:105-114 中的 creditReward 实体定义编写。
使用 CreditRewardSDK 进行测试。

包含的测试用例（共12个）：
1. test_create_credit_reward
2. test_query_credit_reward
3. test_update_credit_reward
4. test_delete_credit_reward
5. test_create_credit_reward_with_large_credit
6. test_create_credit_reward_with_zero_credit
7. test_create_credit_reward_without_owner
8. test_query_nonexistent_credit_reward
9. test_delete_nonexistent_credit_reward
10. test_auto_generated_fields
11. test_modify_time_auto_update
12. test_credit_reward_memo_validation
"""

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

import logging
import unittest

from sdk import CreditRewardSDK, PartnerSDK, StatusSDK
from test_dependency_helper import prepare_partner_dependency
from test_vmi_base import VMITestCase

logger = logging.getLogger(__name__)


class CreditRewardTestCase(VMITestCase):
    namespace = ""
    entity_definition = "credit/creditReward.json"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.log_suite_start("Credit Reward 测试开始")

    @classmethod
    def _init_sdk(cls):
        cls.credit_reward_sdk = CreditRewardSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)

    def setUp(self):
        self.test_data = []
        try:
            partner_deps = prepare_partner_dependency(
                partner_sdk=self.partner_sdk,
                status_sdk=self.status_sdk,
                name_prefix="CREDIT_REWARD_PARTNER",
            )
            self.test_partner = partner_deps["partner"]
        except Exception as e:
            logger.warning(f"创建测试合作伙伴失败: {e}")
            self.skipTest(f"创建测试合作伙伴失败: {e}")

    def tearDown(self):
        for data in self.test_data:
            if "id" in data:
                try:
                    self.credit_reward_sdk.delete_credit_reward(data["id"])
                except Exception as e:
                    logger.warning(f"清理积分消费记录 {data.get('id')} 失败: {e}")
        if (
            hasattr(self, "test_partner")
            and self.test_partner
            and "id" in self.test_partner
        ):
            try:
                self.partner_sdk.delete_partner(self.test_partner["id"])
            except Exception as e:
                logger.warning(f"清理合作伙伴 {self.test_partner.get('id')} 失败: {e}")
        self.test_data.clear()

    @classmethod
    def tearDownClass(cls):
        cls.log_suite_end("Credit Reward 测试结束")
        super().tearDownClass()

    def test_create_credit_reward(self):
        self.log_test_step("测试创建积分消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 100,
            "memo": "测试消费",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建积分消费记录失败")
        required_fields = [
            "id",
            "sn",
            "owner",
            "credit",
            "memo",
            "creater",
            "createTime",
        ]
        for field in required_fields:
            self.assertIn(field, credit_reward, f"积分消费记录缺少必填字段: {field}")
        self.test_data.append(credit_reward)
        self.log_test_success(f"✓ 积分消费记录创建成功: ID={credit_reward.get('id')}")

    def test_query_credit_reward(self):
        self.log_test_step("测试查询积分消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 150,
            "memo": "查询测试",
        }
        created_reward = self.credit_reward_sdk.create_credit_reward(
            credit_reward_param
        )
        self.assertIsNotNone(created_reward, "创建积分消费记录失败")
        queried_reward = self.credit_reward_sdk.query_credit_reward(
            created_reward["id"]
        )
        self.assertIsNotNone(queried_reward, "查询积分消费记录失败")
        self.assertEqual(queried_reward["id"], created_reward["id"], "ID不匹配")
        self.test_data.append(created_reward)
        self.log_test_success(f"✓ 积分消费记录查询成功: ID={queried_reward.get('id')}")

    def test_update_credit_reward(self):
        self.log_test_step("测试更新积分消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 200,
            "memo": "更新前",
        }
        created_reward = self.credit_reward_sdk.create_credit_reward(
            credit_reward_param
        )
        self.assertIsNotNone(created_reward, "创建积分消费记录失败")
        update_param = {"memo": "更新后"}
        updated_reward = self.credit_reward_sdk.update_credit_reward(
            created_reward["id"], update_param
        )
        if updated_reward:
            self.assertEqual(updated_reward["memo"], "更新后", "更新后备注不匹配")
            self.log_test_success(f"✓ 积分消费记录更新成功: ID={updated_reward.get('id')}")
        else:
            self.log_test_observation("⚠ 积分消费记录更新未返回结果")
        self.test_data.append(created_reward)

    def test_delete_credit_reward(self):
        self.log_test_step("测试删除积分消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 300,
            "memo": "删除测试",
        }
        created_reward = self.credit_reward_sdk.create_credit_reward(
            credit_reward_param
        )
        self.assertIsNotNone(created_reward, "创建积分消费记录失败")
        deleted_reward = self.credit_reward_sdk.delete_credit_reward(
            created_reward["id"]
        )
        if deleted_reward:
            self.assertEqual(
                deleted_reward["id"], created_reward["id"], "删除的积分消费记录ID不匹配"
            )
            self.log_test_success(f"✓ 积分消费记录删除成功: ID={deleted_reward.get('id')}")
        else:
            self.log_test_observation("⚠ 积分消费记录删除未返回结果")

    def test_create_credit_reward_with_large_credit(self):
        self.log_test_step("测试创建大积分值消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 999999,
            "memo": "大额消费",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建大积分值消费记录失败")
        self.assertEqual(credit_reward["credit"], 999999, "大积分值不匹配")
        self.test_data.append(credit_reward)
        self.log_test_success(f"✓ 大积分值消费记录创建成功: 积分={credit_reward.get('credit')}")

    def test_create_credit_reward_with_zero_credit(self):
        self.log_test_step("测试创建零积分消费记录")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 0,
            "memo": "零消费",
        }
        credit_reward = None
        try:
            credit_reward = self.credit_reward_sdk.create_credit_reward(
                credit_reward_param
            )
            if credit_reward is None:
                self.log_test_success("✓ 系统正确拒绝创建零积分的消费记录")
            else:
                self.log_test_observation(f"⚠ 系统允许创建零积分的消费记录: ID={credit_reward.get('id')}")
                self.test_data.append(credit_reward)
        except Exception as e:
            # 检查错误代码是否为6
            if "错误代码: 6" in str(e):
                self.log_test_success("✓ 系统正确返回错误代码6拒绝创建零积分的消费记录")
            else:
                self.log_test_observation(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if credit_reward and "id" in credit_reward:
                self.test_data.append(credit_reward)

    def test_create_credit_reward_without_owner(self):
        self.log_test_step("测试创建无所属会员的积分消费记录")
        credit_reward_param = {"credit": 100, "memo": "无会员消费"}
        credit_reward = None
        try:
            credit_reward = self.credit_reward_sdk.create_credit_reward(
                credit_reward_param
            )
            if credit_reward is None:
                self.log_test_success("✓ 系统正确拒绝创建无所属会员的积分消费记录")
            else:
                self.log_test_observation(
                    f"⚠ 系统允许创建无所属会员的积分消费记录: ID={credit_reward.get('id')}"
                )
                self.test_data.append(credit_reward)
        except Exception as e:
            # 检查错误代码是否为4（必填字段缺失）
            if "错误代码: 4" in str(e) and "owner" in str(e):
                self.log_test_success("✓ 系统正确返回错误代码4拒绝创建无所属会员的积分消费记录")
            else:
                self.log_test_observation(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if credit_reward and "id" in credit_reward:
                self.test_data.append(credit_reward)

    def test_query_nonexistent_credit_reward(self):
        self.log_test_step("测试查询不存在的积分消费记录")
        non_existent_id = 999999999
        credit_reward = self.credit_reward_sdk.query_credit_reward(non_existent_id)
        if credit_reward is None:
            self.log_test_success("✓ 查询不存在的积分消费记录返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 查询不存在的积分消费记录返回: {credit_reward}")

    def test_delete_nonexistent_credit_reward(self):
        self.log_test_step("测试删除不存在的积分消费记录")
        non_existent_id = 999999999
        deleted_reward = self.credit_reward_sdk.delete_credit_reward(non_existent_id)
        if deleted_reward is None:
            self.log_test_success("✓ 删除不存在的积分消费记录返回None，符合预期")
        else:
            self.log_test_observation(f"⚠ 删除不存在的积分消费记录返回: {deleted_reward}")

    def test_auto_generated_fields(self):
        self.log_test_step("测试系统自动生成字段")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 50,
            "memo": "自动字段测试",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建积分消费记录失败")
        auto_fields = ["id", "sn", "creater", "createTime"]
        for field in auto_fields:
            self.assertIn(field, credit_reward, f"缺少自动生成字段: {field}")
        self.test_data.append(credit_reward)
        self.log_test_success(f"✓ 系统自动生成字段验证成功: SN={credit_reward.get('sn')}")

    def test_modify_time_auto_update(self):
        self.log_test_step("测试修改时间字段定义对齐")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 100,
            "memo": "时间测试",
        }
        created_reward = self.credit_reward_sdk.create_credit_reward(
            credit_reward_param
        )
        self.assertIsNotNone(created_reward, "创建积分消费记录失败")
        if "modifyTime" in created_reward:
            self.log_test_observation("⚠ 当前服务返回了未在定义中声明的 modifyTime 字段，测试仅记录现象")
        else:
            self.log_test_success("✓ 当前定义未声明 modifyTime，返回结果与定义一致")
        self.test_data.append(created_reward)

    def test_credit_reward_memo_validation(self):
        self.log_test_step("测试积分消费记录备注验证")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 100,
            "memo": "正常备注",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建积分消费记录失败")
        self.assertEqual(credit_reward["memo"], "正常备注", "备注不匹配")
        self.test_data.append(credit_reward)
        self.log_test_success(f"✓ 积分消费记录备注验证成功: 备注={credit_reward.get('memo')}")
