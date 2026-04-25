import base64
import json
import os
import unittest
from typing import Any, Dict, List, Optional
from uuid import uuid4

from apps_runtime import AppsRuntimeClient
from panel_test_support import PanelE2EBase
from portal_service import PortalServiceClient
from service_access import ServiceAccessClient, extract_error_message, extract_first_entity_id
from service_registry import ServiceRegistryClient
from subscription import SubscriptionClient


ENABLE_STATUS = 2
AUDITING_STATUS = 5
PUBLISHED_STATUS = 2


class PanelServiceRoundtripTestCase(PanelE2EBase):
    service_key = os.getenv("MAGICTEST_PANEL_SERVICE_KEY", "user_service").strip()
    service_key_explicit = bool(os.getenv("MAGICTEST_PANEL_SERVICE_KEY", "").strip())
    query_capability_key = os.getenv("MAGICTEST_PANEL_QUERY_CAPABILITY_KEY", "user_query").strip()
    get_capability_key = os.getenv("MAGICTEST_PANEL_GET_CAPABILITY_KEY", "user_get").strip()
    create_capability_key = os.getenv("MAGICTEST_PANEL_CREATE_CAPABILITY_KEY", "user_create").strip()
    update_capability_key = os.getenv("MAGICTEST_PANEL_UPDATE_CAPABILITY_KEY", "user_update").strip()
    delete_capability_key = os.getenv("MAGICTEST_PANEL_DELETE_CAPABILITY_KEY", "user_delete").strip()
    get_entity_id = os.getenv("MAGICTEST_PANEL_GET_ENTITY_ID", "").strip()
    lease_term = int(os.getenv("MAGICTEST_PANEL_SERVICE_LEASE_TERM", "30") or "30")
    create_payload_raw = os.getenv("MAGICTEST_PANEL_CREATE_PAYLOAD_JSON", "").strip()
    update_payload_raw = os.getenv("MAGICTEST_PANEL_UPDATE_PAYLOAD_JSON", "").strip()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registry_client = ServiceRegistryClient(cls.work_session)
        cls.portal_service_client = PortalServiceClient(cls.work_session)
        cls.subscription_client = SubscriptionClient(cls.work_session)
        cls.service_access_client = ServiceAccessClient(cls.work_session)
        cls.apps_runtime_client = AppsRuntimeClient(cls.work_session)

    def _current_subscriber_id(self) -> Optional[int]:
        token = getattr(self.work_session, "session_token", None)
        if not token:
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        try:
            claims = base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8")
            payload_obj = json.loads(claims)
        except Exception:
            return None

        entity = payload_obj.get("X-Mp-Auth-Entity") or {}
        subscriber_id = entity.get("id")
        if isinstance(subscriber_id, int) and subscriber_id > 0:
            return subscriber_id
        return None

    def _find_service_by_key(self, service_key: str) -> Optional[Dict]:
        values = self.registry_client.filter_services({"key": service_key})
        self.assertIsNotNone(values, "过滤服务定义失败")
        for item in values or []:
            if item.get("key") == service_key:
                return item
        return None

    def _require_service_by_key(self, service_key: str) -> Dict:
        service = self._find_service_by_key(service_key)
        if service is not None:
            return service
        if self.service_key_explicit:
            self.fail(f"未找到显式指定的服务定义: {service_key}")
        raise unittest.SkipTest(
            f"当前环境未发现默认服务 {service_key}，请显式设置 MAGICTEST_PANEL_SERVICE_KEY 及对应 capability key"
        )

    def _parse_json_payload(self, raw: str, env_name: str) -> Optional[Dict]:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as err:
            self.fail(f"{env_name} 不是合法 JSON: {err}")
        if not isinstance(parsed, dict):
            self.fail(f"{env_name} 必须是 JSON object")
        return parsed

    def _parse_service_options(self, service: Dict) -> Dict[str, Any]:
        raw = service.get("options")
        if not raw or not isinstance(raw, str):
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _resolve_runtime_entity_metadata(self, service: Dict) -> Optional[Dict[str, Any]]:
        options = self._parse_service_options(service)
        runtime_key = (options.get("runtimeApplicationName") or options.get("runtimeApplicationUUID") or "").strip()
        runtime_entity_name = (options.get("runtimeEntityName") or "").strip()
        if not runtime_key or not runtime_entity_name:
            return None
        runtime_metadata = self.apps_runtime_client.query_runtime_metadata(runtime_key)
        if not runtime_metadata:
            return None
        for entity in runtime_metadata.get("entities") or []:
            identity = entity.get("entity") or {}
            if identity.get("name") == runtime_entity_name:
                return entity
        return None

    @staticmethod
    def _sample_value_for_field(field: Dict[str, Any], suffix: str) -> Any:
        field_type = (field.get("type") or "").lower()
        name = field.get("name") or "value"
        if field_type in ("string", "text"):
            return f"e2e_{name}_{suffix}"
        if field_type in ("integer", "int", "long", "number"):
            return 1
        if field_type in ("float", "double", "decimal"):
            return 1.0
        if field_type in ("boolean", "bool"):
            return True
        return None

    def _build_runtime_payloads(self, runtime_entity: Optional[Dict[str, Any]]) -> Optional[tuple[Dict[str, Any], Dict[str, Any]]]:
        if not runtime_entity:
            return None
        fields = runtime_entity.get("fields") or []
        create_field_names = []
        form = runtime_entity.get("form") or {}
        for tab in form.get("tabs") or []:
            for field_name in tab.get("fields") or []:
                if field_name not in create_field_names:
                    create_field_names.append(field_name)
        if not create_field_names:
            create_field_names = [
                field.get("name")
                for field in fields
                if isinstance(field, dict)
                and field.get("name")
                and not field.get("hiddenInCreate")
                and not field.get("readonly")
            ]
        create_payload: Dict[str, Any] = {}
        update_payload: Dict[str, Any] = {}
        suffix = uuid4().hex[:8]
        for field in fields:
            if not isinstance(field, dict):
                continue
            field_name = field.get("name")
            if not field_name or field_name not in create_field_names:
                continue
            sample = self._sample_value_for_field(field, suffix)
            if sample is None:
                continue
            create_payload[field_name] = sample
            if isinstance(sample, str):
                update_payload[field_name] = f"{sample}_updated"
            elif isinstance(sample, bool):
                update_payload[field_name] = not sample
            else:
                update_payload[field_name] = sample
        if not create_payload:
            return None
        return create_payload, update_payload or dict(create_payload)

    def _extract_entity_id(self, payload: Dict) -> Optional[int]:
        if not isinstance(payload, dict):
            return None

        direct_id = payload.get("id")
        if isinstance(direct_id, int):
            return direct_id

        value = payload.get("value")
        if isinstance(value, dict):
            value_id = value.get("id")
            if isinstance(value_id, int):
                return value_id

        return None

    def _find_publication_by_service(self, service_id: int) -> Optional[Dict]:
        values = self.registry_client.filter_publications()
        self.assertIsNotNone(values, "过滤服务发布失败")
        for item in values or []:
            service = item.get("service") or {}
            if service.get("id") == service_id and item.get("status") == PUBLISHED_STATUS:
                return item
        return None

    def _find_latest_subscription_by_service(self, service_id: int, subscriber_id: Optional[int]) -> Optional[Dict]:
        filter_param = {"service": service_id}
        if subscriber_id:
            filter_param["subscriber"] = subscriber_id
        values = self.subscription_client.filter_subscriptions(filter_param)
        self.assertIsNotNone(values, "过滤订阅失败")

        matched: List[Dict] = []
        for item in values or []:
            service = item.get("service") or {}
            if service.get("id") == service_id:
                if subscriber_id:
                    subscriber = item.get("subscriber")
                    current_subscriber_id = subscriber.get("id") if isinstance(subscriber, dict) else subscriber
                    if current_subscriber_id != subscriber_id:
                        continue
                matched.append(item)

        if not matched:
            return None

        matched.sort(key=lambda item: item.get("updateTime") or item.get("createTime") or 0, reverse=True)
        return matched[0]

    def test_service_definition_subscription_and_endpoint_gateway_roundtrip(self):
        if not self.service_key:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_SERVICE_KEY，跳过 service roundtrip 回归")
        if not getattr(self.work_session, "session_token", None):
            raise unittest.SkipTest("当前未使用账号态会话，跳过 panel/portal 主流程 roundtrip")

        service = self._require_service_by_key(self.service_key)
        service_id = service["id"]
        self.assertEqual(service.get("key"), self.service_key, "服务 key 不匹配")
        self.assertEqual(service.get("name"), self.service_key, "服务 name 应与 key 对齐")
        self.assertTrue(service.get("address"), "服务 address 不应为空")
        subscriber_id = self._current_subscriber_id()
        self.assertIsNotNone(subscriber_id, "未能从当前登录会话解析 subscriber id")

        publication = self._find_publication_by_service(service_id)
        self.assertIsNotNone(publication, f"未找到已发布服务: {self.service_key}")

        portal_services = self.portal_service_client.filter_services()
        self.assertIsNotNone(portal_services, "过滤门户服务失败")
        portal_service = next((item for item in (portal_services or []) if item.get("id") == service_id), None)
        self.assertIsNotNone(portal_service, "已发布服务应出现在 portal 服务列表中")

        panel_debug_meta = self.registry_client.query_service_debug_metadata(service_id)
        self.assertIsNotNone(panel_debug_meta, "查询 panel 服务调试元数据失败")
        self.assertTrue(panel_debug_meta.get("operations"), "panel 调试元数据缺少 operations")
        operation_keys = {item.get("key") for item in (panel_debug_meta.get("operations") or []) if isinstance(item, dict)}

        panel_query_status, panel_query_payload = self.service_access_client.get_service(
            self.service_key,
            self.query_capability_key,
        )
        self.assertEqual(
            panel_query_status,
            200,
            f"panel 账号态 query 调试失败: status={panel_query_status}, payload={panel_query_payload}",
        )
        self.assertNotIn("error", panel_query_payload, f"panel 账号态访问不应返回 error: {panel_query_payload}")

        created_subscription = False
        subscription = self._find_latest_subscription_by_service(service_id, subscriber_id)
        if subscription is None:
            subscribed = self.portal_service_client.create_subscription(service_id, self.lease_term)
            self.assertIsNotNone(subscribed, "创建服务订阅失败")
            created_subscription = True

        subscription = self._find_latest_subscription_by_service(service_id, subscriber_id)
        self.assertIsNotNone(subscription, "创建订阅后未找到对应订阅记录")

        try:
            if subscription.get("status") == AUDITING_STATUS:
                approved = self.subscription_client.approve_subscription(subscription["id"])
                self.assertIsNotNone(approved, "审批订阅失败")
                subscription = self._find_latest_subscription_by_service(service_id, subscriber_id)
                self.assertIsNotNone(subscription, "审批后未找到订阅记录")

            self.assertEqual(subscription.get("status"), ENABLE_STATUS, f"订阅未进入启用状态: {subscription}")

            portal_debug_meta = self.portal_service_client.query_service_debug_metadata(service_id)
            self.assertIsNotNone(portal_debug_meta, "查询 portal 服务调试元数据失败")
            self.assertTrue(portal_debug_meta.get("operations"), "portal 调试元数据缺少 operations")

            endpoint_list = self.portal_service_client.filter_endpoints(
                {"service": service_id, "_pageNumber": 1, "_pageSize": 10000}
            )
            self.assertIsNotNone(endpoint_list, "查询门户服务访问凭证失败")
            self.assertGreater(len(endpoint_list or []), 0, "订阅审批通过后应自动签发默认访问凭证")
            endpoint_item = endpoint_list[0]
            self.assertTrue(endpoint_item.get("endpoint"), "访问凭证缺少 endpoint")
            self.assertTrue(endpoint_item.get("authToken"), "访问凭证缺少 authToken")

            endpoint_session = self.work_session.new_session()
            endpoint_session.bind_auth_secret(
                endpoint_item["endpoint"],
                endpoint_item["authToken"],
            )
            endpoint_access_client = ServiceAccessClient(endpoint_session)

            status_code, payload = endpoint_access_client.get_service(self.service_key)
            self.assertEqual(
                status_code,
                400,
                f"多能力项服务未带 capability key 时应返回 400，实际为 {status_code}: {payload}",
            )
            self.assertIn(
                "service capability key is missing",
                extract_error_message(payload),
                f"错误消息不符合预期: {payload}",
            )

            query_status, query_payload = endpoint_access_client.get_service(
                self.service_key,
                self.query_capability_key,
            )
            self.assertEqual(
                query_status,
                200,
                f"query 能力访问失败: status={query_status}, payload={query_payload}",
            )
            self.assertNotIn("error", query_payload, f"query 能力访问不应返回 error: {query_payload}")

            entity_id = self.get_entity_id
            if not entity_id:
                resolved_entity_id = extract_first_entity_id(query_payload)
                if resolved_entity_id is not None:
                    entity_id = str(resolved_entity_id)

            runtime_entity = self._resolve_runtime_entity_metadata(service)
            generated_payloads = self._build_runtime_payloads(runtime_entity)

            if entity_id:
                get_status, get_payload = endpoint_access_client.get_service(
                    self.service_key,
                    self.get_capability_key,
                    entity_id,
                )
                self.assertEqual(
                    get_status,
                    200,
                    f"get 能力访问失败: status={get_status}, payload={get_payload}",
                )
                self.assertNotIn("error", get_payload, f"get 能力访问不应返回 error: {get_payload}")

            create_payload = self._parse_json_payload(
                self.create_payload_raw,
                "MAGICTEST_PANEL_CREATE_PAYLOAD_JSON",
            )
            update_payload = self._parse_json_payload(
                self.update_payload_raw,
                "MAGICTEST_PANEL_UPDATE_PAYLOAD_JSON",
            )
            if create_payload is None and generated_payloads is not None:
                create_payload = generated_payloads[0]
            if update_payload is None and generated_payloads is not None:
                update_payload = generated_payloads[1]
            should_run_crud_roundtrip = (
                create_payload is not None
                and update_payload is not None
                and self.create_capability_key
                and self.update_capability_key
            )
            if should_run_crud_roundtrip:
                missing_keys = [
                    capability_key
                    for capability_key in [
                        self.create_capability_key,
                        self.update_capability_key,
                    ]
                    if capability_key not in operation_keys
                ]
                self.assertFalse(
                    missing_keys,
                    f"调试元数据中缺少 CRUD 能力项: {missing_keys}, operations={sorted(operation_keys)}",
                )

                create_status, create_result = endpoint_access_client.create_service(
                    self.service_key,
                    self.create_capability_key,
                    create_payload,
                )
                self.assertEqual(
                    create_status,
                    200,
                    f"create 能力访问失败: status={create_status}, payload={create_result}",
                )
                self.assertNotIn("error", create_result, f"create 能力访问不应返回 error: {create_result}")

                created_entity_id = self._extract_entity_id(create_result)
                self.assertIsNotNone(
                    created_entity_id,
                    f"create 返回中未找到实体 ID: {create_result}",
                )

                get_status, get_payload = endpoint_access_client.get_service(
                    self.service_key,
                    self.get_capability_key,
                    created_entity_id,
                )
                self.assertEqual(
                    get_status,
                    200,
                    f"create 后 get 能力访问失败: status={get_status}, payload={get_payload}",
                )
                self.assertNotIn("error", get_payload, f"create 后 get 不应返回 error: {get_payload}")

                update_status, update_result = endpoint_access_client.update_service(
                    self.service_key,
                    self.update_capability_key,
                    created_entity_id,
                    update_payload,
                )
                self.assertEqual(
                    update_status,
                    200,
                    f"update 能力访问失败: status={update_status}, payload={update_result}",
                )
                self.assertNotIn("error", update_result, f"update 能力访问不应返回 error: {update_result}")

                if self.delete_capability_key and self.delete_capability_key in operation_keys:
                    delete_status, delete_result = endpoint_access_client.delete_service(
                        self.service_key,
                        self.delete_capability_key,
                        created_entity_id,
                    )
                    self.assertEqual(
                        delete_status,
                        200,
                        f"delete 能力访问失败: status={delete_status}, payload={delete_result}",
                    )
                    self.assertNotIn("error", delete_result, f"delete 能力访问不应返回 error: {delete_result}")
                elif runtime_entity is not None:
                    delete_api = ((runtime_entity.get("api") or {}).get("delete") or "").strip()
                    self.assertTrue(delete_api, f"运行期实体缺少 delete API，无法清理测试数据: {runtime_entity}")
                    deleted, delete_result = self.apps_runtime_client.delete_entity_value(delete_api, created_entity_id)
                    self.assertTrue(
                        deleted,
                        f"service 未开放 delete，且运行期实体清理失败: id={created_entity_id}, result={delete_result}",
                    )
        finally:
            if created_subscription:
                deleted_subscription = self.portal_service_client.delete_subscription(service_id)
                self.assertIsNotNone(deleted_subscription, "删除测试创建的服务订阅失败")
