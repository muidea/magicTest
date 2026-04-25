"""Access Log 测试用例 — 覆盖 write / filter 及边界异常场景"""

import logging
import os
import unittest
import warnings

from session import session
from access_log import access_log


logger = logging.getLogger(__name__)


class AccessLogTestCase(unittest.TestCase):
    """AccessLog 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.access_log_instance = access_log.AccessLog(cls.work_session)

    def test_write_access_log(self):
        """测试写入访问日志（基本流程）"""
        log_param = access_log.mock_access_log_param()
        result = self.access_log_instance.write_access_log(log_param)
        self.assertTrue(result, "写入访问日志失败")

    def test_filter_access_log(self):
        """测试过滤访问日志（先写后查）"""
        log_param = access_log.mock_access_log_param()
        write_ok = self.access_log_instance.write_access_log(log_param)
        self.assertTrue(write_ok, "写入访问日志（用于过滤）失败")

        filter_param = {
            "params": {
                "items": {
                    "clientIP": "{0}|=".format(log_param["clientIP"]),
                }
            }
        }
        log_list = self.access_log_instance.filter_access_log(filter_param)
        self.assertIsNotNone(log_list, "过滤访问日志失败")
        self.assertGreater(len(log_list), 0, "过滤结果为空")

        # 验证写入的日志出现在过滤结果中
        found = any(
            item.get("clientIP") == log_param["clientIP"] for item in log_list
        )
        self.assertTrue(found, "写入的日志未出现在过滤结果中")

    def test_write_and_filter_with_minimal_fields(self):
        """测试写入仅含必填字段的访问日志"""
        minimal_param = {
            "clientIP": "192.168.1.1",
            "method": "GET",
            "path": "/test",
        }
        result = self.access_log_instance.write_access_log(minimal_param)
        self.assertTrue(result, "写入最小字段访问日志失败")

    def test_filter_with_empty_result(self):
        """测试过滤条件不匹配时返回空列表或None"""
        filter_param = {
            "params": {
                "items": {
                    "clientIP": "0.0.0.0|=",
                }
            }
        }
        log_list = self.access_log_instance.filter_access_log(filter_param)
        # 不匹配时可能返回 None 或空列表，两种都接受
        if log_list is not None:
            self.assertEqual(len(log_list), 0, "不匹配条件应返回空列表")

    def test_write_log_with_all_fields(self):
        """测试写入包含全部字段的访问日志"""
        full_param = access_log.mock_access_log_param()
        full_param["timestamp"] = "2025-01-01 12:00:00"
        full_param["userAgent"] = "TestAgent/1.0"
        result = self.access_log_instance.write_access_log(full_param)
        self.assertTrue(result, "写入全字段访问日志失败")

    def test_filter_with_pagination(self):
        """测试带分页参数的过滤"""
        # 先写入多条日志
        for _ in range(3):
            param = access_log.mock_access_log_param()
            self.access_log_instance.write_access_log(param)

        filter_param = {
            "pagination": {
                "pageSize": 5,
                "pageNum": 1,
            },
            "params": {
                "items": {}
            }
        }
        log_list = self.access_log_instance.filter_access_log(filter_param)
        self.assertIsNotNone(log_list, "分页过滤访问日志失败")

    def test_filter_with_time_range(self):
        """测试按时间范围过滤"""
        log_param = access_log.mock_access_log_param()
        log_param["timestamp"] = "2025-06-15 10:30:00"
        self.access_log_instance.write_access_log(log_param)

        filter_param = {
            "params": {
                "items": {
                    "timestamp": "2025-06-01 00:00:00|>=,2025-06-30 23:59:59|<=",
                }
            }
        }
        log_list = self.access_log_instance.filter_access_log(filter_param)
        self.assertIsNotNone(log_list, "时间范围过滤失败")

    def test_write_log_with_special_characters(self):
        """测试写入含特殊字符的访问日志"""
        special_param = access_log.mock_access_log_param()
        special_param["path"] = "/api/v1/test?key=value&lang=zh#section"
        special_param["userAgent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        result = self.access_log_instance.write_access_log(special_param)
        self.assertTrue(result, "写入含特殊字符的访问日志失败")

    def test_filter_by_http_method(self):
        """测试按HTTP方法过滤访问日志"""
        log_param = access_log.mock_access_log_param()
        log_param["method"] = "POST"
        self.access_log_instance.write_access_log(log_param)

        filter_param = {
            "params": {
                "items": {
                    "method": "POST|=",
                }
            }
        }
        log_list = self.access_log_instance.filter_access_log(filter_param)
        self.assertIsNotNone(log_list, "按HTTP方法过滤失败")
        self.assertGreater(len(log_list), 0, "POST日志过滤结果为空")
        self.assertTrue(
            all(item.get("method") == "POST" for item in log_list),
            "过滤结果包含非POST记录",
        )


if __name__ == "__main__":
    unittest.main()
