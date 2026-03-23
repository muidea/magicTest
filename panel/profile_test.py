import unittest

from panel_test_support import PanelE2EBase
from profile import ProfileClient


class PanelProfileTestCase(PanelE2EBase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.profile_client = ProfileClient(cls.work_session)

    def test_get_system_notifications_smoke(self):
        notifications = self.profile_client.get_system_notifications()
        self.assertIsNotNone(notifications, "查询系统通知失败")
        self.assertIsInstance(notifications, list, "系统通知结果不是列表")

    def test_get_profile_smoke(self):
        profile = self.profile_client.get_profile()
        self.assertIsNotNone(profile, "查询 profile 失败")
        self.assertIn("summary", profile, "profile 缺少 summary")
        self.assertIn("notification", profile, "profile 缺少 notification")
        self.assertIsInstance(profile["summary"], list, "profile.summary 不是列表")
        self.assertIsInstance(profile["notification"], list, "profile.notification 不是列表")

    def test_profile_notifications_shape(self):
        profile = self.profile_client.get_profile()
        self.assertIsNotNone(profile, "查询 profile 失败")
        for notification in profile.get("notification", []):
            self.assertIn("id", notification, "通知缺少 id")
            self.assertIn("title", notification, "通知缺少 title")
            self.assertIn("content", notification, "通知缺少 content")

    def test_profile_summary_shape(self):
        profile = self.profile_client.get_profile()
        self.assertIsNotNone(profile, "查询 profile 失败")
        for summary in profile.get("summary", []):
            self.assertIn("name", summary, "summary 缺少 name")
            self.assertIn("value", summary, "summary 缺少 value")
            self.assertIn("unit", summary, "summary 缺少 unit")
