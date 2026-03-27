#!/usr/bin/env python3
"""
pytest配置文件 - 定义核心fixtures

这个文件包含所有测试共享的fixtures，包括：
1. 会话管理fixtures
2. SDK客户端fixtures
3. 测试数据工厂
4. 配置和工具fixtures
"""

import logging
import random
import time
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, Optional

import pytest

# 配置日志
logger = logging.getLogger(__name__)


def _pick_status_ref(statuses) -> Dict[str, Any]:
    """从状态列表中选择优先可用状态。"""
    preferred_names = {"启用", "已启用", "正常", "active", "enabled"}
    preferred_names_lower = {value.lower() for value in preferred_names}
    for item in statuses:
        name = str(item.get("name", "")).strip().lower()
        if name in preferred_names_lower and item.get("id"):
            return {"id": int(item["id"]), "name": item.get("name", "")}

    if statuses and statuses[0].get("id"):
        return {"id": int(statuses[0]["id"]), "name": statuses[0].get("name", "")}

    return {}


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """测试配置fixture - 从统一配置文件读取"""
    from config_helper import (get_aging_params, get_concurrent_config, get_config,
                               get_credentials, get_namespace, get_server_url,
                               get_session_config)

    cfg = get_config()
    session_cfg = get_session_config()

    config = {
        "mode": cfg.get("mode", "single_tenant"),
        "environment": cfg.get("environment", "local"),
        "server_url": get_server_url(),
        "namespace": get_namespace(),
        "credentials": get_credentials(),
        "refresh_interval": session_cfg.get("refresh_interval", 540),
        "session_timeout": session_cfg.get("timeout", 1800),
        "pytest": cfg.get("pytest", {}),
        "concurrent": get_concurrent_config(),
        "aging": get_aging_params(),
    }

    logger.info(f"测试配置加载完成 - 服务器: {config['server_url']}")
    return config


@pytest.fixture(scope="session")
def session_manager(test_config) -> Generator:
    """全局会话管理器fixture - 会话级别

    提供自动会话刷新功能，9分钟刷新一次
    """
    from session_manager import SessionManager

    logger.info("初始化全局会话管理器")

    mgr = SessionManager(
        server_url=test_config["server_url"],
        namespace=test_config["namespace"],
        username=test_config["credentials"]["username"],
        password=test_config["credentials"]["password"],
        refresh_interval=test_config["refresh_interval"],
        session_timeout=test_config["session_timeout"],
    )

    # 创建会话
    if not mgr.create_session():
        pytest.fail("创建会话失败")

    # 启动自动刷新
    mgr.start_auto_refresh()

    logger.info("会话管理器初始化完成，自动刷新已启动")

    yield mgr

    # 清理
    logger.info("清理会话管理器")
    mgr.stop_auto_refresh()
    mgr.close_session()


@pytest.fixture(scope="session")
def work_session(session_manager) -> Any:
    """工作会话fixture - 会话级别"""
    session = session_manager.get_session()
    if not session:
        pytest.fail("获取工作会话失败")
    return session


@pytest.fixture(scope="session")
def cas_session(session_manager) -> Any:
    """CAS会话fixture - 会话级别"""
    session = session_manager.get_cas_session()
    if not session:
        pytest.fail("获取CAS会话失败")
    return session


@pytest.fixture(scope="session")
def sdk_clients(work_session) -> Dict[str, Any]:
    """SDK客户端fixture - 会话级别

    返回所有SDK客户端的字典
    """
    try:
        from sdk import (GoodsInfoSDK, GoodsSDK, PartnerSDK, ProductInfoSDK,
                         ProductSDK, ShelfSDK, StatusSDK, StockinSDK,
                         StockoutSDK, StoreSDK, WarehouseSDK)

        clients = {
            "status": StatusSDK(work_session),
            "warehouse": WarehouseSDK(work_session),
            "shelf": ShelfSDK(work_session),
            "store": StoreSDK(work_session),
            "product": ProductSDK(work_session),
            "product_info": ProductInfoSDK(work_session),
            "partner": PartnerSDK(work_session),
            "goods": GoodsSDK(work_session),
            "goods_info": GoodsInfoSDK(work_session),
            "stockin": StockinSDK(work_session),
            "stockout": StockoutSDK(work_session),
        }

        logger.debug("SDK客户端初始化完成")
        return clients

    except ImportError as e:
        pytest.fail(f"导入SDK失败: {e}")
    except Exception as e:
        pytest.fail(f"初始化SDK客户端失败: {e}")


