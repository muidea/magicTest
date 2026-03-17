"""Shared helpers for unittest-style VMI dependency setup."""

import logging
import random
import time
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def resolve_status_id(status_sdk, preferred_names=None) -> Optional[int]:
    """Resolve a usable status id from the server."""
    preferred_names = preferred_names or ["启用", "已启用", "正常", "active", "enabled"]
    preferred_names = {value.lower() for value in preferred_names}

    statuses = status_sdk.filter_status({"page": 1, "size": 100}) or []
    for item in statuses:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        name = str(item.get("name", "")).strip().lower()
        if name in preferred_names:
            return int(item["id"])

    for item in statuses:
        if isinstance(item, dict) and item.get("id"):
            return int(item["id"])

    return None


def record_entity(
    created_ids: Dict[str, list],
    class_cleanup_ids: Dict[str, list],
    entity_type: str,
    entity: Optional[Dict[str, Any]],
) -> Optional[int]:
    """Record an entity id into per-test and class-level cleanup registries."""
    if not entity or "id" not in entity:
        return None

    entity_id = int(entity["id"])
    if entity_type in created_ids:
        created_ids[entity_type].append(entity_id)
    if entity_type in class_cleanup_ids:
        class_cleanup_ids[entity_type].append(entity_id)
    return entity_id


def prepare_inventory_dependencies(
    *,
    store_sdk,
    warehouse_sdk,
    shelf_sdk,
    status_sdk,
    created_ids: Dict[str, list],
    class_cleanup_ids: Dict[str, list],
    product_sdk=None,
    product_info_sdk=None,
    goods_info_sdk=None,
    goods_info_type: int = 1,
) -> Dict[str, Optional[int]]:
    """Create real inventory dependencies for tests and record cleanup ids."""
    status_id = resolve_status_id(status_sdk)
    if not status_id:
        raise AssertionError("无法获取可用状态ID")

    suffix = uuid.uuid4().hex[:8]

    store = store_sdk.create_store(
        {
            "name": f"STORE_{suffix}",
            "description": f"测试店铺_{suffix}",
        }
    )
    if not store or "id" not in store:
        raise AssertionError("创建店铺失败")
    store_id = record_entity(created_ids, class_cleanup_ids, "store", store)

    warehouse = warehouse_sdk.create_warehouse(
        {
            "name": f"WAREHOUSE_{suffix}",
            "description": f"测试仓库_{suffix}",
        }
    )
    if not warehouse or "id" not in warehouse:
        raise AssertionError("创建仓库失败")
    warehouse_id = record_entity(created_ids, class_cleanup_ids, "warehouse", warehouse)

    shelf = shelf_sdk.create_shelf(
        {
            "description": f"测试货架_{suffix}",
            "capacity": 100,
            "warehouse": {"id": warehouse_id},
            "status": {"id": status_id},
        }
    )
    if not shelf or "id" not in shelf:
        raise AssertionError("创建货架失败")
    shelf_id = record_entity(created_ids, class_cleanup_ids, "shelf", shelf)

    result = {
        "status_id": status_id,
        "store_id": store_id,
        "warehouse_id": warehouse_id,
        "shelf_id": shelf_id,
        "product_id": None,
        "product_info_id": None,
        "goods_info_id": None,
    }

    if product_sdk and product_info_sdk:
        product = product_sdk.create_product(
            {
                "name": f"PRODUCT_{suffix}",
                "description": f"测试产品_{suffix}",
                "image": [],
                "expire": 365,
                "tags": ["test", suffix],
                "status": {"id": status_id},
            }
        )
        if not product or "id" not in product:
            raise AssertionError("创建产品失败")
        product_id = record_entity(created_ids, class_cleanup_ids, "product", product)
        result["product_id"] = product_id

        product_info = product_info_sdk.create_product_info(
            {
                "sku": str(int(time.time() * 1000) % 100000000 + random.randint(100, 999)),
                "description": f"测试产品SKU_{suffix}",
                "product": {"id": product_id},
            }
        )
        if not product_info or "id" not in product_info:
            raise AssertionError("创建产品SKU失败")
        product_info_id = record_entity(
            created_ids, class_cleanup_ids, "product_info", product_info
        )
        result["product_info_id"] = product_info_id

        if goods_info_sdk:
            goods_info = goods_info_sdk.create_goods_info(
                {
                    "sku": str(int(time.time() * 1000) % 100000000 + random.randint(1000, 9999)),
                    "product": {"id": product_info_id},
                    "type": goods_info_type,
                    "count": 100 if goods_info_type == 1 else 50,
                    "price": 99.99 if goods_info_type == 1 else 49.99,
                    "shelf": [{"id": shelf_id}],
                }
            )
            if not goods_info or "id" not in goods_info:
                raise AssertionError("创建商品信息失败")
            goods_info_id = record_entity(
                created_ids, class_cleanup_ids, "goods_info", goods_info
            )
            result["goods_info_id"] = goods_info_id

    logger.debug("inventory dependencies prepared: %s", result)
    return result


def prepare_store_dependency(
    *,
    store_sdk,
    created_ids: Dict[str, list],
    class_cleanup_ids: Dict[str, list],
) -> Dict[str, Optional[int]]:
    """Create a store dependency for store-bound tests."""
    suffix = uuid.uuid4().hex[:8]
    store = store_sdk.create_store(
        {
            "name": f"STORE_{suffix}",
            "description": f"测试店铺_{suffix}",
        }
    )
    if not store or "id" not in store:
        raise AssertionError("创建店铺失败")

    store_id = record_entity(created_ids, class_cleanup_ids, "store", store)
    return {"store_id": store_id}


def prepare_partner_dependency(
    *,
    partner_sdk,
    status_sdk,
    name_prefix: str = "PARTNER",
    description_prefix: str = "测试会员",
) -> Dict[str, Any]:
    """Create a partner dependency with a real status id from the server."""
    status_id = resolve_status_id(status_sdk)
    if not status_id:
        raise AssertionError("无法获取可用状态ID")

    suffix = uuid.uuid4().hex[:8]
    telephone = f"13{int(uuid.uuid4().hex[:9], 16) % 1000000000:09d}"
    partner = partner_sdk.create_partner(
        {
            "name": f"{name_prefix}_{suffix}",
            "telephone": telephone,
            "wechat": f"wechat_{suffix}",
            "description": f"{description_prefix}_{suffix}",
            "status": {"id": status_id},
        }
    )
    if not partner or "id" not in partner:
        raise AssertionError("创建会员失败")

    return {
        "status_id": status_id,
        "partner": partner,
        "partner_id": int(partner["id"]),
    }
