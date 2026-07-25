#!/usr/bin/env python3
"""
多租户配置助手模块

基于统一配置文件中的以下顶层字段生成多租户视图：
- default_tenant
- default_server_url
- tenant_targets
- tenant_url_template
- credentials
- tenant_user_pool
"""

import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENT_TENANT_IDS = ["t001", "t002", "t003", "t004", "t005"]


def _render_tenant_url(template: str, tenant_id: str) -> str:
    """Render a tenant URL template, accepting both {tenant} and {tenant_id}."""
    return template.format(tenant=tenant_id, tenant_id=tenant_id)


def _normalize_tenant_ids(raw_value: Any) -> List[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, str):
        candidates = raw_value.split(",")
    elif isinstance(raw_value, list):
        candidates = raw_value
    else:
        return []

    normalized: List[str] = []
    for candidate in candidates:
        tenant_id = str(candidate).strip()
        if tenant_id and tenant_id not in normalized:
            normalized.append(tenant_id)
    return normalized


def _build_tenant_entry(
    tenant_id: str,
    server_url: str,
    username: str,
    password: str,
) -> Dict[str, Any]:
    return {
        "server_url": server_url,
        "username": username,
        "password": password,
        "namespace": tenant_id,
        "enabled": True,
    }


def _build_tenant_user_entry(
    tenant_id: str,
    server_url: str,
    username: str,
    password: str,
    role_name: str,
    user_index: int,
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "server_url": server_url,
        "username": username,
        "password": password,
        "role_name": role_name,
        "user_index": user_index,
        "namespace": tenant_id,
        "enabled": True,
    }


def get_multi_tenant_config() -> Dict[str, Any]:
    """获取多租户配置视图。"""
    from config_helper import (
        get_config,
        get_credentials,
        get_server_url,
        get_tenant_url_template,
    )

    base_config = get_config()
    credentials = get_credentials()
    default_tenant = str(base_config.get("default_tenant", "autotest")).strip() or "autotest"
    default_server_url = get_server_url()
    tenant_targets = _normalize_tenant_ids(base_config.get("tenant_targets"))
    tenant_url_template = get_tenant_url_template()

    tenants: Dict[str, Dict[str, Any]] = {
        default_tenant: _build_tenant_entry(
            tenant_id=default_tenant,
            server_url=default_server_url,
            username=credentials["username"],
            password=credentials["password"],
        )
    }

    for tenant_id in tenant_targets:
        if tenant_id == default_tenant:
            continue
        tenants[tenant_id] = _build_tenant_entry(
            tenant_id=tenant_id,
            server_url=_render_tenant_url(tenant_url_template, tenant_id),
            username=credentials["username"],
            password=credentials["password"],
        )

    return {
        "enabled": len(tenant_targets) > 0,
        "default_tenant": default_tenant,
        "tenants": tenants,
    }


def get_preferred_concurrent_tenant_ids() -> List[str]:
    """获取并发和多租户老化默认使用的目标租户列表。"""
    from config_helper import get_tenant_targets

    configured_ids = _normalize_tenant_ids(get_tenant_targets())
    if configured_ids:
        return configured_ids
    return list(DEFAULT_CONCURRENT_TENANT_IDS)