@pytest.fixture(scope="session")
def resource_context(sdk_clients) -> Generator[Dict[str, Any], None, None]:
    """为公共测试数据工厂准备真实依赖资源。"""
    created_entities = {
        "goods_info": [],
        "product_info": [],
        "product": [],
        "store": [],
        "shelf": [],
        "warehouse": [],
    }

    status_list = sdk_clients["status"].filter_status({"page": 1, "size": 100}) or []
    status_ref = _pick_status_ref(
        [item for item in status_list if isinstance(item, dict) and item.get("id")]
    )
    if not status_ref:
        pytest.fail("无法获取可用状态，公共测试资源初始化失败")

    suffix = uuid.uuid4().hex[:8]

    warehouse = sdk_clients["warehouse"].create_warehouse(
        {
            "name": f"PYTEST_WH_{suffix}",
            "description": f"pytest公共仓库_{suffix}",
        }
    )
    if not warehouse or "id" not in warehouse:
        pytest.fail("创建公共仓库失败")
    created_entities["warehouse"].append(int(warehouse["id"]))

    shelf = sdk_clients["shelf"].create_shelf(
        {
            "description": f"pytest公共货架_{suffix}",
            "capacity": 200,
            "warehouse": {"id": int(warehouse["id"])},
            "status": {"id": int(status_ref["id"])},
        }
    )
    if not shelf or "id" not in shelf:
        pytest.fail("创建公共货架失败")
    created_entities["shelf"].append(int(shelf["id"]))

    store = sdk_clients["store"].create_store(
        {
            "name": f"PYTEST_STORE_{suffix}",
            "description": f"pytest公共店铺_{suffix}",
        }
    )
    if not store or "id" not in store:
        pytest.fail("创建公共店铺失败")
    created_entities["store"].append(int(store["id"]))

    product = sdk_clients["product"].create_product(
        {
            "name": f"PYTEST_PRODUCT_{suffix}",
            "description": f"pytest公共产品_{suffix}",
            "image": [],
            "expire": 180,
            "tags": ["pytest", "shared"],
            "status": {"id": int(status_ref["id"])},
        }
    )
    if not product or "id" not in product:
        pytest.fail("创建公共产品失败")
    created_entities["product"].append(int(product["id"]))

    product_info = sdk_clients["product_info"].create_product_info(
        {
            "sku": f"9{int(time.time() * 1000) % 100000000}{random.randint(10, 99)}",
            "description": f"pytest公共产品SKU_{suffix}",
            "product": {"id": int(product["id"])},
        }
    )
    if not product_info or "id" not in product_info:
        pytest.fail("创建公共产品SKU失败")
    created_entities["product_info"].append(int(product_info["id"]))

    goods_info = sdk_clients["goods_info"].create_goods_info(
        {
            "sku": f"8{int(time.time() * 1000) % 100000000}{random.randint(10, 99)}",
            "product": {"id": int(product_info["id"])},
            "type": 1,
            "count": 100,
            "price": 99.99,
            "shelf": [{"id": int(shelf["id"])}],
        }
    )
    if not goods_info or "id" not in goods_info:
        pytest.fail("创建公共商品SKU失败")
    created_entities["goods_info"].append(int(goods_info["id"]))

    context = {
        "status": {"id": int(status_ref["id"])},
        "warehouse": {"id": int(warehouse["id"])},
        "shelf": {"id": int(shelf["id"])},
        "store": {"id": int(store["id"])},
        "product": {"id": int(product["id"])},
        "product_info": {"id": int(product_info["id"])},
        "goods_info": {
            "id": int(goods_info["id"]),
            "sku": goods_info.get("sku", ""),
            "product": {"id": int(product_info["id"])},
            "type": int(goods_info.get("type", 1)),
            "count": int(goods_info.get("count", 100)),
            "price": float(goods_info.get("price", 99.99)),
            "shelf": goods_info.get("shelf") or [{"id": int(shelf["id"])}],
        },
    }

    yield context

    cleanup_plan = [
        ("goods_info", "delete_goods_info"),
        ("product_info", "delete_product_info"),
        ("product", "delete_product"),
        ("store", "delete_store"),
        ("shelf", "delete_shelf"),
        ("warehouse", "delete_warehouse"),
    ]
    for entity_type, method_name in cleanup_plan:
        sdk = sdk_clients.get(entity_type)
        if not sdk:
            continue
        for entity_id in reversed(created_entities[entity_type]):
            try:
                getattr(sdk, method_name)(int(entity_id))
            except Exception as exc:
                logger.warning("清理公共资源 %s(%s) 失败: %s", entity_type, entity_id, exc)


