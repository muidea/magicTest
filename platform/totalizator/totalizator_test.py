"""Totalizator 测试用例 — 覆盖 register / unregister / filter / summary / refresh 及边界异常场景"""

import logging
import os
import unittest
import warnings

from session import session
from totalizator import totalizator


logger = logging.getLogger(__name__)


class TotalizatorTestCase(unittest.TestCase):
    """Totalizator 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    def setUp(self):
        warnings.simplefilter("ignore", ResourceWarning)
        self.work_session = session.MagicSession(self.server_url, self.namespace)
        self.totalizator_instance = totalizator.Totalizator(self.work_session)
        self._registered_names = []

    def tearDown(self):
        """清理注册的总计器"""
        for name in self._registered_names:
            try:
                self.totalizator_instance.unregister_totalizator({"name": name})
            except Exception as err:
                logger.warning("清理总计器 %s 失败: %s", name, err)
        self._registered_names.clear()

    def _register_totalizator(self, name=None, scope=None, metric=None):
        """辅助方法：注册总计器并记录清理"""
        param = totalizator.mock_totalizator_param()
        if name:
            param["name"] = name
        if scope:
            param["scope"] = scope
        if metric:
            param["metric"] = metric

        result = self.totalizator_instance.register_totalizator(param)
        self.assertTrue(result, "注册总计器失败")
        self._registered_names.append(param["name"])
        return param

    def test_register_totalizator(self):
        """测试注册总计器（基本流程）"""
        param = self._register_totalizator()
        # 注册成功后过滤验证
        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(param["name"]),
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        self.assertIsNotNone(tz_list, "过滤总计器失败")
        self.assertGreater(len(tz_list), 0, "注册后过滤结果为空")

    def test_filter_totalizator(self):
        """测试过滤总计器"""
        param = self._register_totalizator()

        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(param["name"]),
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        self.assertIsNotNone(tz_list, "过滤总计器失败")
        self.assertGreater(len(tz_list), 0, "过滤结果为空")

        found = any(
            item.get("name") == param["name"] for item in tz_list
        )
        self.assertTrue(found, "注册的总计器未出现在过滤结果中")

    def test_query_totalizator_summary(self):
        """测试查询总计器摘要"""
        self._register_totalizator()

        summary_param = totalizator.mock_totalizator_summary_param()
        summary = self.totalizator_instance.query_totalizator_summary(summary_param)
        self.assertIsNotNone(summary, "查询总计器摘要失败")

    def test_refresh_totalizator(self):
        """测试刷新总计器"""
        param = self._register_totalizator()

        refresh_param = {
            "name": param["name"],
            "metric": param["metric"],
            "value": totalizator.mock.int(1, 100),
        }
        result = self.totalizator_instance.refresh_totalizator(refresh_param)
        self.assertTrue(result, "刷新总计器失败")

    def test_unregister_totalizator(self):
        """测试取消注册总计器"""
        param = self._register_totalizator()

        result = self.totalizator_instance.unregister_totalizator(param)
        self.assertTrue(result, "取消注册总计器失败")
        self._registered_names.remove(param["name"])

        # 取消注册后过滤应查不到
        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(param["name"]),
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        if tz_list is not None:
            found = any(
                item.get("name") == param["name"] for item in tz_list
            )
            self.assertFalse(found, "取消注册后总计器仍出现在过滤结果中")

    def test_filter_with_empty_result(self):
        """测试过滤不存在总计器"""
        filter_param = {
            "params": {
                "items": {
                    "name": "nonexistent_totalizator_xyz|=",
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        if tz_list is not None:
            self.assertEqual(len(tz_list), 0, "不存在的总计器过滤应返回空列表")

    def test_register_duplicate_name(self):
        """测试重复注册同名总计器"""
        param = self._register_totalizator()
        # 同名注册应成功（覆盖或幂等）
        result = self.totalizator_instance.register_totalizator(param)
        self.assertTrue(result, "重复注册同名总计器应幂等返回True")

    def test_full_lifecycle(self):
        """测试总计器完整生命周期：注册 → 过滤 → 刷新 → 摘要 → 取消注册"""
        # 注册
        param = self._register_totalizator()

        # 过滤验证
        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(param["name"]),
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        self.assertIsNotNone(tz_list, "过滤总计器失败")
        self.assertGreater(len(tz_list), 0, "过滤结果为空")

        # 刷新
        refresh_param = {
            "name": param["name"],
            "metric": param["metric"],
            "value": 50,
        }
        refresh_ok = self.totalizator_instance.refresh_totalizator(refresh_param)
        self.assertTrue(refresh_ok, "刷新总计器失败")

        # 摘要
        summary_param = totalizator.mock_totalizator_summary_param()
        summary = self.totalizator_instance.query_totalizator_summary(summary_param)
        self.assertIsNotNone(summary, "查询总计器摘要失败")

        # 取消注册
        unreg_ok = self.totalizator_instance.unregister_totalizator(param)
        self.assertTrue(unreg_ok, "取消注册总计器失败")
        self._registered_names.remove(param["name"])

    def test_register_with_custom_metric(self):
        """测试注册自定义指标的总计器"""
        param = self._register_totalizator(
            name="test_metric_tz",
            scope="test_scope",
            metric="custom_metric",
        )
        # 验证过滤返回包含自定义指标
        filter_param = {
            "params": {
                "items": {
                    "name": "test_metric_tz|=",
                }
            }
        }
        tz_list = self.totalizator_instance.filter_totalizator(filter_param)
        self.assertIsNotNone(tz_list, "过滤自定义总计器失败")
        if tz_list:
            found = any(
                item.get("name") == "test_metric_tz" for item in tz_list
            )
            self.assertTrue(found, "自定义总计器未出现在过滤结果中")

    def test_unregister_nonexistent(self):
        """测试取消注册不存在的总计器"""
        result = self.totalizator_instance.unregister_totalizator(
            {"name": "nonexistent_cleanup"}
        )
        # 行为取决于实现，幂等返回True或None均可
        self.assertIn(result, (True, None),
                       "取消注册不存在总计器应返回True或None")


if __name__ == "__main__":
    unittest.main()
