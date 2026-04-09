import os
import unittest

from definition import (
    DefinitionClient,
    mock_application_definition_param,
    mock_entity_definition_param,
)
from panel_test_support import PanelE2EBase


class PanelDefinitionTestCase(PanelE2EBase):
    application_definition_id = int(os.getenv("MAGICTEST_PANEL_APPLICATION_DEFINITION_ID", "0") or "0")
    entity_definition_id = int(os.getenv("MAGICTEST_PANEL_ENTITY_DEFINITION_ID", "0") or "0")
    allow_definition_mutation = os.getenv("MAGICTEST_PANEL_ALLOW_DEFINITION_MUTATION", "").lower() in ("1", "true", "yes")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.definition_client = DefinitionClient(cls.work_session)

    def test_filter_entity_definitions_smoke(self):
        entity_list = self.definition_client.filter_entity_definitions()
        self.assertIsNotNone(entity_list, "过滤 entity definition 失败")
        self.assertIsInstance(entity_list, list, "entity definition 结果不是列表")

    def test_query_configured_application_definition(self):
        if self.application_definition_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_DEFINITION_ID，跳过 application definition 查询")

        definition = self.definition_client.query_application_definition(self.application_definition_id)
        self.assertIsNotNone(definition, "查询 application definition 失败")
        self.assertEqual(definition.get("id"), self.application_definition_id, "application definition id 不匹配")

    def test_query_configured_entity_definition(self):
        if self.entity_definition_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_ENTITY_DEFINITION_ID，跳过 entity definition 查询")

        entity = self.definition_client.query_entity_definition(self.entity_definition_id)
        self.assertIsNotNone(entity, "查询 entity definition 失败")
        self.assertEqual(entity.get("id"), self.entity_definition_id, "entity definition id 不匹配")

    def test_query_configured_application_pkg_tree(self):
        if self.application_definition_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_DEFINITION_ID，跳过 pkg tree 查询")

        pkg_tree = self.definition_client.query_application_pkg_tree(self.application_definition_id)
        self.assertIsNotNone(pkg_tree, "查询 application pkg tree 失败")
        self.assertIsInstance(pkg_tree, list, "pkg tree 结果不是列表")

    def test_application_definition_roundtrip(self):
        if not self.allow_definition_mutation:
            raise unittest.SkipTest("未显式允许 definition 变更，跳过 application definition roundtrip")

        created = self.definition_client.create_application_definition(mock_application_definition_param())
        self.assertIsNotNone(created, "创建 application definition 失败")

        try:
            updated_param = created.copy()
            updated_param["description"] = "updated by panel e2e"
            updated = self.definition_client.update_application_definition(created["id"], updated_param)
            self.assertIsNotNone(updated, "更新 application definition 失败")
            self.assertEqual(updated.get("description"), "updated by panel e2e", "application definition 描述更新失败")
        finally:
            self.definition_client.delete_application_definition(created["id"])

    def test_entity_definition_roundtrip(self):
        if not self.allow_definition_mutation:
            raise unittest.SkipTest("未显式允许 definition 变更，跳过 entity definition roundtrip")

        if self.application_definition_id <= 0:
            raise unittest.SkipTest("未设置 MAGICTEST_PANEL_APPLICATION_DEFINITION_ID，无法创建 entity definition")

        application_definition = self.definition_client.query_application_definition(self.application_definition_id)
        self.assertIsNotNone(application_definition, "查询 application definition 失败")

        created = self.definition_client.create_entity_definition(mock_entity_definition_param(application_definition))
        self.assertIsNotNone(created, "创建 entity definition 失败")

        try:
            updated_param = created.copy()
            updated_param["description"] = "updated entity definition"
            updated = self.definition_client.update_entity_definition(created["id"], updated_param)
            self.assertIsNotNone(updated, "更新 entity definition 失败")
            self.assertEqual(updated.get("description"), "updated entity definition", "entity definition 描述更新失败")
        finally:
            self.definition_client.delete_entity_definition(created["id"])
