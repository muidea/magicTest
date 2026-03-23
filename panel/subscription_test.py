import os
import time
import unittest

from panel_test_support import PanelE2EBase
from subscription import SubscriptionClient


ENABLE_STATUS = 2
DISABLE_STATUS = 1


class PanelSubscriptionTestCase(PanelE2EBase):
    subscription_id = int(os.getenv("MAGICTEST_PANEL_SUBSCRIPTION_ID", "0") or "0")
    mutable_subscription_id = int(os.getenv("MAGICTEST_PANEL_MUTABLE_SUBSCRIPTION_ID", "0") or "0")
    allow_status_mutation = os.getenv("MAGICTEST_PANEL_ALLOW_STATUS_MUTATION", "").lower() in ("1", "true", "yes")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.subscription_client = SubscriptionClient(cls.work_session)

    def test_filter_subscriptions_smoke(self):
        subscription_list = self.subscription_client.filter_subscriptions()
        self.assertIsNotNone(subscription_list, "过滤订阅失败")
        self.assertIsInstance(subscription_list, list, "订阅列表结果不是列表")

    def test_query_configured_subscription(self):
        if self.subscription_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_SUBSCRIPTION_ID，跳过订阅详情回归")

        subscription = self.subscription_client.query_subscription(self.subscription_id)
        self.assertIsNotNone(subscription, "查询订阅失败")
        self.assertIn("subscriber", subscription, "订阅结果缺少 subscriber")
        self.assertIn("hostBy", subscription, "订阅结果缺少 hostBy")

    def test_create_delete_endpoint_roundtrip(self):
        if self.mutable_subscription_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_MUTABLE_SUBSCRIPTION_ID，跳过 endpoint 回归")

        endpoint_name = f"e2e-panel-{int(time.time() * 1000)}"
        created = self.subscription_client.create_endpoint(self.mutable_subscription_id, endpoint_name)
        self.assertIsNotNone(created, "创建 endpoint 失败")
        self.assertEqual(created.get("endpoint"), endpoint_name, "创建后的 endpoint 名称不匹配")

        queried = self.subscription_client.query_endpoint(self.mutable_subscription_id, endpoint_name)
        self.assertIsNotNone(queried, "查询 endpoint 失败")
        self.assertEqual(queried.get("endpoint"), endpoint_name, "查询后的 endpoint 名称不匹配")

        deleted = self.subscription_client.delete_endpoint(self.mutable_subscription_id, endpoint_name)
        self.assertIsNotNone(deleted, "删除 endpoint 失败")
        self.assertEqual(deleted.get("endpoint"), endpoint_name, "删除后的 endpoint 名称不匹配")

        missing = self.subscription_client.query_endpoint(self.mutable_subscription_id, endpoint_name)
        self.assertIsNone(missing, "删除后的 endpoint 查询应失败")

    def test_enable_disable_roundtrip(self):
        if self.mutable_subscription_id <= 0 or not self.allow_status_mutation:
            raise unittest.SkipTest("未显式允许状态变更回归，跳过 enable/disable roundtrip")

        subscription = self.subscription_client.query_subscription(self.mutable_subscription_id)
        self.assertIsNotNone(subscription, "查询订阅失败")
        original_status = subscription.get("status")

        try:
            disabled = self.subscription_client.disable_subscription(self.mutable_subscription_id)
            self.assertIsNotNone(disabled, "停用订阅失败")
            self.assertEqual(disabled.get("status"), DISABLE_STATUS, "停用后状态不正确")

            enabled = self.subscription_client.enable_subscription(self.mutable_subscription_id)
            self.assertIsNotNone(enabled, "启用订阅失败")
            self.assertEqual(enabled.get("status"), ENABLE_STATUS, "启用后状态不正确")
        finally:
            if original_status == ENABLE_STATUS:
                self.subscription_client.enable_subscription(self.mutable_subscription_id)
            elif original_status == DISABLE_STATUS:
                self.subscription_client.disable_subscription(self.mutable_subscription_id)
