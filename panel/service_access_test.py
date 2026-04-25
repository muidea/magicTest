import os
import unittest

from panel_test_support import PanelE2EBase
from service_registry import ServiceRegistryClient
from service_access import ServiceAccessClient, extract_error_message, extract_first_entity_id


class PanelServiceAccessTestCase(PanelE2EBase):
    service_key = os.getenv("MAGICTEST_PANEL_SERVICE_KEY", "user_service").strip()
    service_key_explicit = bool(os.getenv("MAGICTEST_PANEL_SERVICE_KEY", "").strip())
    query_capability_key = os.getenv("MAGICTEST_PANEL_QUERY_CAPABILITY_KEY", "user_query")
    get_capability_key = os.getenv("MAGICTEST_PANEL_GET_CAPABILITY_KEY", "user_get")
    get_entity_id = os.getenv("MAGICTEST_PANEL_GET_ENTITY_ID", "").strip()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.service_access_client = ServiceAccessClient(cls.work_session)
        cls.service_registry_client = ServiceRegistryClient(cls.work_session)

    def _require_service_definition(self):
        if not self.service_key:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_SERVICE_KEY，跳过服务访问回归")

        services = self.service_registry_client.filter_services({"key": self.service_key})
        self.assertIsNotNone(services, "过滤服务定义失败")
        for item in services or []:
            if item.get("key") == self.service_key:
                return item

        if self.service_key_explicit:
            self.fail(f"未找到显式指定的服务定义: {self.service_key}")
        raise unittest.SkipTest(
            f"当前环境未发现默认服务 {self.service_key}，请显式设置 MAGICTEST_PANEL_SERVICE_KEY/MAGICTEST_PANEL_QUERY_CAPABILITY_KEY"
        )

    def test_gateway_requires_capability_key_for_multi_capability_service(self):
        self._require_service_definition()

        status_code, payload = self.service_access_client.get_service(self.service_key)
        self.assertEqual(status_code, 400, f"未携带 capability key 时应返回 400，实际为 {status_code}: {payload}")
        self.assertIn(
            "service capability key is missing",
            extract_error_message(payload),
            f"错误消息不符合预期: {payload}",
        )

    def test_gateway_query_capability_access(self):
        if not self.query_capability_key:
            raise unittest.SkipTest("未设置 service/capability key，跳过 query 能力访问校验")
        self._require_service_definition()

        status_code, payload = self.service_access_client.get_service(
            self.service_key,
            self.query_capability_key,
        )
        self.assertEqual(status_code, 200, f"query 能力访问失败: status={status_code}, payload={payload}")
        self.assertNotIn("error", payload, f"query 能力访问不应返回 error: {payload}")

    def test_gateway_get_capability_access_with_entity_id(self):
        if not self.get_capability_key:
            raise unittest.SkipTest("未设置 service/get capability key，跳过 get 能力访问校验")
        self._require_service_definition()
        entity_id = self.get_entity_id
        if not entity_id:
            if not self.query_capability_key:
                raise unittest.SkipTest("未设置 query capability key，且无法自动推导 entity id，跳过 get 能力访问校验")
            query_status, query_payload = self.service_access_client.get_service(
                self.service_key,
                self.query_capability_key,
            )
            if query_status != 200:
                raise unittest.SkipTest(
                    f"query 能力访问失败，无法自动推导 entity id: status={query_status}, payload={query_payload}"
                )
            resolved_entity_id = extract_first_entity_id(query_payload)
            if resolved_entity_id is None:
                raise unittest.SkipTest("query 结果为空，未能自动推导 entity id，跳过 get 能力访问校验")
            entity_id = str(resolved_entity_id)

        status_code, payload = self.service_access_client.get_service(
            self.service_key,
            self.get_capability_key,
            entity_id,
        )
        self.assertEqual(status_code, 200, f"get 能力访问失败: status={status_code}, payload={payload}")
        self.assertNotIn("error", payload, f"get 能力访问不应返回 error: {payload}")
