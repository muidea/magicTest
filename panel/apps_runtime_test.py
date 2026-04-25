import os
import unittest
from typing import Dict, List, Optional, Tuple

from apps_runtime import AppsRuntimeClient
from lifecycle import LifecycleClient
from panel_test_support import PanelE2EBase


class PanelAppsRuntimeTestCase(PanelE2EBase):
    managed_app_uuid = os.getenv("MAGICTEST_PANEL_APP_UUID", "").strip()
    runtime_key = os.getenv("MAGICTEST_APPS_RUNTIME_KEY", "").strip()
    runtime_entity = os.getenv("MAGICTEST_APPS_RUNTIME_ENTITY", "").strip()

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lifecycle_client = LifecycleClient(cls.work_session)
        cls.apps_runtime_client = AppsRuntimeClient(cls.work_session)
        cls._selected_runtime: Optional[Tuple[Dict, Dict]] = None

    def _candidate_runtime_keys(self) -> List[str]:
        candidates: List[str] = []
        if self.runtime_key:
            candidates.append(self.runtime_key)
            return candidates

        running_apps = self.lifecycle_client.fetch_running_applications()
        if running_apps is None:
            raise unittest.SkipTest(
                "未设置 MAGICTEST_APPS_RUNTIME_KEY，且运行中应用自动发现失败，跳过 apps runtime 回归"
            )

        for app in running_apps:
            if self._is_bootstrap_application(app):
                continue

            if self.managed_app_uuid and app.get("uuid") == self.managed_app_uuid:
                name = (app.get("name") or "").strip()
                if name and name not in candidates:
                    candidates.insert(0, name)
                continue

            name = (app.get("name") or "").strip()
            if name and name not in candidates:
                candidates.append(name)

        if not candidates:
            raise unittest.SkipTest("当前未发现可用于 apps runtime 回归的非 bootstrap 运行中应用")

        return candidates

    @staticmethod
    def _is_bootstrap_application(app: Dict) -> bool:
        if not isinstance(app, dict):
            return False
        return (app.get("installSource") or "").strip() == "bootstrap"

    def _pick_runtime_with_entities(self) -> Tuple[Dict, Dict]:
        if self._selected_runtime is not None:
            return self._selected_runtime

        last_metadata: Optional[Dict] = None
        last_runtime: Optional[Dict] = None

        for runtime_key in self._candidate_runtime_keys():
            metadata = self.apps_runtime_client.query_runtime_metadata(runtime_key)
            if metadata is None:
                continue

            application = metadata.get("application") or {}
            entities = metadata.get("entities") or []
            runtime = {"key": runtime_key, "application": application}
            if entities:
                self._selected_runtime = (runtime, metadata)
                return self._selected_runtime

            last_runtime = runtime
            last_metadata = metadata

        if last_metadata is not None and last_runtime is not None:
            self._selected_runtime = (last_runtime, last_metadata)
            return self._selected_runtime

        raise unittest.SkipTest("当前未发现可访问的运行期应用元数据，跳过 apps runtime 回归")

    def _pick_entity_with_list_api(self, metadata: Dict) -> Dict:
        entities = metadata.get("entities") or []
        if self.runtime_entity:
            for entity in entities:
                entity_identity = entity.get("entity") or {}
                if entity_identity.get("name") == self.runtime_entity:
                    return entity
            raise unittest.SkipTest(f"未找到指定实体 {self.runtime_entity}，跳过实体列表回归")

        for entity in entities:
            api = entity.get("api") or {}
            if api.get("list"):
                return entity

        raise unittest.SkipTest("当前运行期应用未返回带列表接口的实体，跳过实体列表回归")

    def test_query_installed_application_runtime_metadata(self):
        runtime, metadata = self._pick_runtime_with_entities()
        application = metadata.get("application") or {}
        entities = metadata.get("entities") or []

        self.assertEqual(application.get("key"), runtime["key"], f"运行期应用 key 不匹配: {metadata}")
        self.assertTrue(application.get("name"), f"运行期应用名称为空: {metadata}")
        self.assertGreater(len(entities), 0, f"运行期应用未返回实体定义: {metadata}")

        entity_with_api = None
        for entity in entities:
            entity_identity = entity.get("entity") or {}
            api = entity.get("api") or {}
            if api.get("list") and api.get("detail") and entity_identity.get("name"):
                entity_with_api = entity
                break

        self.assertIsNotNone(entity_with_api, f"运行期实体未自动补齐 CRUD API: {metadata}")

        entity_identity = entity_with_api.get("entity") or {}
        api = entity_with_api.get("api") or {}
        expected_suffix = f"application={runtime['key']}&entity={entity_identity.get('name')}"
        self.assertIn("/api/v1/apps/entity/values/", api.get("list", ""), f"实体列表 API 不正确: {api}")
        self.assertIn(expected_suffix, api.get("list", ""), f"实体列表 API 未绑定运行期 application/entity: {api}")
        self.assertIn(expected_suffix, api.get("detail", ""), f"实体详情 API 未绑定运行期 application/entity: {api}")

    def test_runtime_entity_list_api_is_available(self):
        runtime, metadata = self._pick_runtime_with_entities()
        entity = self._pick_entity_with_list_api(metadata)
        api = entity.get("api") or {}

        values = self.apps_runtime_client.query_entity_list(api.get("list", ""))
        self.assertIsNotNone(values, f"运行期实体列表访问失败: runtime={runtime}, entity={entity}")
        self.assertIsInstance(values, list, f"运行期实体列表返回结构错误: runtime={runtime}, entity={entity}, values={values}")


if __name__ == "__main__":
    unittest.main()