def get_concurrent_tenant_configs(
    target_tenant_ids: Optional[List[str]] = None,
    auto_fill_missing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """获取并发多租户测试使用的租户配置。"""
    del auto_fill_missing

    config = get_multi_tenant_config()
    if not config["enabled"]:
        return {}

    tenant_ids = _normalize_tenant_ids(target_tenant_ids) if target_tenant_ids else get_preferred_concurrent_tenant_ids()
    return {
        tenant_id: dict(config["tenants"][tenant_id])
        for tenant_id in tenant_ids
        if tenant_id in config["tenants"] and config["tenants"][tenant_id].get("enabled", True)
    }


def get_concurrent_tenant_ids(
    target_tenant_ids: Optional[List[str]] = None,
    auto_fill_missing: bool = True,
) -> List[str]:
    """获取并发多租户测试实际会使用的租户ID列表。"""
    return list(
        get_concurrent_tenant_configs(
            target_tenant_ids=target_tenant_ids,
            auto_fill_missing=auto_fill_missing,
        ).keys()
    )


def get_multi_tenant_user_configs(
    target_tenant_ids: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """获取多租户多用户测试矩阵。

    返回格式:
        {
            "t001": [
                {
                    "tenant_id": "t001",
                    "server_url": "https://t001.local.vpc",
                    "username": "e2euser_t001_001",
                    "password": "Test@123",
                    "role_name": "e2e_multi_user_t001",
                    "user_index": 1,
                    "namespace": "",
                    "enabled": True,
                }
            ]
        }
    """
    from config_helper import get_tenant_user_pool_config

    tenant_pool = get_tenant_user_pool_config()
    if not tenant_pool.get("enabled") or int(tenant_pool.get("users_per_tenant", 0)) <= 0:
        return {}

    multi_tenant_config = get_multi_tenant_config()
    tenant_configs = get_concurrent_tenant_configs(target_tenant_ids=target_tenant_ids)
    if tenant_pool.get("include_default_tenant"):
        default_tenant = multi_tenant_config["default_tenant"]
        default_config = multi_tenant_config["tenants"].get(default_tenant)
        if default_config and default_tenant not in tenant_configs:
            tenant_configs[default_tenant] = dict(default_config)

    account_prefix = str(tenant_pool.get("account_prefix", "e2euser")).strip() or "e2euser"
    default_password = str(tenant_pool.get("default_password", "Test@123"))
    role_name_template = str(
        tenant_pool.get("role_name_template", "e2e_multi_user_{tenant}")
    )
    users_per_tenant = int(tenant_pool.get("users_per_tenant", 0))

    user_configs: Dict[str, List[Dict[str, Any]]] = {}
    for tenant_id, tenant_config in tenant_configs.items():
        role_name = role_name_template.format(tenant=tenant_id, tenant_id=tenant_id)
        tenant_users: List[Dict[str, Any]] = []
        for index in range(1, users_per_tenant + 1):
            username = f"{account_prefix}_{tenant_id}_{index:03d}"
            tenant_users.append(
                _build_tenant_user_entry(
                    tenant_id=tenant_id,
                    server_url=str(tenant_config["server_url"]),
                    username=username,
                    password=default_password,
                    role_name=role_name,
                    user_index=index,
                )
            )
        user_configs[tenant_id] = tenant_users
    return user_configs


def get_flat_multi_tenant_user_configs(
    target_tenant_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """按平铺形式返回多租户多用户测试矩阵。"""
    user_configs = get_multi_tenant_user_configs(target_tenant_ids=target_tenant_ids)
    flattened: List[Dict[str, Any]] = []
    for tenant_users in user_configs.values():
        flattened.extend(tenant_users)
    return flattened


def is_multi_tenant_enabled() -> bool:
    """检查多租户功能是否启用。"""
    return get_multi_tenant_config()["enabled"]


def get_tenant_config(tenant_id: str = "autotest") -> Optional[Dict[str, Any]]:
    """获取指定租户的配置。"""
    config = get_multi_tenant_config()
    default_tenant = config["default_tenant"]

    if not config["enabled"] and tenant_id != default_tenant:
        logger.warning(
            "多租户未启用，只支持默认租户 '%s'，请求的租户: %s",
            default_tenant,
            tenant_id,
        )
        return None

    return config["tenants"].get(tenant_id)


def get_all_tenant_ids() -> List[str]:
    """获取所有启用的租户ID列表。"""
    config = get_multi_tenant_config()
    if not config["enabled"]:
        return [config["default_tenant"]]

    return [
        tenant_id
        for tenant_id, tenant_config in config["tenants"].items()
        if tenant_config.get("enabled", True)
    ]


def get_default_tenant_id() -> str:
    """获取默认租户ID。"""
    return get_multi_tenant_config()["default_tenant"]


def validate_tenant_config(tenant_config: Dict[str, Any]) -> bool:
    """验证租户配置的有效性。"""
    required_fields = ["server_url", "username", "password", "namespace"]

    for field in required_fields:
        if field not in tenant_config:
            logger.error("租户配置缺少必要字段: %s", field)
            return False

    for field in ["server_url", "username", "password"]:
        if not tenant_config[field]:
            logger.error("租户配置字段不能为空: %s", field)
            return False

    server_url = tenant_config["server_url"]
    if not (server_url.startswith("http://") or server_url.startswith("https://")):
        logger.error("服务器URL格式无效: %s", server_url)
        return False

    return True


def create_multi_tenant_config_template() -> Dict[str, Any]:
    """创建精简后的统一配置模板。"""
    return {
        "mode": "aging_multi_tenant",
        "environment": "remote",
        "default_tenant": "autotest",
        "request_namespace": "",
        "request_application": "",
        "default_server_url": "https://autotest.remote.vpc",
        "tenant_targets": list(DEFAULT_CONCURRENT_TENANT_IDS),
        "tenant_url_template": "https://{tenant}.remote.vpc",
        "credentials": {
            "username": "administrator",
            "password": "administrator",
        },
        "tenant_user_pool": {
            "enabled": False,
            "users_per_tenant": 0,
            "account_prefix": "e2euser",
            "default_password": "Test@123",
            "role_name_template": "e2e_multi_user_{tenant}",
            "include_default_tenant": False,
            "verify_login": True,
        },
        "target": {
            "remote_host": "",
            "remote_user": "",
            "deployment_mode": "",
        },
        "observability": {
            "prometheus_url": "",
        },
        "session": {
            "refresh_interval": 540,
            "timeout": 1800,
        },
        "concurrent": {
            "max_workers": 40,
            "timeout": 900,
            "retry_count": 3,
            "workers_per_tenant": 8,
            "iterations_per_worker": 16,
            "write_every": 2,
            "hotspot_read_rounds": 1,
            "hotspot_query_rounds": 1,
            "hotspot_prewrite_query": False,
            "hotspot_shared_context_per_tenant": True,
            "hotspot_measure_loop_only": True,
        },
        "aging": {
            "duration_hours": 24,
            "concurrent_threads": 10,
            "operation_interval": 1.0,
            "max_data_count": 1000,
            "performance_degradation_threshold": 20.0,
            "report_interval_minutes": 5,
            "multi_tenant_business_flow_enabled": True,
        },
    }


def save_multi_tenant_config(
    config: Dict[str, Any], filepath: str = "test_config.generated.json"
) -> bool:
    """保存多租户配置到文件。"""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("多租户配置已保存到: %s", filepath)
        return True
    except Exception as exc:
        logger.error("保存多租户配置失败: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info("=" * 60)
    logger.info("多租户配置助手测试")
    logger.info("=" * 60)

    config = get_multi_tenant_config()
    logger.info("多租户启用状态: %s", config["enabled"])
    logger.info("默认租户: %s", config["default_tenant"])
    logger.info("可用租户数量: %s", len(config["tenants"]))
    logger.info("并发目标租户: %s", get_preferred_concurrent_tenant_ids())

    for tenant_id in get_all_tenant_ids():
        tenant_config = get_tenant_config(tenant_id)
        if tenant_config:
            logger.info("租户 '%s' 配置:", tenant_id)
            logger.info("  服务器: %s", tenant_config["server_url"])
            logger.info("  命名空间: %s", tenant_config["namespace"])
            logger.info("  用户名: %s", tenant_config["username"])

    logger.info("=" * 60)
    logger.info("多租户配置模板:")
    logger.info("=" * 60)
    logger.info("%s", json.dumps(create_multi_tenant_config_template(), indent=2, ensure_ascii=False))
