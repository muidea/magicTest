#!/usr/bin/env python3
"""
多租户配置助手模块 - 扩展配置系统以支持多租户测试

特性：
1. 向后兼容：完全支持现有的单租户配置
2. 可选启用：多租户功能默认禁用，需要时启用
3. 灵活配置：租户数量在实际测试时配置
4. 最小变更：不修改现有配置文件格式，只扩展
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONCURRENT_TENANT_IDS = ["t001", "t002", "t003", "t004", "t005"]


def get_multi_tenant_config() -> Dict[str, Any]:
    """获取多租户配置

    返回包含多租户配置的字典，结构：
    {
        "enabled": False,  # 多租户是否启用
        "default_tenant": "autotest",  # 默认租户ID
        "tenants": {  # 租户配置字典
            "autotest": {
                "server_url": "https://autotest.local.vpc",
                "username": "administrator",
                "password": "administrator",
                "namespace": "autotest",
                "enabled": True
            }
        }
    }
    """
    # 首先获取现有配置
    from config_helper import get_config

    base_config = get_config()

    # 构建多租户配置
    multi_tenant_config = {
        "enabled": False,  # 默认禁用多租户
        "default_tenant": "autotest",
        "tenants": {},
    }

    # 从基础配置中提取默认租户信息
    default_tenant_id = "autotest"
    default_tenant_config = {
        "server_url": base_config.get("server_url", "https://autotest.local.vpc"),
        "username": base_config.get("username", "administrator"),
        "password": base_config.get("password", "administrator"),
        "namespace": base_config.get("namespace", "autotest"),
        "enabled": True,
    }

    # 检查是否启用了多租户配置
    if "multi_tenant" in base_config and base_config["multi_tenant"].get(
        "enabled", False
    ):
        multi_tenant_config["enabled"] = True

        # 处理多租户配置
        mt_config = base_config["multi_tenant"]

        # 设置默认租户ID
        multi_tenant_config["default_tenant"] = mt_config.get(
            "default_tenant", "autotest"
        )

        # 添加所有租户配置
        for tenant in mt_config.get("tenants", []):
            tenant_id = tenant.get("id")
            if not tenant_id:
                logger.warning("跳过无ID的租户配置")
                continue

            # 构建租户配置，使用提供的值或默认值
            tenant_config = {
                "server_url": tenant.get(
                    "server_url", default_tenant_config["server_url"]
                ),
                "username": tenant.get("username", default_tenant_config["username"]),
                "password": tenant.get("password", default_tenant_config["password"]),
                "namespace": tenant.get(
                    "namespace", tenant_id
                ),  # 默认使用租户ID作为namespace
                "enabled": tenant.get("enabled", True),
            }

            multi_tenant_config["tenants"][tenant_id] = tenant_config

    # 总是添加默认租户（autotest）
    if default_tenant_id not in multi_tenant_config["tenants"]:
        multi_tenant_config["tenants"][default_tenant_id] = default_tenant_config

    return multi_tenant_config


def get_preferred_concurrent_tenant_ids() -> List[str]:
    """获取并发多租户测试优先使用的租户ID列表。"""
    from config_helper import get_config

    base_config = get_config()
    concurrent_config = base_config.get("concurrent", {})
    configured_ids = concurrent_config.get("multi_tenant_target_tenants")

    if isinstance(configured_ids, list):
        tenant_ids = [str(tenant_id).strip() for tenant_id in configured_ids]
        tenant_ids = [tenant_id for tenant_id in tenant_ids if tenant_id]
        if tenant_ids:
            return tenant_ids

    return list(DEFAULT_CONCURRENT_TENANT_IDS)


def _build_fallback_tenant_config(tenant_id: str) -> Optional[Dict[str, Any]]:
    """基于默认租户为并发测试补齐目标租户配置。"""
    config = get_multi_tenant_config()
    default_tenant_id = config.get("default_tenant", "autotest")
    default_config = config.get("tenants", {}).get(default_tenant_id)

    if not default_config:
        default_config = config.get("tenants", {}).get("autotest")

    if not default_config:
        logger.warning("无法为租户 '%s' 生成默认配置，缺少基准租户配置", tenant_id)
        return None

    fallback_config = dict(default_config)
    fallback_config["namespace"] = tenant_id
    fallback_config["enabled"] = True
    return fallback_config


def get_concurrent_tenant_configs(
    target_tenant_ids: Optional[List[str]] = None,
    auto_fill_missing: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """获取并发多租户测试使用的租户配置。

    当多租户已启用但目标租户未在配置文件中逐个声明时，
    会基于默认租户自动派生 `server_url/username/password`，并将 `namespace`
    替换为目标租户ID，便于对 t001-t005 这类批量租户直接发起并发测试。
    """
    config = get_multi_tenant_config()
    if not config.get("enabled", False):
        return {}

    resolved_configs: Dict[str, Dict[str, Any]] = {}
    tenant_ids = target_tenant_ids or get_preferred_concurrent_tenant_ids()

    for tenant_id in tenant_ids:
        tenant_config = config["tenants"].get(tenant_id)
        if tenant_config and tenant_config.get("enabled", True):
            resolved_configs[tenant_id] = dict(tenant_config)
            continue

        if auto_fill_missing:
            fallback_config = _build_fallback_tenant_config(tenant_id)
            if fallback_config:
                resolved_configs[tenant_id] = fallback_config

    return resolved_configs


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


def is_multi_tenant_enabled() -> bool:
    """检查多租户功能是否启用"""
    config = get_multi_tenant_config()
    return config["enabled"]


def get_tenant_config(tenant_id: str = "autotest") -> Optional[Dict[str, Any]]:
    """获取指定租户的配置

    Args:
        tenant_id: 租户ID，默认为"autotest"

    Returns:
        租户配置字典，如果租户不存在则返回None
    """
    config = get_multi_tenant_config()

    # 如果多租户未启用，只返回默认租户
    if not config["enabled"] and tenant_id != "autotest":
        logger.warning(f"多租户未启用，只支持autotest租户，请求的租户: {tenant_id}")
        return None

    return config["tenants"].get(tenant_id)


def get_all_tenant_ids() -> List[str]:
    """获取所有启用的租户ID列表"""
    config = get_multi_tenant_config()

    # 如果多租户未启用，只返回默认租户
    if not config["enabled"]:
        return ["autotest"]

    # 返回所有启用的租户
    return [
        tid
        for tid, tconfig in config["tenants"].items()
        if tconfig.get("enabled", True)
    ]


def get_default_tenant_id() -> str:
    """获取默认租户ID"""
    config = get_multi_tenant_config()
    return config["default_tenant"]


def validate_tenant_config(tenant_config: Dict[str, Any]) -> bool:
    """验证租户配置的有效性

    Args:
        tenant_config: 租户配置字典

    Returns:
        配置是否有效
    """
    required_fields = ["server_url", "username", "password", "namespace"]

    for field in required_fields:
        if field not in tenant_config or not tenant_config[field]:
            logger.error(f"租户配置缺少必要字段: {field}")
            return False

    # 验证服务器URL格式
    server_url = tenant_config["server_url"]
    if not (server_url.startswith("http://") or server_url.startswith("https://")):
        logger.error(f"服务器URL格式无效: {server_url}")
        return False

    return True


def create_multi_tenant_config_template() -> Dict[str, Any]:
    """创建多租户配置模板

    返回可用于创建多租户配置的模板字典
    """
    return {
        "server_url": "https://autotest.local.vpc",
        "username": "administrator",
        "password": "administrator",
        "namespace": "autotest",
        "test_mode": "functional",
        "environment": "remote",
        "max_workers": 10,
        "concurrent_timeout": 30,
        "retry_count": 3,
        "concurrent": {
            "multi_tenant_target_tenants": list(DEFAULT_CONCURRENT_TENANT_IDS)
        },
        "multi_tenant": {
            "enabled": False,  # 设置为True启用多租户
            "default_tenant": "autotest",
            "tenants": [
                {
                    "id": "autotest",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "autotest",
                    "enabled": True,
                },
                {
                    "id": "t001",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "t001",
                    "enabled": True,
                },
                {
                    "id": "t002",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "t002",
                    "enabled": True,
                },
                {
                    "id": "t003",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "t003",
                    "enabled": True,
                },
                {
                    "id": "t004",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "t004",
                    "enabled": True,
                },
                {
                    "id": "t005",
                    "server_url": "https://autotest.local.vpc",
                    "username": "administrator",
                    "password": "administrator",
                    "namespace": "t005",
                    "enabled": True,
                },
            ],
        },
    }


def save_multi_tenant_config(
    config: Dict[str, Any], filepath: str = "test_config_multi_tenant.json"
) -> bool:
    """保存多租户配置到文件

    Args:
        config: 配置字典
        filepath: 保存路径

    Returns:
        保存是否成功
    """
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info(f"多租户配置已保存到: {filepath}")
        return True
    except Exception as e:
        logger.error(f"保存多租户配置失败: {e}")
        return False


# 测试代码
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO)

    logger.info("=" * 60)
    logger.info("多租户配置助手测试")
    logger.info("=" * 60)

    # 测试获取配置
    config = get_multi_tenant_config()
    logger.info("多租户启用状态: %s", config["enabled"])
    logger.info("默认租户: %s", config["default_tenant"])
    logger.info("可用租户数量: %s", len(config["tenants"]))

    # 测试获取租户ID列表
    tenant_ids = get_all_tenant_ids()
    logger.info("启用的租户ID: %s", tenant_ids)

    # 测试获取单个租户配置
    for tenant_id in tenant_ids:
        tenant_config = get_tenant_config(tenant_id)
        if tenant_config:
            logger.info("租户 '%s' 配置:", tenant_id)
            logger.info("  服务器: %s", tenant_config["server_url"])
            logger.info("  命名空间: %s", tenant_config["namespace"])
            logger.info("  用户名: %s", tenant_config["username"])

    # 显示配置模板
    logger.info("=" * 60)
    logger.info("多租户配置模板:")
    logger.info("=" * 60)
    template = create_multi_tenant_config_template()
    logger.info("%s", json.dumps(template, indent=2, ensure_ascii=False))

    logger.info("多租户配置助手测试完成")
