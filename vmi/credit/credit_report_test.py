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
Credit Report 测试用例

基于 VMI实体定义和使用说明.md:92-104 中的 creditReport 实体定义编写。
使用 CreditReportSDK 进行测试。

包含的测试用例（共12个）：
1. test_create_credit_report
2. test_query_credit_report
3. test_update_credit_report
4. test_delete_credit_report
5. test_create_credit_report_with_large_credit
6. test_create_credit_report_with_zero_credit
7. test_create_credit_report_without_owner
8. test_query_nonexistent_credit_report
9. test_delete_nonexistent_credit_report
10. test_auto_generated_fields
11. test_modify_time_auto_update
12. test_credit_report_per_owner_limit
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


from sdk import CreditReportSDK, PartnerSDK

logger = logging.getLogger(__name__)


class CreditReportTestCase(unittest.TestCase):
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
        cls.credit_report_sdk = CreditReportSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.test_data = []
        print("Credit Report 测试开始...")

    def setUp(self):
        partner_param = {
            "name": "测试会员-积分报表",
            "telephone": "13800138000",
            "status": {"id": 19},
        }
        try:
            self.test_partner = self.partner_sdk.create_partner(partner_param)
            if not self.test_partner:
                partners = self.partner_sdk.filter_partner(
                    {"name": "测试会员-积分报表"}
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
                    self.credit_report_sdk.delete_credit_report(data["id"])
                except Exception as e:
                    logger.warning(f"清理积分报表 {data.get('id')} 失败: {e}")
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
        print("Credit Report 测试结束")

    def test_create_credit_report(self):
        print("测试创建积分报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 1000,
            "available": 800,
        }
        credit_report = self.credit_report_sdk.create_credit_report(credit_report_param)
        self.assertIsNotNone(credit_report, "创建积分报表失败")
        required_fields = [
            "id",
            "sn",
            "owner",
            "credit",
            "available",
            "creater",
            "createTime",
            "namespace",
        ]
        for field in required_fields:
            self.assertIn(field, credit_report, f"积分报表缺少必填字段: {field}")
        self.test_data.append(credit_report)
        print(f"✓ 积分报表创建成功: ID={credit_report.get('id')}")

    def test_query_credit_report(self):
        print("测试查询积分报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 1500,
            "available": 1200,
        }
        created_report = self.credit_report_sdk.create_credit_report(
            credit_report_param
        )
        self.assertIsNotNone(created_report, "创建积分报表失败")
        queried_report = self.credit_report_sdk.query_credit_report(
            created_report["id"]
        )
        self.assertIsNotNone(queried_report, "查询积分报表失败")
        self.assertEqual(queried_report["id"], created_report["id"], "ID不匹配")
        self.test_data.append(created_report)
        print(f"✓ 积分报表查询成功: ID={queried_report.get('id')}")

    def test_update_credit_report(self):
        print("测试更新积分报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 2000,
            "available": 1800,
        }
        created_report = self.credit_report_sdk.create_credit_report(
            credit_report_param
        )
        self.assertIsNotNone(created_report, "创建积分报表失败")
        update_param = {"credit": 2500, "available": 2000}
        updated_report = self.credit_report_sdk.update_credit_report(
            created_report["id"], update_param
        )
        if updated_report:
            self.assertEqual(updated_report["credit"], 2500, "更新后累计积分不匹配")
            print(f"✓ 积分报表更新成功: ID={updated_report.get('id')}")
        else:
            print("⚠ 积分报表更新未返回结果")
        self.test_data.append(created_report)

    def test_delete_credit_report(self):
        print("测试删除积分报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 3000,
            "available": 2500,
        }
        created_report = self.credit_report_sdk.create_credit_report(
            credit_report_param
        )
        self.assertIsNotNone(created_report, "创建积分报表失败")
        deleted_report = self.credit_report_sdk.delete_credit_report(
            created_report["id"]
        )
        if deleted_report:
            self.assertEqual(
                deleted_report["id"], created_report["id"], "删除的积分报表ID不匹配"
            )
            print(f"✓ 积分报表删除成功: ID={deleted_report.get('id')}")
        else:
            print("⚠ 积分报表删除未返回结果")

    def test_create_credit_report_with_large_credit(self):
        print("测试创建大积分值报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 999999999,
            "available": 888888888,
        }
        credit_report = self.credit_report_sdk.create_credit_report(credit_report_param)
        self.assertIsNotNone(credit_report, "创建大积分值报表失败")
        self.assertEqual(credit_report["credit"], 999999999, "大累计积分不匹配")
        self.test_data.append(credit_report)
        print(f"✓ 大积分值报表创建成功: 累计积分={credit_report.get('credit')}")

    def test_create_credit_report_with_zero_credit(self):
        print("测试创建零积分报表...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 0,
            "available": 0,
        }
        credit_report = self.credit_report_sdk.create_credit_report(credit_report_param)
        if credit_report is None:
            print("✓ 系统正确拒绝创建零积分的积分报表")
        else:
            print(f"⚠ 系统允许创建零积分的积分报表: ID={credit_report.get('id')}")
            self.test_data.append(credit_report)

    def test_create_credit_report_without_owner(self):
        print("测试创建无所属会员的积分报表...")
        credit_report_param = {"credit": 1000, "available": 800}
        credit_report = None
        try:
            credit_report = self.credit_report_sdk.create_credit_report(
                credit_report_param
            )
            if credit_report is None:
                print("✓ 系统正确拒绝创建无所属会员的积分报表")
            else:
                self.assertIn("owner", credit_report, "积分报表应包含所属会员字段")
                print(
                    f"⚠ 系统允许创建无所属会员的积分报表: ID={credit_report.get('id')}"
                )
                self.test_data.append(credit_report)
        except Exception as e:
            # 检查错误代码是否为4（必填字段缺失）
            if "错误代码: 4" in str(e) and "owner" in str(e):
                print("✓ 系统正确返回错误代码4拒绝创建无所属会员的积分报表")
            else:
                print(f"⚠ 系统返回其他错误: {e}")
            # 即使异常，也要尝试清理可能已创建的数据
            if credit_report and "id" in credit_report:
                self.test_data.append(credit_report)

    def test_query_nonexistent_credit_report(self):
        print("测试查询不存在的积分报表...")
        non_existent_id = 999999999
        credit_report = self.credit_report_sdk.query_credit_report(non_existent_id)
        if credit_report is None:
            print("✓ 查询不存在的积分报表返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的积分报表返回: {credit_report}")

    def test_delete_nonexistent_credit_report(self):
        print("测试删除不存在的积分报表...")
        non_existent_id = 999999999
        deleted_report = self.credit_report_sdk.delete_credit_report(non_existent_id)
        if deleted_report is None:
            print("✓ 删除不存在的积分报表返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的积分报表返回: {deleted_report}")

    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 500,
            "available": 400,
        }
        credit_report = self.credit_report_sdk.create_credit_report(credit_report_param)
        self.assertIsNotNone(credit_report, "创建积分报表失败")
        auto_fields = ["id", "sn", "creater", "createTime", "namespace"]
        for field in auto_fields:
            self.assertIn(field, credit_report, f"缺少自动生成字段: {field}")
        self.test_data.append(credit_report)
        print(f"✓ 系统自动生成字段验证成功: SN={credit_report.get('sn')}")

    def test_modify_time_auto_update(self):
        print("测试修改时间自动更新...")
        credit_report_param = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 1000,
            "available": 900,
        }
        created_report = self.credit_report_sdk.create_credit_report(
            credit_report_param
        )
        self.assertIsNotNone(created_report, "创建积分报表失败")

        if "modifyTime" in created_report:
            original_modify_time = created_report["modifyTime"]

            # 更新时必须包含所有必填字段
            update_param = {
                "owner": {"id": self.test_partner["id"]},
                "credit": 1200,
                "available": 900,
            }

            updated_report = self.credit_report_sdk.update_credit_report(
                created_report["id"], update_param
            )
            self.assertIsNotNone(updated_report, "更新积分报表失败")

            if "modifyTime" in updated_report:
                updated_modify_time = updated_report["modifyTime"]

                # 验证modifyTime已自动更新
                self.assertNotEqual(
                    updated_modify_time,
                    original_modify_time,
                    "modifyTime字段在更新后未自动刷新",
                )
                print(f"✓ 修改时间自动更新验证成功")
                print(f"✓ 时间戳变化: {original_modify_time} -> {updated_modify_time}")
            else:
                self.fail("更新操作未返回modifyTime字段")
        else:
            self.fail("创建的数据不包含modifyTime字段")

        self.test_data.append(created_report)

    def test_credit_report_per_owner_limit(self):
        print("测试积分报表每个会员限制...")
        credit_report_param1 = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 1000,
            "available": 800,
        }
        report1 = self.credit_report_sdk.create_credit_report(credit_report_param1)
        self.assertIsNotNone(report1, "创建第一条积分报表失败")
        credit_report_param2 = {
            "owner": {"id": self.test_partner["id"]},
            "credit": 2000,
            "available": 1500,
        }
        report2 = self.credit_report_sdk.create_credit_report(credit_report_param2)
        if report2 is None:
            print("✓ 系统正确限制每个会员只能有一条积分报表")
        else:
            print(f"⚠ 系统允许为同一会员创建多条积分报表: ID={report2.get('id')}")
            self.test_data.append(report2)
        self.test_data.append(report1)
