"""Operation Log 测试用例 — 覆盖 write / filter 及边界异常场景"""

import logging
import os
import unittest
import warnings

from session import session
from operation_log import operation_log


logger = logging.getLogger(__name__)


class OperationLogTestCase(unittest.TestCase):
    """OperationLog 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.oplog_instance = operation_log.OperationLog(cls.work_session)

    def test_write_operation_log(self):
        """测试写入操作日志（基本流程）"""
        log_param = operation_log.mock_operation_log_param()
        result = self.oplog_instance.write_operation_log(log_param)
        self.assertTrue(result, "写入操作日志失败")

    def test_filter_operation_log(self):
        """测试过滤操作日志（先写后查）"""
        log_param = operation_log.mock_operation_log_param()
        write_ok = self.oplog_instance.write_operation_log(log_param)
        self.assertTrue(write_ok, "写入操作日志（用于过滤）失败")

        filter_param = {
            "params": {
                "items": {
                    "operator": "{0}|=".format(log_param["operator"]),
                }
            }
        }
        log_list = self.oplog_instance.filter_operation_log(filter_param)
        self.assertIsNotNone(log_list, "过滤操作日志失败")
        self.assertGreater(len(log_list), 0, "过滤结果为空")

        # 验证写入的日志出现在过滤结果中
        found = any(
            item.get("operator") == log_param["operator"] for item in log_list
        )
        self.assertTrue(found, "写入的操作日志未出现在过滤结果中")

    def test_write_with_minimal_fields(self):
        """测试写入仅含必填字段的操作日志"""
        minimal_param = {
            "operator": "test_user",
            "operation": "test_operation",
            "targetType": "test_target",
            "result": "SUCCESS",
        }
        result = self.oplog_instance.write_operation_log(minimal_param)
        self.assertTrue(result, "写入最小字段操作日志失败")

    def test_filter_with_empty_result(self):
        """测试过滤条件不匹配时返回空列表或None"""
        filter_param = {
            "params": {
                "items": {
                    "operator": "nonexistent_user_xyz|=",
                }
            }
        }
        log_list = self.oplog_instance.filter_operation_log(filter_param)
        if log_list is not None:
            self.assertEqual(len(log_list), 0, "不匹配条件应返回空列表")

    def test_write_log_with_all_fields(self):
        """测试写入包含全部字段的操作日志"""
        full_param = operation_log.mock_operation_log_param()
        full_param["timestamp"] = "2025-01-01 12:00:00"
        full_param["details"] = "Full details for operation log test"
        result = self.oplog_instance.write_operation_log(full_param)
        self.assertTrue(result, "写入全字段操作日志失败")

    def test_write_and_filter_by_result(self):
        """测试写入后按 result 字段过滤"""
        log_param = operation_log.mock_operation_log_param()
        log_param["result"] = "FAILURE"
        write_ok = self.oplog_instance.write_operation_log(log_param)
        self.assertTrue(write_ok, "写入操作日志（用于result过滤）失败")

        filter_param = {
            "params": {
                "items": {
                    "result": "FAILURE|=",
                }
            }
        }
        log_list = self.oplog_instance.filter_operation_log(filter_param)
        self.assertIsNotNone(log_list, "按result过滤操作日志失败")
        if log_list:
            self.assertTrue(
                all(item.get("result") == "FAILURE" for item in log_list),
                "过滤结果包含非FAILURE记录",
            )

    def test_write_and_filter_by_target(self):
        """测试写入后按 targetType 和 targetID 组合过滤"""
        log_param = operation_log.mock_operation_log_param()
        log_param["targetType"] = "order"
        log_param["targetID"] = 10086
        write_ok = self.oplog_instance.write_operation_log(log_param)
        self.assertTrue(write_ok, "写入操作日志（用于target过滤）失败")

        filter_param = {
            "params": {
                "items": {
                    "targetType": "order|=",
                    "targetID": "10086|=",
                }
            }
        }
        log_list = self.oplog_instance.filter_operation_log(filter_param)
        self.assertIsNotNone(log_list, "按target过滤操作日志失败")
        if log_list:
            found = any(
                item.get("targetID") == 10086 for item in log_list
            )
            self.assertTrue(found, "目标操作日志未出现在过滤结果中")

    def test_filter_with_time_range(self):
        """测试按时间范围过滤操作日志"""
        log_param = operation_log.mock_operation_log_param()
        log_param["timestamp"] = "2025-06-15 10:30:00"
        self.oplog_instance.write_operation_log(log_param)

        filter_param = {
            "params": {
                "items": {
                    "timestamp": "2025-06-01 00:00:00|>=,2025-06-30 23:59:59|<=",
                }
            }
        }
        log_list = self.oplog_instance.filter_operation_log(filter_param)
        self.assertIsNotNone(log_list, "时间范围过滤操作日志失败")

    def test_write_log_with_chinese_operator(self):
        """测试写入含中文操作者的操作日志"""
        chinese_param = operation_log.mock_operation_log_param()
        chinese_param["operator"] = "管理员"
        chinese_param["operation"] = "审核通过"
        result = self.oplog_instance.write_operation_log(chinese_param)
        self.assertTrue(result, "写入含中文操作者的操作日志失败")


if __name__ == "__main__":
    unittest.main()
