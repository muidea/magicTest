"""Block 测试用例"""

import logging
import os
import unittest
import warnings

from session import session
from block import block


logger = logging.getLogger(__name__)


class BlockTestCase(unittest.TestCase):
    """Block 测试用例类"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.block_instance = block.Block(cls.work_session)

    def setUp(self):
        self.created_block_ids = []

    def tearDown(self):
        for block_id in self.created_block_ids:
            try:
                self.block_instance.destroy_block(block_id)
            except Exception as err:
                logger.warning("清理区块 %s 失败: %s", block_id, err)

        self.created_block_ids.clear()

    def test_create_block(self):
        new_block = self.block_instance.create_block(block.mock_block_param())
        self.assertIsNotNone(new_block, "创建区块失败")

        required_fields = ["id", "name", "scope"]
        for field in required_fields:
            self.assertIn(field, new_block, f"缺少字段: {field}")

        self.created_block_ids.append(new_block["id"])

    def test_query_block(self):
        new_block = self.block_instance.create_block(block.mock_block_param())
        self.assertIsNotNone(new_block, "创建区块失败")
        self.created_block_ids.append(new_block["id"])

        queried_block = self.block_instance.query_block(new_block["id"])
        self.assertIsNotNone(queried_block, "查询区块失败")
        self.assertEqual(queried_block["id"], new_block["id"], "区块ID不匹配")
        self.assertEqual(queried_block["name"], new_block["name"], "区块名称不匹配")

    def test_update_block(self):
        new_block = self.block_instance.create_block(block.mock_block_param())
        self.assertIsNotNone(new_block, "创建区块失败")
        self.created_block_ids.append(new_block["id"])

        update_param = new_block.copy()
        update_param["scope"] = "updated-scope"

        updated_block = self.block_instance.update_block(update_param["id"], update_param)
        self.assertIsNotNone(updated_block, "更新区块失败")
        self.assertEqual(updated_block["scope"], "updated-scope", "区块 scope 更新失败")

    def test_filter_block(self):
        new_block = self.block_instance.create_block(block.mock_block_param())
        self.assertIsNotNone(new_block, "创建区块失败")
        self.created_block_ids.append(new_block["id"])

        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(new_block["name"]),
                }
            }
        }

        block_list = self.block_instance.filter_block(filter_param)
        self.assertIsNotNone(block_list, "过滤区块失败")
        self.assertGreater(len(block_list), 0, "过滤结果为空")
        self.assertTrue(
            any(item["id"] == new_block["id"] for item in block_list),
            "新建区块未出现在过滤结果中",
        )

    def test_destroy_block(self):
        new_block = self.block_instance.create_block(block.mock_block_param())
        self.assertIsNotNone(new_block, "创建区块失败")

        deleted_block = self.block_instance.destroy_block(new_block["id"])
        self.assertIsNotNone(deleted_block, "销毁区块失败")
        self.assertEqual(deleted_block["id"], new_block["id"], "销毁的区块ID不匹配")

        queried_block = self.block_instance.query_block(new_block["id"])
        self.assertIsNone(queried_block, "已销毁的区块查询应失败")

    def test_query_nonexistent_block(self):
        queried_block = self.block_instance.query_block("999999")
        self.assertIsNone(queried_block, "查询不存在的区块应失败")

    def test_destroy_nonexistent_block(self):
        deleted_block = self.block_instance.destroy_block("999999")
        self.assertIsNone(deleted_block, "销毁不存在的区块应失败")


if __name__ == "__main__":
    unittest.main()