@pytest.fixture
def ensure_session_valid(session_manager) -> bool:
    """确保会话有效的fixture - 函数级别

    在每个测试前检查会话状态，如果无效则尝试恢复
    """
    from session_manager import ensure_session_valid as esv

    if not esv(session_manager):
        logger.warning("会话无效，尝试重新连接")
        if session_manager.reconnect():
            logger.info("会话重新连接成功")
            return True
        else:
            pytest.fail("会话重新连接失败")

    # 更新活动时间
    session_manager.update_activity()
    return True


@pytest.fixture
def execute_with_session_check(session_manager, ensure_session_valid):
    """带会话检查的执行fixture - 函数级别

    包装操作函数，自动处理会话检查和重试
    """

    def _execute(operation_func, *args, **kwargs):
        # 确保会话有效
        if not ensure_session_valid:
            pytest.fail("会话无效且无法恢复，操作中止")

        try:
            # 执行操作
            result = operation_func(*args, **kwargs)

            # 更新活动时间
            session_manager.update_activity()

            return result

        except Exception as e:
            # 检查是否是会话超时错误
            error_msg = str(e).lower()
            session_errors = [
                "session",
                "token",
                "auth",
                "login",
                "unauthorized",
                "timeout",
            ]

            if any(error in error_msg for error in session_errors):
                logger.warning(f"操作可能因会话问题失败: {e}")

                # 尝试重新连接并重试
                logger.info("尝试重新连接并重试操作")
                if session_manager.reconnect():
                    # 重试操作
                    try:
                        result = operation_func(*args, **kwargs)
                        session_manager.update_activity()
                        logger.info("重试操作成功")
                        return result
                    except Exception as retry_error:
                        logger.error(f"重试操作失败: {retry_error}")
                        raise retry_error
                else:
                    logger.error("重新连接失败")
                    raise e
            else:
                # 其他错误，直接抛出
                raise e

    return _execute


# 测试数据工厂fixtures
@pytest.fixture
def random_partner_data(resource_context) -> Dict[str, Any]:
    """随机合作伙伴数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)

    return {
        "name": f"测试合作伙伴_{timestamp}_{random_id}",
        "telephone": f"138{random.randint(10000000, 99999999)}",
        "wechat": f"wechat_{random_id}",
        "description": f"测试合作伙伴描述_{timestamp}",
        "status": resource_context["status"],
    }


@pytest.fixture
def random_product_data(resource_context) -> Dict[str, Any]:
    """随机产品数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)

    return {
        "name": f"测试产品_{timestamp}_{random_id}",
        "description": f"测试产品描述_{timestamp}",
        "image": [],
        "expire": random.randint(30, 365),
        "tags": ["pytest", f"tag-{random_id}"],
        "status": resource_context["status"],
    }


