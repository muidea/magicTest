#!/usr/bin/env python3
"""
简化版长期老化测试运行器

用于持续处理partner, product, stockin, stockout, goods CRUD业务，
检验服务器运行稳定性，具备并发性和持续性。

主要功能：
1. 并发测试：多线程同时执行不同业务操作
2. 持续测试：长时间运行，模拟真实业务场景
3. 数据量限制：业务总数据量不超过1000万条
4. 性能劣化跟踪：监控接口执行时间是否存在劣化
"""

import json
import logging
import os
import random
import statistics
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 配置日志
LOG_LEVEL = os.getenv("VMI_TEST_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class AgingTestConfig:
    """老化测试配置"""

    def __init__(self, config=None):
        # 导入配置助手
        from config_helper import get_aging_params, get_tenant_targets

        # 获取老化测试配置
        aging_config = get_aging_params()

        # 测试持续时间（小时）
        self.duration_hours = aging_config.get("duration_hours", 480)
        # 并发线程数
        self.concurrent_threads = aging_config.get("concurrent_threads", 10)
        # 操作间隔（秒）
        self.operation_interval = aging_config.get("operation_interval", 1.0)
        # 最大数据量（万条）
        self.max_data_count = aging_config.get(
            "max_data_count", 1000
        )  # 1000万条 = 10,000,000条
        # 性能劣化阈值（百分比）
        self.performance_degradation_threshold = aging_config.get(
            "performance_degradation_threshold", 20.0
        )  # 20%性能下降
        # 性能监控窗口大小（操作数）
        self.performance_window_size = 100
        # 报告生成间隔（分钟）
        self.report_interval_minutes = aging_config.get("report_interval_minutes", 30)
        # 是否启用多租户全业务链路老化模式
        self.multi_tenant_business_flow_enabled = aging_config.get(
            "multi_tenant_business_flow_enabled", False
        )
        # 多租户老化目标租户统一来自顶层 tenant_targets，可由 CLI 临时覆盖
        self.target_tenants = get_tenant_targets()

        # 保存原始配置引用（如果提供）
        self.config = config


class AgingTestWorker:
    """老化测试工作线程"""

    def __init__(self, worker_id: int, config: AgingTestConfig):
        self.worker_id = worker_id
        self.config = config
        self.results = []
        self.running = False
        self.entity_cache = {
            "partner": [],
            "product": [],
            "goods": [],
            "stockin": [],
            "stockout": [],
        }
        # 性能监控窗口
        self.performance_window = []
        self.baseline_performance = None
        # 错误统计
        self.error_counts = {
            "total": 0,
            "by_entity": {
                "partner": 0,
                "product": 0,
                "goods": 0,
                "stockin": 0,
                "stockout": 0,
            },
            "by_operation": {
                "create": 0,
                "read": 0,
                "update": 0,
                "delete": 0,
                "list": 0,
            },
        }
        # 重试配置
        self.max_retries = 3
        self.retry_delay = 1.0  # 秒
        self.skipped_operations = 0
        self.bootstrap_resources = {}

    def run(self, stop_event: threading.Event):
        """运行测试工作线程"""
        self.running = True
        logger.info(f"工作线程 {self.worker_id} 启动")

        try:
            # 导入SDK
            import os
            import sys

            # 添加项目根目录到路径
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)

            # 导入配置助手
            from config_helper import get_credentials, get_server_url
            from sdk import (GoodsInfoSDK, GoodsSDK, PartnerSDK, ProductInfoSDK,
                             ProductSDK, ShelfSDK, StatusSDK, StockinSDK,
                             StockoutSDK, StoreSDK, WarehouseSDK)
            from session_manager import SessionManager

            # 初始化会话管理器
            server_url = get_server_url()
            credentials = get_credentials()

            # 创建会话管理器（9分钟刷新一次，符合服务器要求）
            self.session_manager = SessionManager(
                server_url=server_url,
                namespace="",
                username=credentials["username"],
                password=credentials["password"],
                refresh_interval=540,  # 9分钟刷新一次
                session_timeout=1800,  # 30分钟会话超时
            )

            # 创建会话
            if not self.session_manager.create_session():
                logger.error(f"工作线程 {self.worker_id}: 创建会话失败")
                return

            # 启动自动刷新
            self.session_manager.start_auto_refresh()

            # 获取会话对象
            work_session = self.session_manager.get_session()

            # 初始化SDK
            self.partner_sdk = PartnerSDK(work_session)
            self.product_sdk = ProductSDK(work_session)
            self.product_info_sdk = ProductInfoSDK(work_session)
            self.goods_sdk = GoodsSDK(work_session)
            self.goods_info_sdk = GoodsInfoSDK(work_session)
            self.stockin_sdk = StockinSDK(work_session)
            self.stockout_sdk = StockoutSDK(work_session)
            self.status_sdk = StatusSDK(work_session)
            self.warehouse_sdk = WarehouseSDK(work_session)
            self.shelf_sdk = ShelfSDK(work_session)
            self.store_sdk = StoreSDK(work_session)

            if not self._bootstrap_resources():
                logger.error(f"工作线程 {self.worker_id}: 初始化依赖资源失败")
                return

            # 运行测试循环
            while self.running and not stop_event.is_set():
                try:
                    # 随机选择实体类型（现在测试所有五种实体）
                    entity_types = [
                        "partner",
                        "product",
                        "goods",
                        "stockin",
                        "stockout",
                    ]
                    entity_type = random.choice(entity_types)

                    # 随机选择操作类型
                    # 注意：对于stockin和stockout，跳过update操作（服务器端API问题）
                    if entity_type in ["stockin", "stockout"]:
                        operation_types = ["create", "read", "delete", "list"]
                    else:
                        operation_types = ["create", "read", "update", "delete", "list"]
                    operation_type = random.choice(operation_types)

                    if (
                        operation_type == "delete"
                        and not self.entity_cache[entity_type]
                    ):
                        self.skipped_operations += 1
                        time.sleep(self.config.operation_interval)
                        continue

                    # 执行操作（带重试机制）
                    start_time = time.time()
                    attempt_duration_total = 0.0
                    backoff_duration_total = 0.0
                    attempt_count = 0
                    success = False
                    error = None
                    result = None

                    # 重试逻辑
                    for retry_count in range(self.max_retries + 1):
                        try:
                            attempt_start_time = time.time()
                            attempt_count += 1
                            # 在执行操作前检查会话
                            if (
                                hasattr(self, "session_manager")
                                and self.session_manager
                            ):
                                # 更新活动时间
                                self.session_manager.update_activity()

                                # 检查会话是否有效
                                if not self.session_manager.is_session_valid():
                                    logger.warning(
                                        f"工作线程 {self.worker_id}: 会话无效，尝试刷新"
                                    )
                                    if not self.session_manager.refresh_session():
                                        logger.warning(
                                            f"工作线程 {self.worker_id}: 会话刷新失败，尝试重新登录"
                                        )
                                        if not self.session_manager.reconnect():
                                            logger.error(
                                                f"工作线程 {self.worker_id}: 重新登录失败"
                                            )
                                            # 继续尝试操作，可能会失败但会触发重试机制

                            if operation_type == "create":
                                result = self._create_entity(entity_type)
                            elif operation_type == "read":
                                result = self._read_entity(entity_type)
                            elif operation_type == "update":
                                result = self._update_entity(entity_type)
                            elif operation_type == "delete":
                                result = self._delete_entity(entity_type)
                            elif operation_type == "list":
                                result = self._list_entities(entity_type)
                            else:
                                raise ValueError(f"未知操作类型: {operation_type}")
                            attempt_duration_total += time.time() - attempt_start_time

                            success = result is not None
                            if success:
                                break  # 成功，跳出重试循环
                            elif retry_count < self.max_retries:
                                # 记录更多信息帮助调试
                                # 对于缓存为空的delete操作，降低日志级别
                                if (
                                    operation_type == "delete"
                                    and not self.entity_cache[entity_type]
                                ):
                                    logger.debug(
                                        f"工作线程 {self.worker_id} {entity_type}.{operation_type} 操作跳过（缓存为空）"
                                    )
                                else:
                                    logger.warning(
                                        f"工作线程 {self.worker_id} {entity_type}.{operation_type} 操作失败（result=None），第{retry_count + 1}次重试..."
                                    )
                                sleep_duration = self.retry_delay * (retry_count + 1)
                                backoff_duration_total += sleep_duration
                                time.sleep(sleep_duration)  # 指数退避

                        except Exception as e:
                            attempt_duration_total += time.time() - attempt_start_time
                            error = str(e)
                            self.error_counts["total"] += 1
                            self.error_counts["by_entity"][entity_type] += 1
                            self.error_counts["by_operation"][operation_type] += 1

                            if retry_count < self.max_retries:
                                logger.warning(
                                    f"工作线程 {self.worker_id} {entity_type}.{operation_type} 操作异常: {error}，第{retry_count + 1}次重试..."
                                )
                                sleep_duration = self.retry_delay * (retry_count + 1)
                                backoff_duration_total += sleep_duration
                                time.sleep(sleep_duration)  # 指数退避
                            else:
                                logger.error(
                                    f"工作线程 {self.worker_id} {entity_type}.{operation_type} 操作最终失败: {error}"
                                )
                                break

                    wall_duration = time.time() - start_time
                    request_duration = (
                        attempt_duration_total / attempt_count if attempt_count else 0
                    )

                    # 记录结果
                    self.results.append(
                        {
                            "operation_type": operation_type,
                            "entity_type": entity_type,
                            "success": success,
                            "duration": request_duration,
                            "wall_duration": wall_duration,
                            "request_duration": request_duration,
                            "backoff_duration": backoff_duration_total,
                            "attempt_count": attempt_count,
                            "error": error,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

                    # 仅使用成功请求的接口耗时建立性能基线，避免重试退避放大误报。
                    if success and request_duration > 0:
                        self._update_performance_window(request_duration)

                    # 操作间隔
                    time.sleep(self.config.operation_interval)

                except Exception as e:
                    logger.error(f"工作线程 {self.worker_id} 执行操作异常: {e}")
                    time.sleep(1.0)

        except Exception as e:
            logger.error(f"工作线程 {self.worker_id} 初始化失败: {e}")
        finally:
            self.running = False

            # 关闭会话管理器
            if hasattr(self, "session_manager") and self.session_manager:
                logger.info(f"工作线程 {self.worker_id}: 关闭会话管理器")
                self.session_manager.stop_auto_refresh()
                self.session_manager.close_session()

            logger.info(f"工作线程 {self.worker_id} 停止")

    def _update_performance_window(self, duration: float):
        """更新性能监控窗口"""
        self.performance_window.append(duration)

        # 保持窗口大小
        if len(self.performance_window) > self.config.performance_window_size:
            self.performance_window.pop(0)

        # 设置基线性能（前100个操作的平均值）
        if self.baseline_performance is None and len(self.performance_window) >= 100:
            self.baseline_performance = statistics.mean(self.performance_window)
            logger.info(
                f"工作线程 {self.worker_id} 基线性能: {self.baseline_performance:.3f}s"
            )

    def check_performance_degradation(self):
        """检查性能劣化"""
        if self.baseline_performance is None or len(self.performance_window) < 10:
            return None

        current_performance = statistics.mean(self.performance_window)

        # 计算性能变化百分比
        if self.baseline_performance > 0:
            degradation_percent = (
                (current_performance - self.baseline_performance)
                / self.baseline_performance
                * 100
            )

            if degradation_percent > self.config.performance_degradation_threshold:
                return degradation_percent

        return None

    def _bootstrap_resources(self) -> bool:
        """准备老化测试依赖的基础资源。"""
        status_refs = self._load_status_refs()
        if not status_refs:
            logger.error(f"工作线程 {self.worker_id}: 未找到可用状态数据")
            return False

        warehouse = self._ensure_warehouse()
        if not warehouse or "id" not in warehouse:
            logger.error(f"工作线程 {self.worker_id}: 准备仓库失败")
            return False

        shelf = self._ensure_shelf(int(warehouse["id"]), status_refs["default"]["id"])
        if not shelf or "id" not in shelf:
            logger.error(f"工作线程 {self.worker_id}: 准备货架失败")
            return False

        store = self._ensure_store()
        if not store or "id" not in store:
            logger.error(f"工作线程 {self.worker_id}: 准备店铺失败")
            return False

        self.bootstrap_resources = {
            "status_refs": status_refs,
            "warehouse": {"id": int(warehouse["id"])},
            "shelf": {"id": int(shelf["id"])},
            "store": {"id": int(store["id"])},
            "dependency_product": None,
            "dependency_product_info": None,
            "dependency_goods_info": None,
        }
        logger.info(
            "工作线程 %s 依赖资源就绪: status=%s warehouse=%s shelf=%s store=%s",
            self.worker_id,
            status_refs["default"]["id"],
            warehouse["id"],
            shelf["id"],
            store["id"],
        )
        return True

    def _load_status_refs(self):
        """加载状态列表并选出优先使用的状态。"""
        statuses = self.status_sdk.filter_status({"page": 1, "size": 100}) or []
        statuses = [item for item in statuses if isinstance(item, dict) and item.get("id")]
        if not statuses:
            return None

        def pick(preferred_names):
            lowered = {name.lower() for name in preferred_names}
            for item in statuses:
                name = str(item.get("name", "")).strip().lower()
                if name in lowered:
                    return {"id": int(item["id"]), "name": item.get("name", "")}
            return {"id": int(statuses[0]["id"]), "name": statuses[0].get("name", "")}

        return {
            "default": pick(["启用", "已启用", "正常", "active", "enabled"]),
            "partner": pick(["启用", "已启用", "正常", "active", "enabled"]),
            "product": pick(["启用", "已启用", "正常", "active", "enabled"]),
            "fallbacks": [
                {"id": int(item["id"]), "name": item.get("name", "")} for item in statuses
            ],
        }

    def _ensure_warehouse(self):
        """获取现有仓库或创建测试仓库。"""
        warehouses = self.warehouse_sdk.filter_warehouse({"page": 1, "size": 10}) or []
        for warehouse in warehouses:
            if isinstance(warehouse, dict) and warehouse.get("id"):
                return warehouse

        warehouse = self.warehouse_sdk.create_warehouse(
            {
                "name": f"AGING_WAREHOUSE_{self.worker_id}_{int(time.time())}",
                "description": f"老化测试仓库_{self.worker_id}",
            }
        )
        if warehouse:
            return warehouse
        return None

    def _ensure_shelf(self, warehouse_id: int, status_id: int):
        """获取与仓库匹配的货架，必要时创建。"""
        shelves = self.shelf_sdk.filter_shelf({"page": 1, "size": 20}) or []
        for shelf in shelves:
            if not isinstance(shelf, dict) or not shelf.get("id"):
                continue
            shelf_warehouse = shelf.get("warehouse") or {}
            if shelf_warehouse.get("id") == warehouse_id:
                return shelf

        shelf = self.shelf_sdk.create_shelf(
            {
                "description": f"老化测试货架_{self.worker_id}",
                "capacity": max(random.randint(100, 1000), 1),
                "warehouse": {"id": warehouse_id},
                "status": {"id": status_id},
            }
        )
        if shelf:
            return shelf
        return None

    def _ensure_store(self):
        """获取现有店铺或创建测试店铺。"""
        stores = self.store_sdk.filter_store({"page": 1, "size": 10}) or []
        for store in stores:
            if isinstance(store, dict) and store.get("id"):
                return store

        store = self.store_sdk.create_store(
            {
                "name": f"AGING_STORE_{self.worker_id}_{int(time.time())}",
                "description": f"老化测试店铺_{self.worker_id}",
            }
        )
        if store:
            return store
        return None

    def _status_ref(self, key: str = "default"):
        """返回指定用途的状态引用。"""
        refs = self.bootstrap_resources.get("status_refs") or {}
        status_ref = refs.get(key) or refs.get("default")
        if status_ref and status_ref.get("id"):
            return {"id": int(status_ref["id"])}
        return None

    def _resource_ref(self, key: str):
        """返回 bootstrap 后的资源引用。"""
        ref = self.bootstrap_resources.get(key)
        if ref and ref.get("id"):
            return {"id": int(ref["id"])}
        return None

    def _query_dependency_entity(self, sdk, query_method_name: str, key: str):
        """查询缓存的依赖实体，失效时返回 None。"""
        cached = self.bootstrap_resources.get(key)
        if not cached or not cached.get("id"):
            return None

        query_method = getattr(sdk, query_method_name)
        entity = query_method(int(cached["id"]))
        if entity and entity.get("id"):
            self.bootstrap_resources[key] = entity
            return entity

        self.bootstrap_resources[key] = None
        return None

    def _ensure_dependency_product(self):
        """获取或创建依赖产品。"""
        existing = self._query_dependency_entity(
            self.product_sdk, "query_product", "dependency_product"
        )
        if existing:
            return existing

        status_ref = self._status_ref("product")
        if not status_ref:
            return None

        product = self.product_sdk.create_product(
            {
                "name": f"AGING_DEP_PRODUCT_{self.worker_id}_{int(time.time())}",
                "description": f"老化测试依赖产品_{self.worker_id}",
                "image": [],
                "expire": 365,
                "tags": ["aging"],
                "status": status_ref,
            }
        )
        if product and product.get("id"):
            self.bootstrap_resources["dependency_product"] = product
            self.bootstrap_resources["dependency_product_info"] = None
            self.bootstrap_resources["dependency_goods_info"] = None
            return product
        return None

    def _ensure_dependency_product_info(self):
        """获取或创建依赖产品 SKU。"""
        existing = self._query_dependency_entity(
            self.product_info_sdk,
            "query_product_info",
            "dependency_product_info",
        )
        if existing:
            return existing

        product = self._ensure_dependency_product()
        if not product or not product.get("id"):
            return None

        product_info = self.product_info_sdk.create_product_info(
            {
                "sku": f"{self.worker_id}{int(time.time() * 1000) % 100000000}",
                "description": f"老化测试依赖产品SKU_{self.worker_id}",
                "product": {"id": int(product["id"])},
            }
        )
        if product_info and product_info.get("id"):
            self.bootstrap_resources["dependency_product_info"] = product_info
            self.bootstrap_resources["dependency_goods_info"] = None
            return product_info
        return None

    def _ensure_dependency_goods_info(self):
        """获取或创建依赖商品 SKU。"""
        existing = self._query_dependency_entity(
            self.goods_info_sdk,
            "query_goods_info",
            "dependency_goods_info",
        )
        if existing:
            return existing

        product_info = self._ensure_dependency_product_info()
        shelf_ref = self._resource_ref("shelf")
        if not product_info or not product_info.get("id") or not shelf_ref:
            return None

        goods_info = self.goods_info_sdk.create_goods_info(
            {
                "sku": f"{self.worker_id}{int(time.time() * 1000) % 100000000}",
                "product": {"id": int(product_info["id"])},
                "type": 1,
                "count": random.randint(50, 200),
                "price": round(random.uniform(5.0, 500.0), 2),
                "shelf": [shelf_ref],
            }
        )
        if goods_info and goods_info.get("id"):
            self.bootstrap_resources["dependency_goods_info"] = goods_info
            return goods_info
        return None

    def _create_entity(self, entity_type: str):
        """创建实体"""
        if entity_type == "partner":
            data = self._generate_partner_data()
            if not data:
                return None
            result = self.partner_sdk.create_partner(data)
        elif entity_type == "product":
            data = self._generate_product_data()
            if not data:
                return None
            result = self.product_sdk.create_product(data)
        elif entity_type == "goods":
            product_info = self._get_or_create_product_info()
            if not product_info or "id" not in product_info:
                return None
            data = self._generate_goods_data(int(product_info["id"]))
            if not data:
                return None
            result = self.goods_sdk.create_goods(data)
        elif entity_type == "stockin":
            goods_info = self._get_or_create_goods_info()
            if goods_info and goods_info.get("id") and goods_info.get("product_id"):
                data = self._generate_stockin_data(goods_info)
                result = self.stockin_sdk.create_stockin(data) if data else None
            else:
                result = None
        elif entity_type == "stockout":
            goods_info = self._get_or_create_goods_info()
            if goods_info and goods_info.get("id") and goods_info.get("product_id"):
                data = self._generate_stockout_data(goods_info)
                result = self.stockout_sdk.create_stockout(data) if data else None
            else:
                result = None
        else:
            raise ValueError(f"未知实体类型: {entity_type}")

        if result and "id" in result:
            self.entity_cache[entity_type].append(str(result["id"]))

        return result

    def _read_entity(self, entity_type: str):
        """读取实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            # 如果没有缓存，先创建一个
            return self._create_entity(entity_type)

        entity_id = random.choice(entity_ids)

        if entity_type == "partner":
            return self.partner_sdk.query_partner(int(entity_id))
        elif entity_type == "product":
            return self.product_sdk.query_product(int(entity_id))
        elif entity_type == "goods":
            return self.goods_sdk.query_goods(int(entity_id))
        elif entity_type == "stockin":
            return self.stockin_sdk.query_stockin(int(entity_id))
        elif entity_type == "stockout":
            return self.stockout_sdk.query_stockout(int(entity_id))
        else:
            raise ValueError(f"未知实体类型: {entity_type}")

    def _update_entity(self, entity_type: str):
        """更新实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            # 如果没有缓存，先创建一个
            entity = self._create_entity(entity_type)
            if not entity or "id" not in entity:
                return None
            entity_id = str(entity["id"])
        else:
            entity_id = random.choice(entity_ids)

        # 获取当前实体
        current_entity = self._read_entity(entity_type)
        if not current_entity:
            return None

        # 更新描述字段
        current_entity["description"] = (
            f"老化测试更新_{self.worker_id}_{int(time.time())}"
        )

        if entity_type == "partner":
            return self.partner_sdk.update_partner(int(entity_id), current_entity)
        elif entity_type == "product":
            return self.product_sdk.update_product(int(entity_id), current_entity)
        elif entity_type == "goods":
            return self.goods_sdk.update_goods(int(entity_id), current_entity)
        elif entity_type == "stockin":
            # 服务器端API问题：更新stockin时要求goodsInfo包含完整的product字段
            # 在操作选择阶段已经跳过update操作，这里不应该被调用
            logger.debug(f"stockin更新操作不应被调用（已在操作选择阶段跳过）")
            return None
        elif entity_type == "stockout":
            # 服务器端API问题：更新stockout时要求goodsInfo包含完整的product字段
            # 在操作选择阶段已经跳过update操作，这里不应该被调用
            logger.debug(f"stockout更新操作不应被调用（已在操作选择阶段跳过）")
            return None
        else:
            raise ValueError(f"未知实体类型: {entity_type}")

    def _delete_entity(self, entity_type: str):
        """删除实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            logger.debug(f"_delete_entity: {entity_type} 缓存为空")
            return None

        entity_id = random.choice(entity_ids)
        logger.debug(f"_delete_entity: 尝试删除 {entity_type} ID: {entity_id}")

        try:
            if entity_type == "partner":
                result = self.partner_sdk.delete_partner(int(entity_id))
            elif entity_type == "product":
                result = self.product_sdk.delete_product(int(entity_id))
            elif entity_type == "goods":
                result = self.goods_sdk.delete_goods(int(entity_id))
            elif entity_type == "stockin":
                result = self.stockin_sdk.delete_stockin(int(entity_id))
            elif entity_type == "stockout":
                result = self.stockout_sdk.delete_stockout(int(entity_id))
            else:
                raise ValueError(f"未知实体类型: {entity_type}")

            logger.debug(
                f"_delete_entity: {entity_type}.delete({entity_id}) 返回: {result}"
            )

            if result:
                self.entity_cache[entity_type].remove(entity_id)
                logger.debug(
                    f"_delete_entity: 从缓存移除 {entity_type} ID: {entity_id}"
                )

            return result

        except Exception as e:
            logger.error(
                f"_delete_entity: 删除 {entity_type} ID: {entity_id} 时出现异常: {e}"
            )
            return None

    def _list_entities(self, entity_type: str):
        """列出实体"""
        filters = {"page": 1, "size": 10}

        if entity_type == "partner":
            return self.partner_sdk.filter_partner(filters)
        elif entity_type == "product":
            return self.product_sdk.filter_product(filters)
        elif entity_type == "goods":
            return self.goods_sdk.filter_goods(filters)
        elif entity_type == "stockin":
            return self.stockin_sdk.filter_stockin(filters)
        elif entity_type == "stockout":
            return self.stockout_sdk.filter_stockout(filters)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")

    def _get_or_create_goods(self):
        """获取或创建商品信息"""
        goods_ids = self.entity_cache["goods"]
        if goods_ids:
            # 随机选择一个商品ID，并尝试获取其详细信息
            goods_id = random.choice(goods_ids)
            try:
                goods_info = self.goods_sdk.query_goods(int(goods_id))
                if goods_info:
                    product_ref = goods_info.get("product") or {}
                    product_id = product_ref.get("id")
                    if not product_id:
                        product_info = self._get_or_create_product_info()
                        product_id = product_info.get("id") if product_info else None
                    return {
                        "id": goods_id,
                        "sku": goods_info.get("sku", f"SKU_{self.worker_id:04d}"),
                        "product_id": product_id,
                    }
            except:
                pass

        # 需要先准备产品 SKU
        product_info = self._get_or_create_product_info()
        if not product_info or "id" not in product_info:
            return None

        # 创建新商品
        goods_data = self._generate_goods_data(int(product_info["id"]))
        if not goods_data:
            return None

        goods = self.goods_sdk.create_goods(goods_data)
        if goods and "id" in goods:
            goods_id = str(goods["id"])
            self.entity_cache["goods"].append(goods_id)
            return {
                "id": goods_id,
                "sku": goods.get("sku", goods_data["sku"]),
                "product_id": goods_data["product"]["id"],
            }

        # 如果创建失败，返回默认值
        return None

    def _get_or_create_product_info(self):
        """获取或创建产品 SKU 信息。"""
        product_info = self._ensure_dependency_product_info()
        if product_info and product_info.get("id"):
            return {"id": int(product_info["id"])}
        return None

    def _get_or_create_goods_info(self):
        """获取或创建商品 SKU 信息。"""
        goods_info = self._ensure_dependency_goods_info()
        if not goods_info or not goods_info.get("id"):
            return None

        product_ref = goods_info.get("product") or {}
        return {
            "id": int(goods_info["id"]),
            "sku": goods_info.get("sku", ""),
            "product_id": product_ref.get("id"),
            "shelf": goods_info.get("shelf") or [],
        }

    def _generate_partner_data(self):
        """生成合作伙伴数据"""
        status_ref = self._status_ref("partner")
        if not status_ref:
            return None
        return {
            "name": f"老化测试合作伙伴_{self.worker_id}_{int(time.time())}",
            "telephone": f"138{random.randint(10000000, 99999999)}",
            "wechat": f"wechat_{self.worker_id}",
            "description": f"老化测试合作伙伴描述_{self.worker_id}",
            "status": status_ref,
        }

    def _generate_product_data(self):
        """生成产品数据"""
        status_ref = self._status_ref("product")
        if not status_ref:
            return None
        return {
            "name": f"老化测试产品_{self.worker_id}_{int(time.time())}",
            "description": f"老化测试产品描述_{self.worker_id}",
            "image": [],
            "expire": random.randint(30, 365),
            "tags": ["aging", f"worker-{self.worker_id}"],
            "status": status_ref,
        }

    def _generate_goods_data(self, product_id: int):
        """生成商品数据"""
        timestamp = int(time.time())
        status_ref = self._status_ref("default")
        store_ref = self._resource_ref("store")
        shelf_ref = self._resource_ref("shelf")
        if not status_ref or not store_ref or not shelf_ref or not product_id:
            return None
        return {
            "name": f"老化测试商品_{self.worker_id}_{timestamp}",
            "sku": f"SKU_{self.worker_id:04d}_{timestamp}",
            "price": round(random.uniform(5.0, 500.0), 2),
            "count": random.randint(1, 1000),  # 注意：是count不是quantity
            "description": f"老化测试商品描述_{self.worker_id}",
            "parameter": f"参数_{self.worker_id}_{timestamp}",
            "serviceInfo": f"服务信息_{self.worker_id}_{timestamp}",
            "status": status_ref,
            "product": {"id": int(product_id)},
            "shelf": [shelf_ref],
            "store": store_ref,
        }

    def _generate_stockin_data(self, goods_info: dict):
        """生成入库数据"""
        if not goods_info or not goods_info.get("id") or not goods_info.get("product_id"):
            return None

        store_ref = self._resource_ref("store")
        status_ref = self._status_ref("default")
        shelf_refs = goods_info.get("shelf") or [self._resource_ref("shelf")]
        if (
            not store_ref
            or not status_ref
            or not shelf_refs
        ):
            return None

        return {
            "goodsInfo": [
                {
                    "id": int(goods_info["id"]),
                    "sku": goods_info.get("sku", ""),
                    "product": {"id": int(goods_info["product_id"])},
                    "type": 1,  # 入库类型，整数
                    "count": random.randint(1, 100),
                    "price": round(random.uniform(5.0, 500.0), 2),
                    "shelf": shelf_refs,
                }
            ],
            "description": f"老化测试入库_{self.worker_id}_{int(time.time())}",
            "status": status_ref,
            "store": store_ref,
        }

    def _generate_stockout_data(self, goods_info: dict):
        """生成出库数据"""
        if not goods_info or not goods_info.get("id") or not goods_info.get("product_id"):
            return None

        store_ref = self._resource_ref("store")
        status_ref = self._status_ref("default")
        shelf_refs = goods_info.get("shelf") or [self._resource_ref("shelf")]
        if (
            not store_ref
            or not status_ref
            or not shelf_refs
        ):
            return None

        return {
            "goodsInfo": [
                {
                    "id": int(goods_info["id"]),
                    "sku": goods_info.get("sku", ""),
                    "product": {"id": int(goods_info["product_id"])},
                    "type": 2,  # 出库类型，整数
                    "count": random.randint(1, 50),
                    "price": round(random.uniform(5.0, 500.0), 2),
                    "shelf": shelf_refs,
                }
            ],
            "description": f"老化测试出库_{self.worker_id}_{int(time.time())}",
            "status": status_ref,
            "store": store_ref,
        }

    def get_statistics(self):
        """获取统计信息"""
        if not self.results:
            return {}

        successful_results = [r for r in self.results if r["success"]]
        failed_results = [r for r in self.results if not r["success"]]

        durations = [r["duration"] for r in self.results if r["duration"] > 0]

        # 计算性能劣化
        degradation_percent = self.check_performance_degradation()

        # 计算总数据量（缓存中的实体数）
        total_entities = sum(len(ids) for ids in self.entity_cache.values())

        # 计算错误率
        total_errors = self.error_counts["total"]
        error_rate = (
            total_errors / len(self.results) * 100
            if self.results and total_errors > 0
            else 0
        )
        wall_durations = [r["wall_duration"] for r in self.results if r["wall_duration"] > 0]
        retry_counts = [r["attempt_count"] for r in self.results if r["attempt_count"] > 0]

        return {
            "total_operations": len(self.results),
            "successful_operations": len(successful_results),
            "failed_operations": len(failed_results),
            "skipped_operations": self.skipped_operations,
            "success_rate": (
                len(successful_results) / len(self.results) * 100 if self.results else 0
            ),
            "avg_duration": statistics.mean(durations) if durations else 0,
            "avg_wall_duration": statistics.mean(wall_durations) if wall_durations else 0,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "avg_attempt_count": statistics.mean(retry_counts) if retry_counts else 0,
            "entity_counts": {
                entity_type: len(ids) for entity_type, ids in self.entity_cache.items()
            },
            "total_entities": total_entities,
            "performance_degradation_percent": degradation_percent,
            "baseline_performance": self.baseline_performance,
            "current_performance": (
                statistics.mean(self.performance_window)
                if self.performance_window
                else 0
            ),
            "error_statistics": {
                "total_errors": total_errors,
                "error_rate": error_rate,
                "by_entity": self.error_counts["by_entity"],
                "by_operation": self.error_counts["by_operation"],
            },
        }


class MultiTenantAgingWorker:
    """多租户全业务链路老化测试工作线程。

    每个 worker 绑定一个 tenant，持续重复执行完整 VMI 业务流，
    直到老化测试总入口发出停止信号。
    """

    def __init__(
        self,
        worker_id: int,
        tenant_id: str,
        tenant_config: Dict[str, Any],
        config: AgingTestConfig,
    ):
        self.worker_id = worker_id
        self.tenant_id = tenant_id
        self.tenant_config = tenant_config
        self.config = config
        self.results: List[Dict[str, Any]] = []
        self.running = False
        self.performance_window: List[float] = []
        self.baseline_performance: Optional[float] = None
        self.error_counts = {
            "total": 0,
            "by_entity": {"multi_tenant_full_flow": 0},
            "by_operation": {"full_flow": 0},
        }
        self.skipped_operations = 0
        self.session_manager = None
        self._scenario_func = None

    def run(self, stop_event: threading.Event):
        """运行租户老化循环。"""
        self.running = True
        logger.info("多租户老化线程 %s 启动: tenant=%s", self.worker_id, self.tenant_id)

        try:
            from concurrent_test_v2 import MultiTenantBusinessScenarioFactory
            from config_helper import get_session_config
            from session_manager import SessionManager

            session_config = get_session_config()
            self.session_manager = SessionManager(
                server_url=self.tenant_config["server_url"],
                namespace=self.tenant_config["namespace"],
                username=self.tenant_config["username"],
                password=self.tenant_config["password"],
                refresh_interval=session_config.get("refresh_interval", 540),
                session_timeout=session_config.get("timeout", 1800),
            )

            if not self.session_manager.create_session():
                logger.error(
                    "多租户老化线程 %s: tenant=%s 创建会话失败",
                    self.worker_id,
                    self.tenant_id,
                )
                return

            self.session_manager.start_auto_refresh()
            self._scenario_func = (
                MultiTenantBusinessScenarioFactory.create_full_business_flow_test()
            )

            while self.running and not stop_event.is_set():
                start_time = time.time()
                success = False
                error = None

                try:
                    if not self.session_manager.is_session_valid():
                        logger.warning(
                            "多租户老化线程 %s: tenant=%s 会话无效，尝试重连",
                            self.worker_id,
                            self.tenant_id,
                        )
                        if not self.session_manager.reconnect():
                            raise RuntimeError("会话重连失败")

                    self._scenario_func(
                        tenant_id=self.tenant_id,
                        session_manager=self.session_manager,
                    )
                    success = True

                except Exception as exc:
                    error = str(exc)
                    self.error_counts["total"] += 1
                    self.error_counts["by_entity"]["multi_tenant_full_flow"] += 1
                    self.error_counts["by_operation"]["full_flow"] += 1
                    logger.error(
                        "多租户老化线程 %s: tenant=%s 执行失败 - %s",
                        self.worker_id,
                        self.tenant_id,
                        exc,
                    )

                duration = time.time() - start_time
                self.results.append(
                    {
                        "operation_type": "full_flow",
                        "entity_type": "multi_tenant_full_flow",
                        "success": success,
                        "duration": duration,
                        "wall_duration": duration,
                        "request_duration": duration,
                        "backoff_duration": 0,
                        "attempt_count": 1,
                        "error": error,
                        "timestamp": datetime.now().isoformat(),
                        "tenant_id": self.tenant_id,
                    }
                )

                if success and duration > 0:
                    self._update_performance_window(duration)

                if not stop_event.is_set():
                    time.sleep(self.config.operation_interval)

        except Exception as exc:
            logger.error(
                "多租户老化线程 %s 初始化失败: tenant=%s error=%s",
                self.worker_id,
                self.tenant_id,
                exc,
            )
        finally:
            self.running = False
            if self.session_manager:
                try:
                    self.session_manager.stop_auto_refresh()
                    self.session_manager.close_session()
                except Exception as exc:
                    logger.warning(
                        "多租户老化线程 %s: tenant=%s 清理会话失败 - %s",
                        self.worker_id,
                        self.tenant_id,
                        exc,
                    )
            logger.info("多租户老化线程 %s 停止: tenant=%s", self.worker_id, self.tenant_id)

    def _update_performance_window(self, duration: float):
        """更新性能监控窗口。"""
        self.performance_window.append(duration)
        if len(self.performance_window) > 100:
            self.performance_window.pop(0)

        if self.baseline_performance is None and len(self.performance_window) >= 20:
            self.baseline_performance = statistics.mean(self.performance_window)
            logger.info(
                "多租户老化线程 %s: tenant=%s 基线性能 %.3fs",
                self.worker_id,
                self.tenant_id,
                self.baseline_performance,
            )

    def check_performance_degradation(self):
        """检查性能劣化。"""
        if self.baseline_performance is None or len(self.performance_window) < 5:
            return None

        current_performance = statistics.mean(self.performance_window)
        if self.baseline_performance > 0:
            degradation_percent = (
                (current_performance - self.baseline_performance)
                / self.baseline_performance
                * 100
            )
            if degradation_percent > self.config.performance_degradation_threshold:
                return degradation_percent

        return None

    def get_statistics(self):
        """获取统计信息。"""
        if not self.results:
            return {}

        successful_results = [r for r in self.results if r["success"]]
        failed_results = [r for r in self.results if not r["success"]]
        durations = [r["duration"] for r in self.results if r["duration"] > 0]
        wall_durations = [
            r["wall_duration"] for r in self.results if r["wall_duration"] > 0
        ]
        degradation_percent = self.check_performance_degradation()

        return {
            "tenant_id": self.tenant_id,
            "total_operations": len(self.results),
            "successful_operations": len(successful_results),
            "failed_operations": len(failed_results),
            "skipped_operations": self.skipped_operations,
            "success_rate": (
                len(successful_results) / len(self.results) * 100 if self.results else 0
            ),
            "avg_duration": statistics.mean(durations) if durations else 0,
            "avg_wall_duration": statistics.mean(wall_durations) if wall_durations else 0,
            "min_duration": min(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "avg_attempt_count": 1,
            "entity_counts": {"multi_tenant_full_flow": 0},
            "total_entities": 0,
            "performance_degradation_percent": degradation_percent,
            "baseline_performance": self.baseline_performance,
            "current_performance": (
                statistics.mean(self.performance_window)
                if self.performance_window
                else 0
            ),
            "error_statistics": {
                "total_errors": self.error_counts["total"],
                "error_rate": (
                    self.error_counts["total"] / len(self.results) * 100
                    if self.results and self.error_counts["total"] > 0
                    else 0
                ),
                "by_entity": self.error_counts["by_entity"],
                "by_operation": self.error_counts["by_operation"],
            },
        }


class AgingTestRunner:
    """老化测试运行器"""

    def __init__(self, config=None):
        self.config = config or AgingTestConfig()
        self.workers = []
        self.worker_threads = []
        self.stop_event = threading.Event()
        self.start_time = None
        self.metrics_history = []
        self.data_limit_exceeded = False
        self.performance_degradation_detected = False
        self.stop_reason = None

    def run(self):
        """运行老化测试"""
        logger.info("开始长期老化测试")
        logger.info(
            f"测试配置: 持续时间={self.config.duration_hours}小时, "
            f"并发线程={self.config.concurrent_threads}, "
            f"最大数据量={self.config.max_data_count}万条"
        )
        if self.config.multi_tenant_business_flow_enabled:
            logger.info("老化模式: 多租户全业务链路")

        try:
            self.start_time = datetime.now()

            # 启动工作线程
            self._start_workers()

            # 运行指定时间
            end_time = self.start_time + timedelta(hours=self.config.duration_hours)

            while datetime.now() < end_time and not self.stop_event.is_set():
                # 记录指标
                metrics = self._record_metrics()

                # 打印状态
                self._print_status(metrics)

                # 检查停止条件
                if not self._check_continue_conditions():
                    break

                # 等待下一个报告周期，但不要超过预定结束时间。
                remaining_seconds = max(
                    0.0, (end_time - datetime.now()).total_seconds()
                )
                if remaining_seconds <= 0:
                    break
                wait_seconds = min(
                    self.config.report_interval_minutes * 60,
                    remaining_seconds,
                )
                self.stop_event.wait(wait_seconds)

        except KeyboardInterrupt:
            logger.info("测试被用户中断")
            self.stop_reason = "用户中断"
        except Exception as e:
            logger.error(f"测试运行异常: {e}")
            self.stop_reason = f"异常: {str(e)}"
        finally:
            # 停止测试
            self.stop()

            # 工作线程停止后再补一次最终指标，确保最后一轮完成的结果进入报告。
            if self.workers:
                self._record_metrics()

            # 生成最终报告
            report = self._generate_report()
            self._save_report(report)

            logger.info("长期老化测试完成")

        return self.stop_reason in (None, "", "正常完成")

    def _resolve_multi_tenant_configs(self) -> Dict[str, Dict[str, Any]]:
        """解析多租户老化测试目标租户配置。"""
        from tenant_config_helper import (get_concurrent_tenant_configs,
                                          get_preferred_concurrent_tenant_ids)

        target_tenants = self.config.target_tenants
        if not target_tenants:
            target_tenants = get_preferred_concurrent_tenant_ids()

        tenant_configs = get_concurrent_tenant_configs(target_tenants)
        if not tenant_configs:
            raise RuntimeError("多租户老化模式已启用，但未解析到可用租户配置")

        missing_tenants = [
            tenant_id for tenant_id in target_tenants if tenant_id not in tenant_configs
        ]
        if missing_tenants:
            raise RuntimeError(f"多租户老化目标租户配置不完整，缺少: {missing_tenants}")

        self.config.target_tenants = list(tenant_configs.keys())
        return tenant_configs

    def _start_workers(self):
        """启动工作线程"""
        # 停止现有工作线程
        self._stop_workers()

        # 创建新的工作线程
        self.workers = []
        if self.config.multi_tenant_business_flow_enabled:
            tenant_configs = self._resolve_multi_tenant_configs()
            for i, tenant_id in enumerate(tenant_configs.keys()):
                worker = MultiTenantAgingWorker(
                    worker_id=i,
                    tenant_id=tenant_id,
                    tenant_config=tenant_configs[tenant_id],
                    config=self.config,
                )
                self.workers.append(worker)
            logger.info(
                "多租户老化模式启用，固定并发租户: %s",
                list(tenant_configs.keys()),
            )
        else:
            for i in range(self.config.concurrent_threads):
                worker = AgingTestWorker(i, self.config)
                self.workers.append(worker)

        # 启动工作线程
        self.worker_threads = []
        for worker in self.workers:
            thread = threading.Thread(
                target=worker.run, args=(self.stop_event,), daemon=True
            )
            thread.start()
            self.worker_threads.append(thread)

        logger.info("启动 %s 个工作线程", len(self.workers))

    def _stop_workers(self):
        """停止工作线程"""
        self.stop_event.set()
        join_timeout = 60.0 if self.config.multi_tenant_business_flow_enabled else 5.0
        for thread in self.worker_threads:
            thread.join(timeout=join_timeout)
        self.stop_event.clear()
        self.worker_threads = []
        logger.info("工作线程已停止")

    def _record_metrics(self):
        """记录指标"""
        total_stats = {
            "total_operations": 0,
            "successful_operations": 0,
            "failed_operations": 0,
            "skipped_operations": 0,
            "avg_duration": 0,
            "total_entities": 0,
            "worker_count": len(self.workers),
            "performance_degradation_detected": False,
            "data_limit_exceeded": False,
        }

        worker_durations = []
        performance_degradations = []

        for worker in self.workers:
            stats = worker.get_statistics()
            if stats:
                total_stats["total_operations"] += stats["total_operations"]
                total_stats["successful_operations"] += stats["successful_operations"]
                total_stats["failed_operations"] += stats["failed_operations"]
                total_stats["skipped_operations"] += stats.get("skipped_operations", 0)
                total_stats["total_entities"] += stats.get("total_entities", 0)

                if stats["avg_duration"] > 0:
                    worker_durations.append(stats["avg_duration"])

                # 检查性能劣化
                degradation_percent = stats.get("performance_degradation_percent")
                if degradation_percent is not None:
                    performance_degradations.append(degradation_percent)
                    logger.warning(
                        f"工作线程 {worker.worker_id} 检测到性能劣化: {degradation_percent:.1f}% "
                        f"(基线: {stats.get('baseline_performance', 0):.3f}s, "
                        f"当前: {stats.get('current_performance', 0):.3f}s)"
                    )

        if worker_durations:
            total_stats["avg_duration"] = statistics.mean(worker_durations)

        if total_stats["total_operations"] > 0:
            total_stats["success_rate"] = (
                total_stats["successful_operations"]
                / total_stats["total_operations"]
                * 100
            )

        # 检查数据量限制
        max_data_count = self.config.max_data_count * 10000  # 转换为实际条数
        if total_stats["total_entities"] > max_data_count:
            total_stats["data_limit_exceeded"] = True
            self.data_limit_exceeded = True
            self.stop_reason = (
                f"数据量超过限制: {total_stats['total_entities']} > {max_data_count}"
            )
            logger.error(
                f"数据量超过限制: {total_stats['total_entities']} > {max_data_count}"
            )

        # 检查性能劣化
        if performance_degradations:
            avg_degradation = statistics.mean(performance_degradations)
            total_stats["performance_degradation_detected"] = True
            total_stats["avg_degradation_percent"] = avg_degradation
            self.performance_degradation_detected = True
            logger.warning(f"检测到性能劣化: 平均{avg_degradation:.1f}%")

        if self.start_time:
            elapsed_minutes = (datetime.now() - self.start_time).total_seconds() / 60
        else:
            elapsed_minutes = 0

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_minutes": elapsed_minutes,
            "metrics": total_stats,
        }

        self.metrics_history.append(metrics)
        return metrics

    def _check_continue_conditions(self):
        """检查是否应该继续测试"""
        # 检查停止条件
        if self.data_limit_exceeded:
            logger.error(f"测试停止: {self.stop_reason}")
            return False

        return True

    def _print_status(self, metrics):
        """打印状态"""
        if not metrics:
            return

        m = metrics["metrics"]
        elapsed = metrics["elapsed_minutes"]

        status = (
            f"[老化测试] 已运行: {elapsed:.1f}分钟, "
            f"操作数: {m.get('total_operations', 0)}, "
            f"成功率: {m.get('success_rate', 0):.1f}%, "
            f"平均耗时: {m.get('avg_duration', 0):.3f}s, "
            f"数据量: {m.get('total_entities', 0)}/{self.config.max_data_count * 10000}, "
            f"跳过: {m.get('skipped_operations', 0)}"
        )

        if m.get("performance_degradation_detected"):
            status += f", 性能劣化: {m.get('avg_degradation_percent', 0):.1f}%"

        logger.info(status)

    def _generate_report(self):
        """生成测试报告"""
        if not self.start_time:
            return {}

        end_time = datetime.now()
        total_duration = (
            (end_time - self.start_time).total_seconds() if self.start_time else 0
        )
        final_metrics = self.metrics_history[-1]["metrics"] if self.metrics_history else {}

        total_operations = final_metrics.get("total_operations", 0)
        successful_operations = final_metrics.get("successful_operations", 0)
        failed_operations = final_metrics.get("failed_operations", 0)
        skipped_operations = final_metrics.get("skipped_operations", 0)
        total_entities = final_metrics.get("total_entities", 0)

        report = {
            "test_info": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_duration_seconds": total_duration,
                "total_duration_hours": total_duration / 3600,
                "config": {
                    "duration_hours": self.config.duration_hours,
                    "concurrent_threads": self.config.concurrent_threads,
                    "operation_interval": self.config.operation_interval,
                    "max_data_count": self.config.max_data_count,
                    "performance_degradation_threshold": self.config.performance_degradation_threshold,
                    "multi_tenant_business_flow_enabled": self.config.multi_tenant_business_flow_enabled,
                    "target_tenants": self.config.target_tenants,
                },
            },
            "summary": {
                "total_operations": total_operations,
                "successful_operations": successful_operations,
                "failed_operations": failed_operations,
                "skipped_operations": skipped_operations,
                "success_rate": (
                    (successful_operations / total_operations * 100)
                    if total_operations > 0
                    else 0
                ),
                "total_entities": total_entities,
                "data_limit_exceeded": self.data_limit_exceeded,
                "performance_degradation_detected": self.performance_degradation_detected,
                "stop_reason": self.stop_reason,
            },
            "metrics_history": self.metrics_history,
            "analysis": self._analyze_metrics(),
        }

        return report

    def _analyze_metrics(self):
        """分析指标"""
        if not self.metrics_history:
            return {}

        effective_history = [
            item
            for item in self.metrics_history
            if item.get("metrics", {}).get("total_operations", 0) > 0
        ]
        if not effective_history:
            effective_history = self.metrics_history

        # 趋势分析
        success_rates = [
            m["metrics"].get("success_rate", 0) for m in effective_history
        ]
        durations = [m["metrics"].get("avg_duration", 0) for m in effective_history]
        entity_counts = [
            m["metrics"].get("total_entities", 0) for m in effective_history
        ]

        analysis = {
            "trend_analysis": {
                "success_rate_trend": (
                    "stable"
                    if len(success_rates) < 2
                    else (
                        "improving"
                        if success_rates[-1] > success_rates[0]
                        else "declining"
                    )
                ),
                "duration_trend": (
                    "stable"
                    if len(durations) < 2
                    else ("improving" if durations[-1] < durations[0] else "worsening")
                ),
                "entity_growth_trend": (
                    "stable"
                    if len(entity_counts) < 2
                    else (
                        "growing"
                        if entity_counts[-1] > entity_counts[0]
                        else "shrinking"
                    )
                ),
                "final_success_rate": success_rates[-1] if success_rates else 0,
                "final_avg_duration": durations[-1] if durations else 0,
                "final_entity_count": entity_counts[-1] if entity_counts else 0,
            },
            "performance_analysis": {
                "degradation_detected": self.performance_degradation_detected,
                "degradation_threshold": self.config.performance_degradation_threshold,
                "data_limit_exceeded": self.data_limit_exceeded,
                "max_data_limit": self.config.max_data_count * 10000,
                "final_data_usage_percent": (
                    (entity_counts[-1] / (self.config.max_data_count * 10000) * 100)
                    if entity_counts and self.config.max_data_count > 0
                    else 0
                ),
            },
            "recommendations": self._generate_recommendations(),
        }

        return analysis

    def _generate_recommendations(self):
        """生成建议"""
        recommendations = []

        if not self.metrics_history:
            return recommendations

        final_metrics = self.metrics_history[-1]["metrics"]
        success_rate = final_metrics.get("success_rate", 0)
        avg_duration = final_metrics.get("avg_duration", 0)
        total_entities = final_metrics.get("total_entities", 0)

        if self.data_limit_exceeded:
            recommendations.append(
                f"数据量已超过限制({self.config.max_data_count}万条)，建议优化数据清理策略或扩容数据库"
            )

        if self.performance_degradation_detected:
            recommendations.append(
                "检测到性能劣化，建议检查数据库索引、查询优化和服务器资源"
            )

        if success_rate < 95:
            recommendations.append("系统稳定性需要提升，建议检查服务器资源和数据库性能")

        if avg_duration > 1.0:
            recommendations.append("响应时间较长，建议优化接口性能和数据库查询")

        if final_metrics.get("failed_operations", 0) > 0:
            recommendations.append("存在失败操作，建议检查错误日志并修复问题")

        # 数据量相关建议
        max_entities = self.config.max_data_count * 10000
        if total_entities > max_entities * 0.8:
            recommendations.append(
                f"数据量接近限制({total_entities}/{max_entities})，建议提前规划数据清理或扩容"
            )

        return recommendations

    def _save_report(self, report):
        """保存测试报告"""
        if not report:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = f"aging_test_report_{timestamp}.json"

        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"测试报告已保存到: {report_file}")

        # 同时生成简化的文本报告
        self._generate_text_report(report, f"aging_test_summary_{timestamp}.txt")

    def _generate_text_report(self, report, filename: str):
        """生成文本报告"""
        with open(filename, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("长期老化测试报告\n")
            f.write("=" * 60 + "\n\n")

            # 测试信息
            test_info = report.get("test_info", {})
            f.write("测试信息:\n")
            f.write(f"  开始时间: {test_info.get('start_time', 'N/A')}\n")
            f.write(f"  结束时间: {test_info.get('end_time', 'N/A')}\n")
            f.write(f"  总时长: {test_info.get('total_duration_hours', 0):.2f} 小时\n")
            f.write(
                f"  并发线程数: {test_info.get('config', {}).get('concurrent_threads', 0)}\n"
            )
            f.write(
                f"  最大数据量限制: {test_info.get('config', {}).get('max_data_count', 0)} 万条\n\n"
            )

            # 测试摘要
            summary = report.get("summary", {})
            f.write("测试摘要:\n")
            f.write(f"  总操作数: {summary.get('total_operations', 0)}\n")
            f.write(f"  成功操作: {summary.get('successful_operations', 0)}\n")
            f.write(f"  失败操作: {summary.get('failed_operations', 0)}\n")
            f.write(f"  成功率: {summary.get('success_rate', 0):.2f}%\n")
            f.write(f"  总数据量: {summary.get('total_entities', 0)} 条\n")
            f.write(
                f"  数据量限制: {'已超过' if summary.get('data_limit_exceeded') else '未超过'}\n"
            )
            f.write(
                f"  性能劣化: {'已检测到' if summary.get('performance_degradation_detected') else '未检测到'}\n"
            )
            f.write(f"  停止原因: {summary.get('stop_reason', '正常完成')}\n\n")

            # 分析结果
            analysis = report.get("analysis", {})
            trend = analysis.get("trend_analysis", {})
            f.write("趋势分析:\n")
            f.write(f"  成功率趋势: {trend.get('success_rate_trend', 'N/A')}\n")
            f.write(f"  响应时间趋势: {trend.get('duration_trend', 'N/A')}\n")
            f.write(f"  数据增长趋势: {trend.get('entity_growth_trend', 'N/A')}\n")
            f.write(f"  最终成功率: {trend.get('final_success_rate', 0):.2f}%\n")
            f.write(f"  最终平均耗时: {trend.get('final_avg_duration', 0):.3f}秒\n")
            f.write(f"  最终数据量: {trend.get('final_entity_count', 0)} 条\n\n")

            # 建议
            recommendations = analysis.get("recommendations", [])
            if recommendations:
                f.write("改进建议:\n")
                for i, rec in enumerate(recommendations, 1):
                    f.write(f"  {i}. {rec}\n")
            else:
                f.write("系统表现良好，无需特别改进。\n")

            f.write("\n" + "=" * 60 + "\n")

        logger.info(f"文本报告已保存到: {filename}")

    def stop(self):
        """停止测试"""
        logger.info("停止老化测试")
        self.stop_event.set()
        self._stop_workers()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="长期老化测试")
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="测试持续时间（小时），未指定时使用配置文件，支持小数如0.5（30分钟）",
    )
    parser.add_argument(
        "--threads", type=int, default=None, help="并发线程数，未指定时使用配置文件"
    )
    parser.add_argument(
        "--interval", type=float, default=None, help="操作间隔（秒），未指定时使用配置文件"
    )
    parser.add_argument(
        "--max-data", type=int, default=None, help="最大数据量（万条），未指定时使用配置文件"
    )
    parser.add_argument(
        "--degradation-threshold",
        type=float,
        default=None,
        help="性能劣化阈值（百分比），未指定时使用配置文件",
    )
    parser.add_argument(
        "--report-interval",
        type=float,
        default=None,
        help="报告生成间隔（分钟），未指定时使用配置文件",
    )
    parser.add_argument(
        "--multi-tenant-business-flow",
        action="store_true",
        help="启用多租户全业务链路老化模式",
    )
    parser.add_argument(
        "--target-tenants",
        type=str,
        default=None,
        help="多租户老化目标租户，逗号分隔，例如 t001,t002,t003,t004,t005",
    )

    args = parser.parse_args()

    config = AgingTestConfig()
    if args.duration is not None:
        config.duration_hours = args.duration
    if args.threads is not None:
        config.concurrent_threads = args.threads
    if args.interval is not None:
        config.operation_interval = args.interval
    if args.max_data is not None:
        config.max_data_count = args.max_data
    if args.degradation_threshold is not None:
        config.performance_degradation_threshold = args.degradation_threshold
    if args.report_interval is not None:
        config.report_interval_minutes = args.report_interval
    if args.multi_tenant_business_flow:
        config.multi_tenant_business_flow_enabled = True
    if args.target_tenants:
        config.target_tenants = [
            tenant_id.strip()
            for tenant_id in args.target_tenants.split(",")
            if tenant_id.strip()
        ]

    runner = AgingTestRunner(config)
    success = runner.run()
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    main()
