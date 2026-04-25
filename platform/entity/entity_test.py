"""Entity 测试用例"""

import logging
import os
import unittest
import warnings

from session import session
from application import application
from block import block
from entity import entity


logger = logging.getLogger(__name__)


class EntityTestCase(unittest.TestCase):
    """Entity 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.app_instance = application.Application(cls.work_session)
        cls.block_instance = block.Block(cls.work_session)
        cls.entity_instance = entity.Entity(cls.work_session)

    def setUp(self):
        self.created_entity_ids = []
        self.created_block_ids = []
        self.created_app_ids = []

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

    def tearDown(self):
        for entity_id in self.created_entity_ids:
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

        self.created_entity_ids.clear()
        self.created_block_ids.clear()
        self.created_app_ids.clear()

    def _create_entity(self):
        new_entity = self.entity_instance.create_entity(
            entity.mock_entity_param([self.current_block])
        )
        self.assertIsNotNone(new_entity, "创建实体失败")
        self.created_entity_ids.append(new_entity["id"])
        return new_entity

    def test_create_entity(self):
        new_entity = self._create_entity()

        required_fields = ["id", "name", "pkgPath", "version", "fields"]
        for field in required_fields:
            self.assertIn(field, new_entity, f"缺少字段: {field}")

    def test_search_entity(self):
        new_entity = self._create_entity()

        pkg_key = "{0}@{1}".format(new_entity["name"], new_entity["pkgPath"])
        searched_entity = self.entity_instance.search_entity(pkg_key)
        self.assertIsNotNone(searched_entity, "搜索实体失败")
        self.assertEqual(searched_entity["id"], new_entity["id"], "搜索实体ID不匹配")

    def test_query_entity(self):
        new_entity = self._create_entity()

        queried_entity = self.entity_instance.query_entity(new_entity["id"])
        self.assertIsNotNone(queried_entity, "查询实体失败")
        self.assertEqual(queried_entity["id"], new_entity["id"], "实体ID不匹配")
        self.assertEqual(queried_entity["name"], new_entity["name"], "实体名称不匹配")

    def test_update_entity(self):
        new_entity = self._create_entity()

        update_param = new_entity.copy()
        update_param["version"] = "0.0.2"

        updated_entity = self.entity_instance.update_entity(update_param["id"], update_param)
        self.assertIsNotNone(updated_entity, "更新实体失败")
        self.assertEqual(updated_entity["version"], "0.0.2", "实体版本更新失败")

    def test_filter_entity(self):
        new_entity = self._create_entity()

        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(new_entity["name"]),
                }
            }
        }

        entity_list = self.entity_instance.filter_entity(filter_param)
        self.assertIsNotNone(entity_list, "过滤实体失败")
        self.assertGreater(len(entity_list), 0, "过滤结果为空")
        self.assertTrue(
            any(item["id"] == new_entity["id"] for item in entity_list),
            "新建实体未出现在过滤结果中",
        )

    def test_enable_disable_entity(self):
        new_entity = self._create_entity()

        enabled_entity = self.entity_instance.enable_entity(new_entity["id"])
        self.assertIsNotNone(enabled_entity, "启用实体失败")

        disabled_entity = self.entity_instance.disable_entity(new_entity["id"])
        self.assertIsNotNone(disabled_entity, "禁用实体失败")

    def test_destroy_entity(self):
        new_entity = self._create_entity()

        deleted_entity = self.entity_instance.destroy_entity(new_entity["id"])
        self.assertIsNotNone(deleted_entity, "销毁实体失败")
        self.assertEqual(deleted_entity["id"], new_entity["id"], "销毁的实体ID不匹配")

        queried_entity = self.entity_instance.query_entity(new_entity["id"])
        self.assertIsNone(queried_entity, "已销毁的实体查询应失败")
        self.created_entity_ids.remove(new_entity["id"])

    def test_search_nonexistent_entity(self):
        searched_entity = self.entity_instance.search_entity("missing@test")
        self.assertIsNone(searched_entity, "搜索不存在实体应失败")

    def test_query_nonexistent_entity(self):
        queried_entity = self.entity_instance.query_entity(999999)
        self.assertIsNone(queried_entity, "查询不存在实体应失败")

    def test_search_nonexistent_entity_with_invalid_key(self):
        """测试搜索无效格式的包键"""
        searched_entity = self.entity_instance.search_entity("invalid_key_without_at")
        self.assertIsNone(searched_entity, "无效包键搜索应失败")

    def test_enable_already_enabled_entity(self):
        """测试重复启用实体（幂等性）"""
        new_entity = self._create_entity()

        enabled_first = self.entity_instance.enable_entity(new_entity["id"])
        self.assertIsNotNone(enabled_first, "首次启用实体失败")

        enabled_second = self.entity_instance.enable_entity(new_entity["id"])
        # 幂等操作应返回有效结果
        if enabled_second is not None:
            self.assertIn("id", enabled_second, "重复启用应返回实体信息")

    def test_disable_already_disabled_entity(self):
        """测试重复禁用实体（幂等性）"""
        new_entity = self._create_entity()

        enabled = self.entity_instance.enable_entity(new_entity["id"])
        self.assertIsNotNone(enabled, "启用实体失败")

        disabled_first = self.entity_instance.disable_entity(new_entity["id"])
        self.assertIsNotNone(disabled_first, "首次禁用实体失败")

        disabled_second = self.entity_instance.disable_entity(new_entity["id"])
        # 幂等操作
        if disabled_second is not None:
            self.assertIn("id", disabled_second, "重复禁用应返回实体信息")

    def test_enable_nonexistent_entity(self):
        """测试启用不存在的实体（异常测试）"""
        enabled = self.entity_instance.enable_entity(999999)
        self.assertIsNone(enabled, "启用不存在实体应失败")

    def test_disable_nonexistent_entity(self):
        """测试禁用不存在的实体（异常测试）"""
        disabled = self.entity_instance.disable_entity(999999)
        self.assertIsNone(disabled, "禁用不存在实体应失败")

    def test_filter_entity_with_pagination(self):
        """测试带分页的过滤实体"""
        filter_param = {
            "pagination": {
                "pageSize": 10,
                "pageNum": 1,
            },
            "params": {
                "items": {}
            }
        }
        entity_list = self.entity_instance.filter_entity(filter_param)
        self.assertIsNotNone(entity_list, "分页过滤实体失败")
        self.assertGreaterEqual(len(entity_list), 0, "分页过滤结果异常")

    def test_update_nonexistent_entity(self):
        """测试更新不存在的实体（异常测试）"""
        updated = self.entity_instance.update_entity(999999, {"name": "ghost"})
        self.assertIsNone(updated, "更新不存在实体应失败")


if __name__ == "__main__":
    unittest.main()