@pytest.fixture
def random_goods_data(resource_context) -> Dict[str, Any]:
    """随机商品数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)

    return {
        "name": f"测试商品_{timestamp}_{random_id}",
        "sku": f"SKU_{random_id:04d}_{timestamp}",
        "price": round(random.uniform(5.0, 500.0), 2),
        "count": random.randint(1, 1000),
        "description": f"测试商品描述_{timestamp}",
        "parameter": f"参数_{random_id}",
        "serviceInfo": f"服务信息_{timestamp}",
        "status": resource_context["status"],
        "product": resource_context["product_info"],
        "shelf": [resource_context["shelf"]],
        "store": resource_context["store"],
    }


@pytest.fixture
def random_stockin_data(resource_context) -> Dict[str, Any]:
    """随机入库数据工厂"""
    timestamp = int(time.time())
    goods_info_ref = dict(resource_context["goods_info"])
    goods_info_ref["count"] = random.randint(1, 100)
    goods_info_ref["price"] = round(random.uniform(5.0, 500.0), 2)
    goods_info_ref["type"] = 1

    return {
        "goodsInfo": [goods_info_ref],
        "description": f"测试入库_{timestamp}",
        "status": resource_context["status"],
        "store": resource_context["store"],
    }


@pytest.fixture
def random_stockout_data(resource_context) -> Dict[str, Any]:
    """随机出库数据工厂"""
    timestamp = int(time.time())
    goods_info_ref = dict(resource_context["goods_info"])
    goods_info_ref["count"] = random.randint(1, 50)
    goods_info_ref["price"] = round(random.uniform(5.0, 500.0), 2)
    goods_info_ref["type"] = 2

    return {
        "goodsInfo": [goods_info_ref],
        "description": f"测试出库_{timestamp}",
        "status": resource_context["status"],
        "store": resource_context["store"],
    }


@pytest.fixture
def entity_cleanup(sdk_clients) -> Generator:
    """实体清理fixture - 函数级别

    自动清理测试创建的实体
    """
    created_entities = {
        "partner": [],
        "product": [],
        "product_info": [],
        "goods": [],
        "goods_info": [],
        "store": [],
        "shelf": [],
        "warehouse": [],
        "stockin": [],
        "stockout": [],
    }

    yield created_entities

    # 测试结束后清理实体
    logger.info("清理测试创建的实体")

    cleanup_order = [
        "stockin",
        "stockout",
        "goods",
        "goods_info",
        "product_info",
        "product",
        "store",
        "shelf",
        "warehouse",
        "partner",
    ]
    for entity_type in cleanup_order:
        entity_ids = created_entities.get(entity_type) or []
        if not entity_ids:
            continue

        sdk_client = sdk_clients.get(entity_type)
        if not sdk_client:
            continue

        for entity_id in entity_ids:
            try:
                if entity_type == "partner":
                    sdk_client.delete_partner(int(entity_id))
                elif entity_type == "product":
                    sdk_client.delete_product(int(entity_id))
                elif entity_type == "product_info":
                    sdk_client.delete_product_info(int(entity_id))
                elif entity_type == "goods":
                    sdk_client.delete_goods(int(entity_id))
                elif entity_type == "goods_info":
                    sdk_client.delete_goods_info(int(entity_id))
                elif entity_type == "store":
                    sdk_client.delete_store(int(entity_id))
                elif entity_type == "shelf":
                    sdk_client.delete_shelf(int(entity_id))
                elif entity_type == "warehouse":
                    sdk_client.delete_warehouse(int(entity_id))
                elif entity_type == "stockin":
                    sdk_client.delete_stockin(int(entity_id))
                elif entity_type == "stockout":
                    sdk_client.delete_stockout(int(entity_id))

                logger.debug(f"清理 {entity_type} ID: {entity_id}")
            except Exception as e:
                logger.warning(f"清理 {entity_type} ID: {entity_id} 失败: {e}")


@pytest.fixture
def performance_monitor():
    """性能监控fixture - 函数级别"""
    from test_base_with_session_manager import PerformanceMonitor

    monitor = PerformanceMonitor()
    monitor.start()

    yield monitor

    monitor.stop()


# 自定义pytest钩子
def pytest_sessionstart(session):
    """测试会话开始时调用"""
    logger.info("=" * 60)
    logger.info("VMI测试会话开始")
    logger.info("=" * 60)


def pytest_sessionfinish(session, exitstatus):
    """测试会话结束时调用"""
    logger.info("=" * 60)
    logger.info(f"VMI测试会话结束 - 退出状态: {exitstatus}")
    logger.info("=" * 60)


def pytest_runtest_logstart(nodeid, location):
    """测试开始运行时调用"""
    test_name = nodeid.split("::")[-1]
    logger.info(f"开始测试: {test_name}")


def pytest_runtest_logfinish(nodeid, location):
    """测试结束运行时调用"""
    test_name = nodeid.split("::")[-1]
    logger.info(f"结束测试: {test_name}")
