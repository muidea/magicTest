import os
import unittest

from panel_test_support import PanelE2EBase
from lifecycle import LifecycleClient


RUNNING_STATUS = 3
STOPPED_STATUS = 4


class PanelApplicationLifecycleTestCase(PanelE2EBase):
    managed_app_uuid = os.getenv("MAGICTEST_PANEL_APP_UUID", "")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lifecycle_client = LifecycleClient(cls.work_session)

    def _find_running_application(self, app_uuid):
        app_list = self.lifecycle_client.fetch_running_applications()
        self.assertIsNotNone(app_list, "查询运行中应用失败")
        for app_item in app_list:
            if app_item.get("uuid") == app_uuid:
                return app_item
        return None

    def test_fetch_running_applications(self):
        app_list = self.lifecycle_client.fetch_running_applications()
        self.assertIsNotNone(app_list, "查询运行中应用失败")
        self.assertIsInstance(app_list, list, "运行中应用结果不是列表")

    def test_start_stop_configured_application(self):
        if not self.managed_app_uuid:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APP_UUID，跳过 start/stop 回归")

        original = self._find_running_application(self.managed_app_uuid)
        if original is None:
            raise unittest.SkipTest("目标应用未安装或当前 namespace 不可见，跳过 start/stop 回归")

        original_status = original.get("status")

        if original_status == RUNNING_STATUS:
            stopped = self.lifecycle_client.stop_application(self.managed_app_uuid)
            self.assertIsNotNone(stopped, "停止应用失败")
            self.assertEqual(stopped.get("status"), STOPPED_STATUS, "停止后状态不正确")

            restarted = self.lifecycle_client.start_application(self.managed_app_uuid)
            self.assertIsNotNone(restarted, "重启应用失败")
            self.assertEqual(restarted.get("status"), RUNNING_STATUS, "重启后状态不正确")
            return

        started = self.lifecycle_client.start_application(self.managed_app_uuid)
        self.assertIsNotNone(started, "启动应用失败")
        self.assertEqual(started.get("status"), RUNNING_STATUS, "启动后状态不正确")

        stopped = self.lifecycle_client.stop_application(self.managed_app_uuid)
        self.assertIsNotNone(stopped, "停止应用失败")
        self.assertEqual(stopped.get("status"), STOPPED_STATUS, "恢复停止状态失败")
