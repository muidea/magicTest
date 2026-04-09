#!/usr/bin/env python3
"""
VMI 测试框架 - 完整验证测试
验证核心功能，无需网络连接
"""

import json
import logging
import os
import unittest
from unittest.mock import Mock, patch

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__, components=("vmi", "cas"))

logger = logging.getLogger(__name__)


def _clear_config_cache() -> None:
    import sys

    for module in ["config_helper", "tenant_config_helper"]:
        if module in sys.modules:
            del sys.modules[module]


class TestFrameworkValidation(unittest.TestCase):
    """框架验证测试"""

    def test_config_system(self):
        """测试配置系统"""
        logger.info("测试配置系统")

        self.assertTrue(os.path.exists("test_config.json"), "配置文件不存在")

        with open("test_config.json", "r", encoding="utf-8") as f:
            raw_config = json.load(f)

        _clear_config_cache()
        from config_helper import get_config

        config = get_config()

        self.assertIn("mode", config, "配置缺少mode字段")
        self.assertIn("environment", config, "配置缺少environment字段")
        self.assertIn("default_tenant", config, "配置缺少default_tenant字段")
        self.assertIn("default_server_url", config, "配置缺少default_server_url字段")
        self.assertIn("request_application", config, "配置缺少request_application字段")
        self.assertIn("credentials", config, "配置缺少credentials字段")
        self.assertIn("tenant_targets", config, "配置缺少tenant_targets字段")
        self.assertIn("target", config, "配置缺少target字段")
        self.assertIn("observability", config, "配置缺少observability字段")
        self.assertIn("hotspot_prewrite_query", config["concurrent"], "并发配置缺少hotspot_prewrite_query字段")
        self.assertNotIn("server", raw_config, "配置仍包含旧server字段")
        self.assertNotIn("multi_tenant", raw_config, "配置仍包含旧multi_tenant字段")

        logger.info("配置系统测试通过")

    def test_module_imports(self):
        """测试模块导入"""
        logger.info("测试模块导入")

        try:
            from multi_tenant_manager import (MultiTenantSessionManager,
                                              SDKFactory)
            from tenant_config_helper import (get_multi_tenant_config,
                                              is_multi_tenant_enabled)
            from test_base_multi_tenant import TestBaseMultiTenant

            logger.info("核心模块导入成功")
        except ImportError as e:
            self.fail(f"核心模块导入失败: {e}")

        try:
            from config_helper import get_config
            from session_manager import SessionManager
            from test_base_with_session_manager import (
                ConcurrentTestMixin, PerformanceMonitor,
                TestBaseWithSessionManager)

            logger.info("基础模块导入成功")
        except ImportError as e:
            self.fail(f"基础模块导入失败: {e}")

        logger.info("模块导入测试通过")

    def test_config_helpers(self):
        """测试配置助手"""
        logger.info("测试配置助手")
        _clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()

        self.assertIn("enabled", config)
        self.assertIn("default_tenant", config)
        self.assertIn("tenants", config)
        self.assertIsInstance(config["enabled"], bool)
        self.assertEqual(config["enabled"], is_multi_tenant_enabled())
        self.assertIn("autotest", config["tenants"])

        logger.info("配置助手测试通过")

    @patch("session_manager.SessionManager")
    def test_multi_tenant_manager(self, MockSessionManager):
        """测试多租户管理器"""
        logger.info("测试多租户管理器")

        from multi_tenant_manager import MultiTenantSessionManager, SDKFactory

        mock_session = Mock()
        mock_session.create_session.return_value = True
        mock_session.is_logged_in = True
        mock_session.work_session = Mock()
        MockSessionManager.return_value = mock_session

        test_config = {
            "tenant1": {
                "server_url": "https://tenant1.local.vpc",
                "username": "admin1",
                "password": "password1",
                "namespace": "tenant1",
                "enabled": True,
            },
            "tenant2": {
                "server_url": "https://tenant2.local.vpc",
                "username": "admin2",
                "password": "password2",
                "namespace": "tenant2",
                "enabled": True,
            },
        }

        mt_manager = MultiTenantSessionManager(test_config)

        self.assertEqual(len(mt_manager.session_managers), 2)
        self.assertIn("tenant1", mt_manager.session_managers)
        self.assertIn("tenant2", mt_manager.session_managers)

        sdk_factory = SDKFactory(mt_manager)

        class TestSDK:
            def __init__(self, session):
                self.session = session

        sdk = sdk_factory.get_sdk_for_tenant("tenant1", TestSDK)
        self.assertIsNotNone(sdk)

        logger.info("多租户管理器测试通过")

    def test_base_classes(self):
        """测试测试基类"""
        logger.info("测试测试基类")

        from test_base_multi_tenant import TestBaseMultiTenant
        from test_base_with_session_manager import TestBaseWithSessionManager

        self.assertTrue(issubclass(TestBaseMultiTenant, TestBaseWithSessionManager))

        required_methods = [
            "switch_tenant",
            "get_sdk_for_current_tenant",
            "get_sdk_for_tenant",
            "run_for_tenant",
            "run_for_all_tenants",
            "get_tenant_status",
            "assert_tenant_isolation",
        ]

        for method in required_methods:
            self.assertTrue(
                hasattr(TestBaseMultiTenant, method),
                f"TestBaseMultiTenant缺少方法: {method}",
            )

        logger.info("测试基类测试通过")

    def test_runtime_readiness(self):
        """测试运行时入口完整性"""
        logger.info("测试运行时入口完整性")

        test_files = ["scenario_test.py", "aging_test_simple.py", "run_tests.py"]

        for test_file in test_files:
            self.assertTrue(os.path.exists(test_file), f"测试文件不存在: {test_file}")

        _clear_config_cache()

        from tenant_config_helper import (get_multi_tenant_config,
                                          is_multi_tenant_enabled)

        config = get_multi_tenant_config()
        self.assertIsInstance(is_multi_tenant_enabled(), bool)
        self.assertIn("autotest", config["tenants"])
        self.assertTrue(config["tenants"]["autotest"]["enabled"])
        self.assertEqual(config["default_tenant"], "autotest")

        logger.info("运行时入口完整性测试通过")

    def test_multi_tenant_full_flow_coverage(self):
        """测试多租户全业务链路覆盖矩阵完整性"""
        logger.info("测试多租户全业务链路覆盖矩阵")

        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        coverage = MultiTenantBusinessScenarioFactory.get_full_flow_coverage()
        expected_entities = {
            "status",
            "warehouse",
            "shelf",
            "store",
            "partner",
            "member",
            "product",
            "product_info",
            "goods_info",
            "goods",
            "reward_policy",
            "credit",
            "credit_report",
            "credit_reward",
            "goods_item",
            "stockin",
            "stockout",
            "order",
        }

        self.assertEqual(set(coverage.keys()), expected_entities)
        self.assertEqual(coverage["status"], ["list", "query"])

        mutable_entities = expected_entities - {"status"}
        for entity_type in mutable_entities:
            self.assertEqual(
                coverage[entity_type],
                ["create", "query", "list", "update", "delete"],
                f"{entity_type} 覆盖矩阵不完整",
            )

        logger.info("多租户全业务链路覆盖矩阵测试通过")

    def test_hotspot_stress_skips_prewrite_query_by_default(self):
        """测试热点压测默认不在写入前额外回读对象"""
        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        context = {
            "status_id": 1,
            "warehouse_id": 11,
            "shelf_id": 12,
            "store_id": 13,
            "product_id": 14,
            "product_info_id": 15,
            "goods_info_id": 16,
            "goods_id": 17,
            "suffix": "unit",
            "hotspot_update_templates": {
                "warehouse": {"name": "wh", "description": "seed"},
                "store": {"name": "store", "description": "seed"},
                "product": {
                    "name": "product",
                    "description": "seed",
                    "image": [],
                    "expire": 365,
                    "tags": ["stress"],
                    "status": {"id": 1},
                },
                "goods": {
                    "sku": "sku-1",
                    "name": "goods",
                    "description": "seed",
                    "parameter": "p",
                    "serviceInfo": "s",
                    "product": {"id": 15},
                    "count": 160,
                    "price": 128.88,
                    "shelf": [{"id": 12}],
                    "store": {"id": 13},
                    "status": {"id": 1},
                },
            },
        }

        status_sdk = Mock()
        status_sdk.filter_status.return_value = []
        warehouse_sdk = Mock()
        warehouse_sdk.filter_warehouse.return_value = []
        warehouse_sdk.query.return_value = {"id": 11}
        warehouse_sdk.update_warehouse.return_value = {"id": 11}
        warehouse_sdk.query_warehouse.return_value = {"id": 11}
        store_sdk = Mock()
        store_sdk.filter_store.return_value = []
        store_sdk.query.return_value = {"id": 13}
        store_sdk.update_store.return_value = {"id": 13}
        store_sdk.query_store.return_value = {"id": 13}
        product_sdk = Mock()
        product_sdk.filter_product.return_value = []
        product_sdk.query.return_value = {"id": 14}
        product_sdk.update_product.return_value = {"id": 14}
        product_sdk.query_product.return_value = {"id": 14}
        product_info_sdk = Mock()
        product_info_sdk.filter_product_info.return_value = []
        product_info_sdk.query.return_value = {"id": 15}
        goods_info_sdk = Mock()
        goods_info_sdk.filter_goods_info.return_value = []
        goods_info_sdk.query.return_value = {"id": 16}
        goods_sdk = Mock()
        goods_sdk.filter_goods.return_value = []
        goods_sdk.query.return_value = {"id": 17}
        goods_sdk.update_goods.return_value = {"id": 17}
        goods_sdk.query_goods.return_value = {"id": 17}
        sdks = {
            "status": status_sdk,
            "warehouse": warehouse_sdk,
            "store": store_sdk,
            "product": product_sdk,
            "product_info": product_info_sdk,
            "goods_info": goods_info_sdk,
            "goods": goods_sdk,
        }

        test_func = MultiTenantBusinessScenarioFactory.create_hotspot_stress_test(
            write_every=1,
            read_rounds=1,
            query_rounds=1,
            prewrite_query=False,
            shared_context_provider=lambda tenant_id, session_manager: context,
        )

        with patch.object(
            MultiTenantBusinessScenarioFactory,
            "_get_hotspot_sdks",
            return_value=sdks,
        ):
            test_func("t001", 0, 0, Mock())

        warehouse_sdk.query_warehouse.assert_not_called()
        store_sdk.query_store.assert_not_called()
        product_sdk.query_product.assert_not_called()
        goods_sdk.query_goods.assert_not_called()

        warehouse_sdk.update_warehouse.assert_called_once_with(
            11, {"description": "热点压测更新仓库_unit_0"}
        )
        store_sdk.update_store.assert_called_once_with(
            13, {"description": "热点压测更新门店_unit_0"}
        )
        product_sdk.update_product.assert_called_once_with(
            14, {"description": "热点压测更新产品_unit_0"}
        )
        goods_sdk.update_goods.assert_called_once_with(
            17,
            {
                "description": "热点压测更新商品_unit_0",
                "count": 160,
            },
        )

    def test_hotspot_sdks_rebuilt_after_session_reconnect(self):
        """测试热点 SDK 缓存在会话重建后会重新绑定到新 session。"""
        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        first_session = Mock(name="first_session")
        second_session = Mock(name="second_session")
        session_manager = Mock()
        session_manager.get_session.side_effect = [first_session, second_session]

        with patch("sdk.StatusSDK", side_effect=lambda s: ("status", s)), patch(
            "sdk.WarehouseSDK", side_effect=lambda s: ("warehouse", s)
        ), patch("sdk.ShelfSDK", side_effect=lambda s: ("shelf", s)), patch(
            "sdk.StoreSDK", side_effect=lambda s: ("store", s)
        ), patch("sdk.ProductSDK", side_effect=lambda s: ("product", s)), patch(
            "sdk.ProductInfoSDK", side_effect=lambda s: ("product_info", s)
        ), patch("sdk.GoodsInfoSDK", side_effect=lambda s: ("goods_info", s)), patch(
            "sdk.GoodsSDK", side_effect=lambda s: ("goods", s)
        ):
            first_sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(
                session_manager
            )
            second_sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(
                session_manager
            )

        self.assertIs(first_sdks["status"][1], first_session)
        self.assertIs(second_sdks["status"][1], second_session)
        self.assertIsNot(first_sdks, second_sdks)

    def test_goods_hotspot_only_hits_goods_sdk(self):
        """测试 goods 专项热点压测只访问 goods 链路。"""
        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        context = {
            "status_id": 1,
            "shelf_id": 12,
            "store_id": 13,
            "product_info_id": 15,
            "goods_id": 17,
            "suffix": "unit",
            "hotspot_update_templates": {
                "goods": {
                    "sku": "sku-1",
                    "name": "goods",
                    "description": "seed",
                    "parameter": "p",
                    "serviceInfo": "s",
                    "product": {"id": 15},
                    "count": 160,
                    "price": 128.88,
                    "shelf": [{"id": 12}],
                    "store": {"id": 13},
                    "status": {"id": 1},
                },
            },
        }

        goods_sdk = Mock()
        goods_sdk.filter_goods.return_value = []
        goods_sdk.query.return_value = {"id": 17}
        goods_sdk.update_goods.return_value = {"id": 17}
        sdks = {
            "status": Mock(),
            "warehouse": Mock(),
            "store": Mock(),
            "product": Mock(),
            "product_info": Mock(),
            "goods_info": Mock(),
            "goods": goods_sdk,
        }

        test_func = MultiTenantBusinessScenarioFactory.create_goods_hotspot_stress_test(
            write_every=1,
            read_rounds=1,
            query_rounds=1,
            prewrite_query=False,
            shared_context_provider=lambda tenant_id, session_manager: context,
        )

        with patch.object(
            MultiTenantBusinessScenarioFactory,
            "_get_hotspot_sdks",
            return_value=sdks,
        ):
            test_func("t001", 0, 0, Mock())

        goods_sdk.filter_goods.assert_called_once()
        goods_sdk.query.assert_called_once_with(
            17,
            unittest.mock.ANY,
        )
        goods_sdk.update_goods.assert_called_once_with(
            17,
            {
                "description": "专项压测更新商品_unit_0",
                "count": 160,
            },
        )
        sdks["status"].filter_status.assert_not_called()
        sdks["warehouse"].filter_warehouse.assert_not_called()
        sdks["warehouse"].query.assert_not_called()
        sdks["store"].filter_store.assert_not_called()
        sdks["store"].query.assert_not_called()
        sdks["product"].filter_product.assert_not_called()
        sdks["product"].query.assert_not_called()
        sdks["product_info"].filter_product_info.assert_not_called()
        sdks["product_info"].query.assert_not_called()
        sdks["goods_info"].filter_goods_info.assert_not_called()
        sdks["goods_info"].query.assert_not_called()

    def test_multi_tenant_list_assertion_prefers_id_filter(self):
        """测试多租户全业务流的列表校验优先使用按 id 过滤，避免高位 ID 被分页吞掉。"""
        from concurrent_test_v2 import MultiTenantBusinessScenarioFactory

        partner_sdk = Mock()
        partner_sdk.filter_partner.side_effect = [
            [{"id": 4450, "name": "partner-4450"}],
        ]
        sdks = {"partner": partner_sdk}

        MultiTenantBusinessScenarioFactory._assert_list_contains(
            sdks,
            "partner",
            4450,
            "t001",
        )

        partner_sdk.filter_partner.assert_called_once_with(
            {"id": 4450, "page": 1, "size": 20}
        )

    def test_test_runner(self):
        """测试运行器"""
        logger.info("测试运行器")

        self.assertTrue(os.path.exists("run_tests.py"), "统一测试入口不存在")

        with open("run_tests.py", "r") as f:
            content = f.read()

        self.assertIn("def run_", content)
        self.assertIn("--validation", content)
        self.assertIn("--multi-tenant", content)
        self.assertIn("--quick", content)
        self.assertIn("--all", content)
        self.assertIn("--hotspot", content)
        self.assertIn("--goods-hotspot", content)
        self.assertIn("--report-file", content)
        self.assertIn("--request-application", content)

        logger.info("测试运行器测试通过")

    @patch.dict(os.environ, {"MAGICTEST_REQUEST_APPLICATION": "perf-run-verify"}, clear=False)
    @patch("session_manager.Cas")
    @patch("session_manager.MagicSession")
    def test_session_manager_binds_request_application(self, mock_session_cls, mock_cas_cls):
        """测试 SessionManager 会绑定 request_application 头"""
        from session_manager import SessionManager

        mock_session = Mock()
        mock_session_cls.return_value = mock_session
        mock_cas = Mock()
        mock_cas.login.return_value = True
        mock_cas.get_session_token.return_value = "token"
        mock_cas_cls.return_value = mock_cas

        manager = SessionManager(
            server_url="https://autotest.remote.vpc",
            namespace="",
            username="administrator",
            password="administrator",
        )
        self.assertTrue(manager.create_session())
        mock_session.bind_application.assert_called_once_with("perf-run-verify")

    @patch("session_manager.Cas")
    @patch("session_manager.MagicSession")
    def test_session_manager_create_session_failure_does_not_expose_unauthed_session(
        self, mock_session_cls, mock_cas_cls
    ):
        """测试登录失败时不会留下未认证 session 给业务线程复用。"""
        from session_manager import SessionManager

        failed_session = Mock()
        mock_session_cls.return_value = failed_session
        failed_cas = Mock()
        failed_cas.login.return_value = False
        failed_cas.get_session_token.return_value = None
        mock_cas_cls.return_value = failed_cas

        manager = SessionManager(
            server_url="https://autotest.remote.vpc",
            namespace="",
            username="administrator",
            password="administrator",
        )
        self.assertFalse(manager.create_session())
        self.assertIsNone(manager.work_session)
        self.assertIsNone(manager.cas_session)
        self.assertIsNone(manager.get_session())
        failed_session.close.assert_called_once()

    @patch("session_manager.Cas")
    @patch("session_manager.MagicSession")
    def test_session_manager_refresh_failure_reconnects_in_refresh_thread(
        self, mock_session_cls, mock_cas_cls
    ):
        """测试刷新线程内 refresh 失败后可安全重登，不会自 join 卡死。"""
        from session_manager import SessionManager

        first_session = Mock()
        first_session.sync_from = Mock()
        second_session = Mock()
        mock_session_cls.side_effect = [first_session, second_session]

        first_cas = Mock()
        first_cas.login.return_value = True
        first_cas.get_session_token.return_value = "token-1"
        first_cas.refresh.return_value = None

        second_cas = Mock()
        second_cas.login.return_value = True
        second_cas.get_session_token.return_value = "token-2"

        mock_cas_cls.side_effect = [first_cas, second_cas]

        manager = SessionManager(
            server_url="https://autotest.remote.vpc",
            namespace="",
            username="administrator",
            password="administrator",
        )
        self.assertTrue(manager.create_session())

        manager.refresh_thread = unittest.mock.Mock()
        manager.refresh_thread.is_alive.return_value = True
        manager.refresh_thread.__eq__ = Mock(return_value=False)
        # 将当前线程伪装成 refresh_thread 上下文，覆盖自 join 风险路径。
        manager.refresh_thread = unittest.mock.sentinel.refresh_thread

        with patch("session_manager.threading.current_thread", return_value=manager.refresh_thread):
            self.assertTrue(manager.refresh_session())

        self.assertTrue(manager.is_logged_in)
        self.assertIs(manager.work_session, first_session)
        first_session.sync_from.assert_called_once_with(second_session)
        second_session.close.assert_called_once()

    @patch("session_manager.Cas")
    @patch("session_manager.MagicSession")
    def test_session_manager_get_session_hides_unauthed_session(
        self, mock_session_cls, mock_cas_cls
    ):
        """测试 get_session 不会返回缺少认证信息的 session。"""
        from session_manager import SessionManager

        mock_session = Mock()
        mock_session.session_token = None
        mock_session.session_auth_endpoint = None
        mock_session.session_auth_token = None
        mock_session_cls.return_value = mock_session
        mock_cas = Mock()
        mock_cas.login.return_value = True
        mock_cas.get_session_token.return_value = None
        mock_cas_cls.return_value = mock_cas

        manager = SessionManager(
            server_url="https://autotest.remote.vpc",
            namespace="",
            username="administrator",
            password="administrator",
        )
        self.assertFalse(manager.create_session())
        self.assertIsNone(manager.get_session())

    def test_cas_refresh_uses_temporary_session_without_polluting_shared_session(self):
        """测试 refresh 失败时不会把共享业务 session 置为旧 token。"""
        from cas import Cas

        shared_session = Mock()
        refresh_session = Mock()
        shared_session.new_session.return_value = refresh_session
        refresh_session.get.return_value = {
            "error": {"code": 401, "message": "expired"}
        }

        cas_client = Cas(shared_session)
        cas_client.session_token = "live-token"

        self.assertIsNone(cas_client.refresh("expired-token"))
        shared_session.bind_token.assert_not_called()
        refresh_session.bind_token.assert_called_once_with("expired-token")
        refresh_session.close.assert_called_once()

    def test_cas_refresh_updates_shared_session_only_after_success(self):
        """测试 refresh 成功后才回写共享业务 session 的新 token。"""
        from cas import Cas

        shared_session = Mock()
        refresh_session = Mock()
        shared_session.new_session.return_value = refresh_session
        refresh_session.get.return_value = {
            "value": {
                "sessionToken": "new-token",
                "entity": {"id": 1, "name": "tenant-admin"},
            }
        }

        cas_client = Cas(shared_session)
        cas_client.session_token = "old-token"

        self.assertEqual(cas_client.refresh("old-token"), "new-token")
        refresh_session.bind_token.assert_called_once_with("old-token")
        shared_session.sync_cookies_from.assert_called_once_with(refresh_session)
        shared_session.bind_token.assert_called_once_with("new-token")
        refresh_session.close.assert_called_once()

    def test_magic_session_sync_from_keeps_header_state_consistent(self):
        """测试 MagicSession.sync_from 后 header 使用的是同一份认证快照。"""
        from session import MagicSession

        source = MagicSession("https://autotest.local.vpc", "")
        source.bind_auth_secret("/api/v1/cas/session/login/", "sig-token")
        source.bind_application("perf-run-001")
        source.bind_source("perf-run-001")

        target = MagicSession("https://stale.local.vpc", "legacy")
        target.bind_token("old-token")
        target.bind_application("legacy-app")

        target.sync_from(source)

        headers = target.header()
        self.assertEqual(
            headers.get("Authorization"),
            "Sig Credential=/api/v1/cas/session/login/,Signature=sig-token",
        )
        self.assertEqual(headers.get("X-Mp-Application"), "perf-run-001")
        self.assertEqual(headers.get("X-Mp-Source"), "perf-run-001")
        self.assertNotIn("X-Mp-Namespace", headers)

    def test_magic_session_new_session_copies_current_auth_snapshot(self):
        """测试 new_session 会复制当前认证快照。"""
        from session import MagicSession

        session = MagicSession("https://autotest.local.vpc", "")
        session.bind_token("bearer-token")
        session.bind_application("perf-run-002")
        session.bind_source("perf-run-002")
        session.current_session.cookies.set("session_token", "cookie-token", domain="autotest.local.vpc", path="/")

        cloned = session.new_session()
        headers = cloned.header()

        self.assertEqual(headers.get("Authorization"), "Bearer bearer-token")
        self.assertEqual(headers.get("X-Mp-Application"), "perf-run-002")
        self.assertEqual(headers.get("X-Mp-Source"), "perf-run-002")
        self.assertEqual(cloned.current_session.cookies.get("session_token"), "cookie-token")

    def test_magic_session_sync_from_copies_cookie_jar(self):
        """测试 sync_from 会同步 cookie jar，避免 refresh 后继续携带旧 cookie。"""
        from session import MagicSession

        source = MagicSession("https://autotest.local.vpc", "")
        source.bind_token("new-bearer-token")
        source.current_session.cookies.set("session_token", "new-cookie-token", domain="autotest.local.vpc", path="/")

        target = MagicSession("https://autotest.local.vpc", "")
        target.bind_token("old-bearer-token")
        target.current_session.cookies.set("session_token", "old-cookie-token", domain="autotest.local.vpc", path="/")

        target.sync_from(source)

        self.assertEqual(target.current_session.cookies.get("session_token"), "new-cookie-token")

    @patch("concurrent_test_v2._query_prometheus")
    def test_prometheus_summary_marks_application_override(self, mock_query_prometheus):
        """测试 Prometheus 摘要会显式标记 request_application 未被保留"""
        from concurrent_test_v2 import build_prometheus_summary

        def fake_query(_prometheus_url, query):
            if 'application="perf-run-verify"' in query and "http_requests_total" in query:
                return {"result": []}
            if 'application="perf-run-verify"' in query and "http_transactions_total" in query:
                return {"result": []}
            if 'application="perf-run-verify"' in query and "sum by (path)" in query:
                return {"result": []}
            if query == "up":
                return {
                    "result": [
                        {"metric": {"job": "magicbase", "instance": "magicbase:9090"}, "value": [0, "1"]},
                    ]
                }
            if "sum by (job, instance) (magicBase_magicbase_http_requests_total)" in query:
                return {
                    "result": [
                        {"metric": {"job": "magicbase", "instance": "magicbase:9090"}, "value": [0, "20"]},
                    ]
                }
            if "sum by (job, instance) (magicBase_magicorm_orm_operations_total)" in query:
                return {
                    "result": [
                        {"metric": {"job": "magicbase", "instance": "magicbase:9090"}, "value": [0, "12"]},
                    ]
                }
            if "sum by (application, path)" in query:
                return {
                    "result": [
                        {
                            "metric": {
                                "application": "svc-app-001",
                                "path": "/api/v1/public/value/vmi/store/filter",
                            },
                            "value": [0, "12"],
                        },
                        {
                            "metric": {
                                "application": "svc-app-001",
                                "path": "/api/v1/public/value/vmi/store/query/:id",
                            },
                            "value": [0, "5"],
                        },
                        {
                            "metric": {
                                "application": "svc-app-002",
                                "path": "/api/v1/value/filter",
                            },
                            "value": [0, "3"],
                        },
                    ]
                }
            if "magicBase_magicorm_orm_operations_total" in query:
                return {"result": [{"value": [0, "12"]}]}
            if "magicBase_magicorm_database_queries_total" in query:
                return {"result": [{"value": [0, "18"]}]}
            if "magicBase_magicorm_database_executions_total" in query:
                return {"result": [{"value": [0, "6"]}]}
            if "sum(increase(magicBase_magicbase_http_requests_total[10m]))" in query:
                return {"result": [{"value": [0, "20"]}]}
            self.fail(f"unexpected query: {query}")

        mock_query_prometheus.side_effect = fake_query

        summary = build_prometheus_summary(
            {
                "request_application": "perf-run-verify",
                "prometheus_window": "10m",
                "observability": {
                    "prometheus_url": "https://apm.remote.vpc/prometheus/"
                },
            }
        )

        self.assertIsNotNone(summary)
        self.assertFalse(summary["application_label_retained"])
        self.assertEqual(summary["correlation_mode"], "service_application_override")
        self.assertEqual(summary["observed_application"], "svc-app-001")
        self.assertAlmostEqual(summary["observed_application_share"], 17 / 20)
        self.assertEqual(
            summary["scrape_targets_up"],
            [{"job": "magicbase", "instance": "magicbase:9090", "value": 1.0}],
        )
        self.assertIn("coverage_note", summary)
        self.assertEqual(
            summary["top_application_totals_unfiltered"],
            [
                {"application": "svc-app-001", "value": 17.0},
                {"application": "svc-app-002", "value": 3.0},
            ],
        )

    def test_integration(self):
        """测试集成"""
        logger.info("测试集成")

        try:
            from multi_tenant_manager import MultiTenantSessionManager
            from tenant_config_helper import get_multi_tenant_config

            config = get_multi_tenant_config()

            self.assertIsInstance(config, dict)
            self.assertIn("tenants", config)

            with patch("session_manager.SessionManager"):
                test_config = {
                    "autotest": {
                        "server_url": "https://autotest.local.vpc",
                        "username": "admin",
                        "password": "password",
                        "namespace": "autotest",
                        "enabled": True,
                    }
                }

                mt_manager = MultiTenantSessionManager(test_config)
                self.assertIn("autotest", mt_manager.session_managers)

            logger.info("集成测试通过")
        except Exception as e:
            self.fail(f"集成测试失败: {e}")

    def test_http_request_metrics_collects_host_distribution(self):
        from concurrent_test_v2 import HTTPRequestMetricsCollector

        collector = HTTPRequestMetricsCollector()
        collector.observe(
            method="GET",
            url="/api/v1/vmi/stores/",
            full_url="https://t001.remote.vpc/api/v1/vmi/stores/",
            elapsed=0.2,
            status_code=200,
            response={"error": None, "values": []},
        )
        collector.observe(
            method="POST",
            url="/api/v1/vmi/stores/",
            full_url="https://t002.local.vpc/api/v1/vmi/stores/",
            elapsed=0.3,
            status_code=200,
            response={"error": None, "value": {"id": 1}},
        )

        snapshot = collector.snapshot(total_time=1.0)
        self.assertEqual(snapshot["http_requests"], 2)
        self.assertEqual(snapshot["http_remote_requests"], 1)
        self.assertEqual(snapshot["http_local_requests"], 1)
        self.assertEqual(
            snapshot["http_host_distribution"],
            [
                {"host": "t001.remote.vpc", "count": 1},
                {"host": "t002.local.vpc", "count": 1},
            ],
        )


def run_validation():
    """运行验证测试"""
    logger.info("=" * 60)
    logger.info("VMI 测试框架 - 验证测试")
    logger.info("=" * 60)

    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestFrameworkValidation)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    logger.info("=" * 60)
    logger.info("验证结果摘要")
    logger.info("=" * 60)

    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)

    logger.info("总测试数: %s", total)
    logger.info("通过数: %s", passed)
    logger.info("失败数: %s", len(result.failures))

    if result.wasSuccessful():
        logger.info("所有验证测试通过")
        logger.info("框架验证清单:")
        logger.info("1. 配置系统正常")
        logger.info("2. 模块导入正常")
        logger.info("3. 配置助手正常")
        logger.info("4. 多租户管理器正常")
        logger.info("5. 测试基类正常")
        logger.info("6. 运行时入口完整")
        logger.info("7. 测试运行器正常")
        logger.info("8. 集成测试正常")
        return True

    logger.error("部分测试失败")
    if result.failures:
        for test, _traceback in result.failures:
            logger.error("失败: %s", test)
    if result.errors:
        for test, _traceback in result.errors:
            logger.error("错误: %s", test)
    return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = run_validation()
    exit(0 if success else 1)
