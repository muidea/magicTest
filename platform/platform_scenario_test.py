"""平台跨模块集成场景测试 — 覆盖 Application → Block → Entity → Value 的完整编排链路

这些用例验证多个平台模块之间的协作和依赖关系，而非孤立的单一接口测试。
"""

import logging
import os
import unittest
import warnings

from session import session
from application import application
from block import block
from entity import entity
from value import value
from operation_log import operation_log
from totalizator import totalizator


logger = logging.getLogger(__name__)


class PlatformScenarioTestCase(unittest.TestCase):
    """平台跨模块集成场景测试"""

    server_url = os.getenv("MAGICTEST_PLATFORM_BASE_URL", "https://autotest.local.vpc/api/v1")
    namespace = os.getenv("MAGICTEST_PLATFORM_NAMESPACE", "")

    @classmethod
    def setUpClass(cls):
        warnings.simplefilter("ignore", ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.app = application.Application(cls.work_session)
        cls.block = block.Block(cls.work_session)
        cls.entity = entity.Entity(cls.work_session)
        cls.value = value.Value(cls.work_session)
        cls.oplog = operation_log.OperationLog(cls.work_session)
        cls.totalizator = totalizator.Totalizator(cls.work_session)

    def setUp(self):
        self._cleanup_stack = []

    def tearDown(self):
        """逆序清理所有测试资源"""
        for cleanup_fn in reversed(self._cleanup_stack):
            try:
                cleanup_fn()
            except Exception as err:
                logger.warning("清理资源失败: %s", err)

    # ---- 资源创建辅助 ----

    def _create_app(self):
        """创建测试应用并注册清理"""
        app_param = application.mock_application_param()
        new_app = self.app.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用失败")
        app_id = new_app["id"]
        self._cleanup_stack.append(lambda: self.app.destroy_application(app_id))
        return new_app

    def _create_block(self):
        """创建测试区块并注册清理"""
        block_param = block.mock_block_param()
        new_block = self.block.create_block(block_param)
        self.assertIsNotNone(new_block, "创建区块失败")
        block_id = new_block["id"]
        self._cleanup_stack.append(lambda: self.block.destroy_block(block_id))
        return new_block

    def _create_entity(self, app_uuid, blocks):
        """在指定应用下创建实体"""
        self.work_session.bind_application(app_uuid)
        entity_param = entity.mock_entity_param(blocks)
        new_entity = self.entity.create_entity(entity_param)
        self.assertIsNotNone(new_entity, "创建实体失败")
        entity_id = new_entity["id"]
        self._cleanup_stack.append(lambda: self.entity.destroy_entity(entity_id))
        return new_entity

    # ---- 场景用例 ----

    def test_scenario_full_platform_chain(self):
        """场景1: 完整平台链路 — Application → Block → Entity → Value

        创建应用 → 创建区块 → 绑定应用 → 创建实体 → 启用实体 → 插入值 → 查询值 → 清理
        """
        # 创建应用
        new_app = self._create_app()
        self.assertIn("id", new_app, "应用缺少id字段")
        self.assertIn("uuid", new_app, "应用缺少uuid字段")

        # 创建区块
        new_block = self._create_block()
        self.assertIn("id", new_block, "区块缺少id字段")

        # 绑定应用并创建实体
        self.work_session.bind_application(new_app["uuid"])
        entity_param = entity.mock_entity_param([new_block])
        new_entity = self.entity.create_entity(entity_param)
        self.assertIsNotNone(new_entity, "创建实体失败")
        entity_id = new_entity["id"]
        self._cleanup_stack.append(
            lambda: self.entity.destroy_entity(entity_id)
        )

        # 启用实体
        enabled = self.entity.enable_entity(entity_id)
        self.assertIsNotNone(enabled, "启用实体失败")

        # 插入值
        entity_value = value.mock_entity_value(new_entity)
        inserted = self.value.insert_value(entity_value)
        self.assertIsNotNone(inserted, "插入值失败")
        self.assertIn("name", inserted, "插入值缺少name字段")

        # 查询值
        query_param = value.mock_entity_query(new_entity, inserted)
        queried = self.value.query_value(query_param)
        self.assertIsNotNone(queried, "查询值失败")
        self.assertEqual(queried["name"], inserted["name"], "值名称不匹配")

        # 禁用并销毁实体（通过清理栈执行）
        self._cleanup_stack.append(
            lambda: self.entity.disable_entity(entity_id)
        )

    def test_scenario_application_start_stop(self):
        """场景2: 应用启动停止链路"""
        new_app = self._create_app()

        # 启动应用
        started = self.app.start_application(new_app["id"])
        self.assertIsNotNone(started, "启动应用失败")

        # 停止应用
        stopped = self.app.stop_application(new_app["id"])
        self.assertIsNotNone(stopped, "停止应用失败")

    def test_scenario_entity_enable_disable_cycle(self):
        """场景3: 实体启用/禁用/启用的状态转换"""
        new_app = self._create_app()
        new_block = self._create_block()
        new_entity = self._create_entity(new_app["uuid"], [new_block])

        # 先启用
        enabled = self.entity.enable_entity(new_entity["id"])
        self.assertIsNotNone(enabled, "启用实体失败")

        # 禁用
        disabled = self.entity.disable_entity(new_entity["id"])
        self.assertIsNotNone(disabled, "禁用实体失败")

        # 再次启用
        re_enabled = self.entity.enable_entity(new_entity["id"])
        self.assertIsNotNone(re_enabled, "再次启用实体失败")

    def test_scenario_operation_log(self):
        """场景4: 操作日志写入与过滤"""
        oplog_param = operation_log.mock_operation_log_param()
        write_ok = self.oplog.write_operation_log(oplog_param)
        self.assertTrue(write_ok, "写入操作日志失败")

        oplog_filter = {
            "params": {
                "items": {
                    "operator": "{0}|=".format(oplog_param["operator"]),
                }
            }
        }
        oplog_list = self.oplog.filter_operation_log(oplog_filter)
        self.assertIsNotNone(oplog_list, "过滤操作日志失败")

    def test_scenario_totalizator_and_entity_value_interaction(self):
        """场景5: 总计器与实体值的交互

        注册总计器 → 创建应用/实体 → 刷新总计器 → 过滤总计器
        """
        # 注册总计器
        tz_param = totalizator.mock_totalizator_param()
        register_ok = self.totalizator.register_totalizator(tz_param)
        self.assertTrue(register_ok, "注册总计器失败")
        self._cleanup_stack.append(
            lambda: self.totalizator.unregister_totalizator(tz_param)
        )

        # 创建应用/区块/实体（验证不影响总计器）
        new_app = self._create_app()
        new_block = self._create_block()
        new_entity = self._create_entity(new_app["uuid"], [new_block])

        # 刷新总计器
        refresh_param = {
            "name": tz_param["name"],
            "metric": tz_param["metric"],
            "value": 42,
        }
        refresh_ok = self.totalizator.refresh_totalizator(refresh_param)
        self.assertTrue(refresh_ok, "刷新总计器失败")

        # 过滤总计器
        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(tz_param["name"]),
                }
            }
        }
        tz_list = self.totalizator.filter_totalizator(filter_param)
        self.assertIsNotNone(tz_list, "过滤总计器失败")
        self.assertGreater(len(tz_list), 0, "过滤结果为空")

    def test_scenario_application_update_and_filter(self):
        """场景6: 应用创建 → 更新 → 过滤验证"""
        new_app = self._create_app()

        # 更新应用
        update_param = new_app.copy()
        update_param["description"] = "Scenario updated description"
        updated = self.app.update_application(update_param["id"], update_param)
        self.assertIsNotNone(updated, "更新应用失败")
        self.assertEqual(
            updated["description"], "Scenario updated description",
            "应用描述更新失败",
        )

        # 过滤验证
        filter_param = {
            "params": {
                "items": {
                    "name": "{0}|=".format(new_app["name"]),
                }
            }
        }
        app_list = self.app.filter_application(filter_param)
        self.assertIsNotNone(app_list, "过滤应用失败")
        self.assertGreater(len(app_list), 0, "过滤结果为空")
        found = any(item["id"] == new_app["id"] for item in app_list)
        self.assertTrue(found, "更新后的应用未出现在过滤结果中")

    def test_scenario_block_and_entity_dependency(self):
        """场景7: 区块依赖验证 — 删除含实体的区块"""
        new_app = self._create_app()
        new_block = self._create_block()

        # 在区块下创建实体
        new_entity = self._create_entity(new_app["uuid"], [new_block])
        self.assertIn("block", new_entity, "实体缺少block字段")
        block_ids = [b["id"] for b in new_entity["block"]]
        self.assertIn(new_block["id"], block_ids, "区块ID未在实体关联中出现")

        # 先销毁实体，再销毁区块（依赖关系要求）
        self.entity.destroy_entity(new_entity["id"])
        self._cleanup_stack.pop()  # 移除已执行的清理

        self.block.destroy_block(new_block["id"])
        self._cleanup_stack.pop()  # 移除已执行的清理

    def test_scenario_value_update_and_filter(self):
        """场景8: 值更新后过滤验证"""
        new_app = self._create_app()
        new_block = self._create_block()
        new_entity = self._create_entity(new_app["uuid"], [new_block])

        # 启用实体
        self.entity.enable_entity(new_entity["id"])
        self._cleanup_stack.append(
            lambda: self.entity.disable_entity(new_entity["id"])
        )

        # 插入值
        entity_value = value.mock_entity_value(new_entity)
        inserted = self.value.insert_value(entity_value)
        self.assertIsNotNone(inserted, "插入值失败")

        # 更新值
        updated_param = value.update_value(new_entity, inserted)
        updated = self.value.update_value(updated_param)
        self.assertIsNotNone(updated, "更新值失败")

        # 过滤值
        filter_param = value.mock_entity_filter(new_entity, updated)
        filtered = self.value.filter_value(filter_param)
        self.assertIsNotNone(filtered, "过滤值失败")
        self.assertIn("values", filtered, "过滤结果缺少values字段")

    def test_scenario_multi_block_entity(self):
        """场景9: 实体关联多个区块"""
        new_app = self._create_app()
        block_a = self._create_block()
        block_b = self._create_block()

        # 实体关联两个区块
        self.work_session.bind_application(new_app["uuid"])
        entity_param = entity.mock_entity_param([block_a, block_b])
        new_entity = self.entity.create_entity(entity_param)
        self.assertIsNotNone(new_entity, "创建多区块实体失败")
        entity_id = new_entity["id"]
        self._cleanup_stack.append(
            lambda: self.entity.destroy_entity(entity_id)
        )

        # 验证实体关联到两个区块
        self.assertIn("block", new_entity, "实体缺少block字段")
        self.assertGreaterEqual(
            len(new_entity["block"]), 2,
            "实体应关联至少2个区块",
        )

        block_ids = [b["id"] for b in new_entity["block"]]
        self.assertIn(block_a["id"], block_ids, "区块A未关联")
        self.assertIn(block_b["id"], block_ids, "区块B未关联")

    def test_scenario_entity_field_types(self):
        """场景10: 多种字段类型的实体创建"""
        from entity import entity as entity_mod

        new_app = self._create_app()
        new_block = self._create_block()

        self.work_session.bind_application(new_app["uuid"])

        # 构建包含多种字段类型的实体
        entity_param = entity.mock_entity_param([new_block])
        # 添加不同类型的字段
        field_types = [
            {"value": 100, "name": "bool", "pkgPath": ""},
            {"value": 104, "name": "int", "pkgPath": ""},
            {"value": 105, "name": "int64", "pkgPath": ""},
            {"value": 112, "name": "float64", "pkgPath": ""},
            {"value": 113, "name": "string", "pkgPath": ""},
            {"value": 114, "name": "time", "pkgPath": ""},
        ]
        extra_fields = []
        for i, ft in enumerate(field_types):
            extra_fields.append({
                "index": i + 1,
                "name": "field_{}".format(ft["name"]),
                "spec": {"viewDeclare": [1, 2]},
                "type": ft,
            })
        entity_param["fields"] = extra_fields

        new_entity = self.entity.create_entity(entity_param)
        self.assertIsNotNone(new_entity, "创建多类型字段实体失败")
        entity_id = new_entity["id"]
        self._cleanup_stack.append(
            lambda: self.entity.destroy_entity(entity_id)
        )

        # 验证所有字段类型都存在
        created_fields = {f["name"]: f for f in new_entity.get("fields", [])}
        for ft in field_types:
            field_name = "field_{}".format(ft["name"])
            self.assertIn(field_name, created_fields,
                          "缺少字段类型: {}".format(ft["name"]))


if __name__ == "__main__":
    unittest.main()
