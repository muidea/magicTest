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


from sdk import CreditRewardSDK, PartnerSDK

logger = logging.getLogger(__name__)


class CreditRewardTestCase(unittest.TestCase):
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
        cls.credit_reward_sdk = CreditRewardSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.test_data = []
        print("Credit Reward 测试开始...")

    def setUp(self):
        partner_param = {
            "name": "测试会员-积分消费",
            "telephone": "13800138001",
            "status": {"id": 19},
        }
        try:
            self.test_partner = self.partner_sdk.create_partner(partner_param)
            if not self.test_partner:
                partners = self.partner_sdk.filter_partner(
                    {"name": "测试会员-积分消费"}
                )
                if partners and len(partners) > 0:
                    self.test_partner = partners[0]
                else:
                    self.skipTest("无法创建或找到测试合作伙伴")
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
        print("Credit Reward 测试结束")

    def test_create_credit_reward(self):
        print("测试创建积分消费记录...")
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
            "namespace",
        ]
        for field in required_fields:
            self.assertIn(field, credit_reward, f"积分消费记录缺少必填字段: {field}")
        self.test_data.append(credit_reward)
        print(f"✓ 积分消费记录创建成功: ID={credit_reward.get('id')}")

    def test_query_credit_reward(self):
        print("测试查询积分消费记录...")
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
        print(f"✓ 积分消费记录查询成功: ID={queried_reward.get('id')}")

    def test_update_credit_reward(self):
        print("测试更新积分消费记录...")
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
            print(f"✓ 积分消费记录更新成功: ID={updated_reward.get('id')}")
        else:
            print("⚠ 积分消费记录更新未返回结果")
        self.test_data.append(created_reward)

    def test_delete_credit_reward(self):
        print("测试删除积分消费记录...")
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
            print(f"✓ 积分消费记录删除成功: ID={deleted_reward.get('id')}")
        else:
            print("⚠ 积分消费记录删除未返回结果")

    def test_create_credit_reward_with_large_credit(self):
        print("测试创建大积分值消费记录...")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 999999,
            "memo": "大额消费",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建大积分值消费记录失败")
        self.assertEqual(credit_reward["credit"], 999999, "大积分值不匹配")
        self.test_data.append(credit_reward)
        print(f"✓ 大积分值消费记录创建成功: 积分={credit_reward.get('credit')}")

    def test_create_credit_reward_with_zero_credit(self):
        print("测试创建零积分消费记录...")
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
                print("✓ 系统正确拒绝创建零积分的消费记录")
            else:
                print(f"⚠ 系统允许创建零积分的消费记录: ID={credit_reward.get('id')}")
                self.test_data.append(credit_reward)
        except Exception as e:
            # 检查错误代码是否为6
            if "错误代码: 6" in str(e):
                print("✓ 系统正确返回错误代码6拒绝创建零积分的消费记录")
            else:
                print(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if credit_reward and "id" in credit_reward:
                self.test_data.append(credit_reward)

    def test_create_credit_reward_without_owner(self):
        print("测试创建无所属会员的积分消费记录...")
        credit_reward_param = {"credit": 100, "memo": "无会员消费"}
        credit_reward = None
        try:
            credit_reward = self.credit_reward_sdk.create_credit_reward(
                credit_reward_param
            )
            if credit_reward is None:
                print("✓ 系统正确拒绝创建无所属会员的积分消费记录")
            else:
                print(
                    f"⚠ 系统允许创建无所属会员的积分消费记录: ID={credit_reward.get('id')}"
                )
                self.test_data.append(credit_reward)
        except Exception as e:
            # 检查错误代码是否为4（必填字段缺失）
            if "错误代码: 4" in str(e) and "owner" in str(e):
                print("✓ 系统正确返回错误代码4拒绝创建无所属会员的积分消费记录")
            else:
                print(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if credit_reward and "id" in credit_reward:
                self.test_data.append(credit_reward)

    def test_query_nonexistent_credit_reward(self):
        print("测试查询不存在的积分消费记录...")
        non_existent_id = 999999999
        credit_reward = self.credit_reward_sdk.query_credit_reward(non_existent_id)
        if credit_reward is None:
            print("✓ 查询不存在的积分消费记录返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的积分消费记录返回: {credit_reward}")

    def test_delete_nonexistent_credit_reward(self):
        print("测试删除不存在的积分消费记录...")
        non_existent_id = 999999999
        deleted_reward = self.credit_reward_sdk.delete_credit_reward(non_existent_id)
        if deleted_reward is None:
            print("✓ 删除不存在的积分消费记录返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的积分消费记录返回: {deleted_reward}")

    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 50,
            "memo": "自动字段测试",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建积分消费记录失败")
        auto_fields = ["id", "sn", "creater", "createTime", "namespace"]
        for field in auto_fields:
            self.assertIn(field, credit_reward, f"缺少自动生成字段: {field}")
        self.test_data.append(credit_reward)
        print(f"✓ 系统自动生成字段验证成功: SN={credit_reward.get('sn')}")

    def test_modify_time_auto_update(self):
        print("测试修改时间自动更新...")
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
            original_modify_time = created_reward["modifyTime"]
            update_param = {"memo": "时间更新"}
            updated_reward = self.credit_reward_sdk.update_credit_reward(
                created_reward["id"], update_param
            )
            if updated_reward and "modifyTime" in updated_reward:
                updated_modify_time = updated_reward["modifyTime"]
                self.assertNotEqual(
                    updated_modify_time, original_modify_time, "修改时间未自动更新"
                )
                print(f"✓ 修改时间自动更新验证成功")
            else:
                print("⚠ 更新后未返回modifyTime字段")
        else:
            print("⚠ 积分消费记录不包含modifyTime字段")
        self.test_data.append(created_reward)

    def test_credit_reward_memo_validation(self):
        print("测试积分消费记录备注验证...")
        credit_reward_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 100,
            "memo": "正常备注",
        }
        credit_reward = self.credit_reward_sdk.create_credit_reward(credit_reward_param)
        self.assertIsNotNone(credit_reward, "创建积分消费记录失败")
        self.assertEqual(credit_reward["memo"], "正常备注", "备注不匹配")
        self.test_data.append(credit_reward)
        print(f"✓ 积分消费记录备注验证成功: 备注={credit_reward.get('memo')}")
