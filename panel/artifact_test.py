import os
import unittest

from artifact import (
    ArtifactClient,
    mock_application_artifact_param,
    mock_entity_artifact_param,
)
from panel_test_support import PanelE2EBase


class PanelArtifactTestCase(PanelE2EBase):
    application_artifact_id = int(os.getenv("MAGICTEST_PANEL_APPLICATION_ARTIFACT_ID", "0") or "0")
    entity_artifact_id = int(os.getenv("MAGICTEST_PANEL_ENTITY_ARTIFACT_ID", "0") or "0")
    allow_artifact_mutation = os.getenv("MAGICTEST_PANEL_ALLOW_ARTIFACT_MUTATION", "").lower() in ("1", "true", "yes")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.artifact_client = ArtifactClient(cls.work_session)

    def test_filter_entities_smoke(self):
        entity_list = self.artifact_client.filter_entities()
        self.assertIsNotNone(entity_list, "过滤 entity artifact 失败")
        self.assertIsInstance(entity_list, list, "entity artifact 结果不是列表")

    def test_query_configured_application_artifact(self):
        if self.application_artifact_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_ARTIFACT_ID，跳过 application artifact 查询")

        artifact = self.artifact_client.query_application_artifact(self.application_artifact_id)
        self.assertIsNotNone(artifact, "查询 application artifact 失败")
        self.assertEqual(artifact.get("id"), self.application_artifact_id, "application artifact id 不匹配")

    def test_query_configured_entity_artifact(self):
        if self.entity_artifact_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_ENTITY_ARTIFACT_ID，跳过 entity artifact 查询")

        entity = self.artifact_client.query_entity(self.entity_artifact_id)
        self.assertIsNotNone(entity, "查询 entity artifact 失败")
        self.assertEqual(entity.get("id"), self.entity_artifact_id, "entity artifact id 不匹配")

    def test_query_configured_application_pkg_tree(self):
        if self.application_artifact_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_ARTIFACT_ID，跳过 pkg tree 查询")

        pkg_tree = self.artifact_client.query_application_pkg_tree(self.application_artifact_id)
        self.assertIsNotNone(pkg_tree, "查询 application pkg tree 失败")
        self.assertIsInstance(pkg_tree, list, "pkg tree 结果不是列表")

    def test_application_artifact_roundtrip(self):
        if not self.allow_artifact_mutation:
            raise unittest.SkipTest("未显式允许 artifact 变更，跳过 application artifact roundtrip")

        created = self.artifact_client.create_application_artifact(mock_application_artifact_param())
        self.assertIsNotNone(created, "创建 application artifact 失败")

        try:
            updated_param = created.copy()
            updated_param["description"] = "updated by panel e2e"
            updated = self.artifact_client.update_application_artifact(created["id"], updated_param)
            self.assertIsNotNone(updated, "更新 application artifact 失败")
            self.assertEqual(updated.get("description"), "updated by panel e2e", "application artifact 描述更新失败")
        finally:
            self.artifact_client.delete_application_artifact(created["id"])

    def test_entity_artifact_roundtrip(self):
        if not self.allow_artifact_mutation:
            raise unittest.SkipTest("未显式允许 artifact 变更，跳过 entity artifact roundtrip")

        if self.application_artifact_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_ARTIFACT_ID，无法创建 entity artifact")

        application_artifact = self.artifact_client.query_application_artifact(self.application_artifact_id)
        self.assertIsNotNone(application_artifact, "查询 application artifact 失败")

        created = self.artifact_client.create_entity(mock_entity_artifact_param(application_artifact))
        self.assertIsNotNone(created, "创建 entity artifact 失败")

        try:
            updated_param = created.copy()
            updated_param["description"] = "updated entity artifact"
            updated = self.artifact_client.update_entity(created["id"], updated_param)
            self.assertIsNotNone(updated, "更新 entity artifact 失败")
            self.assertEqual(updated.get("description"), "updated entity artifact", "entity artifact 描述更新失败")
        finally:
            self.artifact_client.delete_entity(created["id"])
