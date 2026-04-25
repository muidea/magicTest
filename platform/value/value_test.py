"""Value 测试用例"""

import logging
import os
import unittest
import warnings

from session import session
from application import application
from block import block
from entity import entity
from value import value


logger = logging.getLogger(__name__)


class ValueTestCase(unittest.TestCase):
    """Value 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.app_instance = application.Application(cls.work_session)
        cls.block_instance = block.Block(cls.work_session)
        cls.entity_instance = entity.Entity(cls.work_session)
        cls.value_instance = value.Value(cls.work_session)

    def setUp(self):
        self.created_app_ids = []
        self.created_block_ids = []
        self.created_entity_ids = []
        self.created_entity_value = None

        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用失败")
        self.created_app_ids.append(new_app["id"])
        self.work_session.bind_application(new_app["uuid"])
        self.current_app = new_app

        block_param = block.mock_block_param()
        new_block = self.block_instance.create_block(block_param)
        self.assertIsNotNone(new_block, "创建区块失败")
        self.created_block_ids.append(new_block["id"])
        self.current_block = new_block

        entity_param = entity.mock_entity_param([new_block])
        new_entity = self.entity_instance.create_entity(entity_param)
        self.assertIsNotNone(new_entity, "创建实体失败")
        self.created_entity_ids.append(new_entity["id"])
        self.current_entity = new_entity

        enabled_entity = self.entity_instance.enable_entity(new_entity["id"])
        self.assertIsNotNone(enabled_entity, "启用实体失败")

    def tearDown(self):
        if self.created_entity_value is not None:
            try:
                self.value_instance.delete_value(self.created_entity_value)
            except Exception as err:
                logger.warning("清理值失败: %s", err)

        for entity_id in self.created_entity_ids:
            try:
                self.entity_instance.disable_entity(entity_id)
            except Exception:
                pass
            try:
                self.entity_instance.destroy_entity(entity_id)
            except Exception as err:
                logger.warning("清理实体 %s 失败: %s", entity_id, err)

        for block_id in self.created_block_ids:
            try:
                self.block_instance.destroy_block(block_id)
            except Exception as err:
                logger.warning("清理区块 %s 失败: %s", block_id, err)

        for app_id in self.created_app_ids:
            try:
                self.app_instance.destroy_application(app_id)
            except Exception as err:
                logger.warning("清理应用 %s 失败: %s", app_id, err)

    def _insert_value(self):
        entity_value = value.mock_entity_value(self.current_entity)
        inserted_value = self.value_instance.insert_value(entity_value)
        self.assertIsNotNone(inserted_value, "插入值失败")
        self.created_entity_value = inserted_value
        return inserted_value

    def test_insert_value(self):
        inserted_value = self._insert_value()
        self.assertIn("name", inserted_value, "插入结果缺少name字段")
        self.assertIn("pkgPath", inserted_value, "插入结果缺少pkgPath字段")
        self.assertIn("fields", inserted_value, "插入结果缺少fields字段")

    def test_query_value(self):
        inserted_value = self._insert_value()

        queried_value = self.value_instance.query_value(
            value.mock_entity_query(self.current_entity, inserted_value)
        )
        self.assertIsNotNone(queried_value, "查询值失败")
        self.assertEqual(queried_value["name"], inserted_value["name"], "值名称不匹配")
        self.assertEqual(queried_value["pkgPath"], inserted_value["pkgPath"], "值包路径不匹配")

    def test_update_value(self):
        inserted_value = self._insert_value()
        updated_param = value.update_value(self.current_entity, inserted_value)

        updated_value = self.value_instance.update_value(updated_param)
        self.assertIsNotNone(updated_value, "更新值失败")
        self.assertEqual(updated_value["name"], inserted_value["name"], "更新后值名称不匹配")

    def test_filter_value(self):
        first_value = self._insert_value()
        second_value = self.value_instance.insert_value(first_value)
        self.assertIsNotNone(second_value, "第二次插入值失败")

        filtered_value = self.value_instance.filter_value(
            value.mock_entity_filter(self.current_entity, first_value)
        )
        self.assertIsNotNone(filtered_value, "过滤值失败")
        self.assertIn("values", filtered_value, "过滤结果缺少values字段")
        self.assertGreaterEqual(len(filtered_value["values"]), 2, "过滤结果数量不符合预期")

    def test_delete_value(self):
        inserted_value = self._insert_value()

        deleted_value = self.value_instance.delete_value(inserted_value)
        self.assertIsNotNone(deleted_value, "删除值失败")
        self.assertEqual(deleted_value["name"], inserted_value["name"], "删除的值名称不匹配")
        self.created_entity_value = None

    def test_query_nonexistent_value(self):
        queried_value = self.value_instance.query_value(
            {
                "name": "missing",
                "pkgPath": "missing",
                "fields": [],
            }
        )
        self.assertIsNone(queried_value, "查询不存在的值应失败")

    def test_insert_duplicate_value(self):
        """测试插入重复值"""
        inserted_value = self._insert_value()

        # 使用相同参数再次插入
        entity_value = value.mock_entity_value(self.current_entity)
        second_insert = self.value_instance.insert_value(entity_value)
        self.assertIsNotNone(second_insert, "第二次插入值应成功（允许多条）")

    def test_delete_nonexistent_value(self):
        """测试删除不存在的值（异常测试）"""
        deleted_value = self.value_instance.delete_value(
            {
                "name": "ghost_value",
                "pkgPath": "ghost_pkg",
                "fields": [],
            }
        )
        self.assertIsNone(deleted_value, "删除不存在的值应失败")

    def test_update_nonexistent_value(self):
        """测试更新不存在的值（异常测试）"""
        updated_value = self.value_instance.update_value(
            {
                "name": "ghost_value",
                "pkgPath": "ghost_pkg",
                "fields": [],
            }
        )
        self.assertIsNone(updated_value, "更新不存在的值应失败")

    def test_filter_value_with_empty_result(self):
        """测试过滤条件不匹配时返回空结果"""
        filter_param = value.mock_entity_filter(
            {"name": "nonexistent_entity", "pkgPath": "nonexistent_pkg"},
            {"fields": []},
        )
        filtered_value = self.value_instance.filter_value(filter_param)
        self.assertIsNotNone(filtered_value, "过滤不存在的值不应崩溃")
        values = filtered_value.get("values", [])
        self.assertEqual(len(values), 0, "不匹配条件应返回空列表")

    def test_insert_value_with_empty_fields(self):
        """测试插入空字段的值"""
        empty_value = {
            "name": self.current_entity["name"],
            "pkgPath": self.current_entity["pkgPath"],
            "fields": [],
        }
        inserted_value = self.value_instance.insert_value(empty_value)
        # 行为取决于服务实现，记录观察
        if inserted_value is not None:
            self.created_entity_value = inserted_value
            self.assertIn("name", inserted_value, "插入结果缺少name字段")


if __name__ == "__main__":
    unittest.main()
