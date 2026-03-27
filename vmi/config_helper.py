#!/usr/bin/env python3
"""
配置助手模块 - 从统一配置文件读取服务器地址和认证信息
"""

import json
import logging
import os
from copy import deepcopy
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "test_config.json")
DEFAULT_TENANT_TARGETS = ["t001", "t002", "t003", "t004", "t005"]

_config_cache = None

DEFAULT_CONFIG: Dict[str, Any] = {
    "mode": "single_tenant",
    "environment": "local",
    "default_tenant": "autotest",
    "request_namespace": "",
    "default_server_url": "https://autotest.local.vpc",
    "tenant_targets": [],
    "tenant_url_template": "https://{tenant}.local.vpc",
    "credentials": {"username": "administrator", "password": "administrator"},
    "session": {"refresh_interval": 540, "timeout": 1800},
    "pytest": {
        "markers": [
            "basic: 基础功能测试",
            "concurrent: 并发测试",
            "scenario: 业务场景测试",
            "aging: 老化测试",
            "smoke: 冒烟测试",
            "integration: 集成测试",
            "performance: 性能测试",
        ],
        "addopts": ["-v", "--tb=short", "--strict-markers", "--durations=10"],
        "log_level": "INFO",
    },
    "concurrent": {"max_workers": 10, "timeout": 30, "retry_count": 3},
    "aging": {
        "duration_hours": 24,
        "concurrent_threads": 10,
        "operation_interval": 1.0,
        "max_data_count": 1000,
        "performance_degradation_threshold": 20.0,
        "report_interval_minutes": 30,
        "multi_tenant_business_flow_enabled": False,
    },
    "coverage": {
        "source": ["."],
        "omit": [
            "*/test_*.py",
            "*/__pycache__/*",
            "*/.*",
            "*/venv/*",
            "*/virtualenv/*",
        ],
    },
}


def _merge_nested_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _normalize_tenant_targets(raw_value: Any) -> List[str]:
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


def _normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _merge_nested_dict(DEFAULT_CONFIG, config)
    normalized["tenant_targets"] = _normalize_tenant_targets(
        normalized.get("tenant_targets")
    )
    return normalized


def get_config() -> Dict[str, Any]:
    """获取统一配置文件。"""
    global _config_cache

    if _config_cache is not None:
        return _config_cache

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _config_cache = _normalize_config(json.load(f))
                return _config_cache
        except Exception as exc:
            logger.warning("读取配置文件失败，使用默认配置: %s", exc)

    _config_cache = deepcopy(DEFAULT_CONFIG)
    return _config_cache


def get_server_url() -> str:
    """获取默认服务器地址。"""
    return str(get_config().get("default_server_url", DEFAULT_CONFIG["default_server_url"]))


def get_credentials() -> Dict[str, str]:
    """获取认证信息。"""
    creds = get_config().get("credentials", {})
    return {
        "username": str(creds.get("username", "administrator")),
        "password": str(creds.get("password", "administrator")),
        "namespace": get_namespace(),
    }


def get_username() -> str:
    """获取用户名。"""
    return get_credentials()["username"]


def get_password() -> str:
    """获取密码。"""
    return get_credentials()["password"]


def get_namespace() -> str:
    """获取请求头使用的命名空间。"""
    return str(get_config().get("request_namespace", ""))


def get_default_tenant() -> str:
    """获取默认租户。"""
    return str(get_config().get("default_tenant", "autotest"))


def get_tenant_targets() -> List[str]:
    """获取启用的多租户目标列表。"""
    return list(get_config().get("tenant_targets", []))


def get_tenant_url_template() -> str:
    """获取租户 URL 模板。"""
    return str(
        get_config().get("tenant_url_template", DEFAULT_CONFIG["tenant_url_template"])
    )


def get_aging_params() -> Dict[str, Any]:
    """获取老化测试参数。"""
    return dict(get_config().get("aging", {}))


def get_session_config() -> Dict[str, Any]:
    """获取会话配置。"""
    return dict(get_config().get("session", {}))


def get_concurrent_config() -> Dict[str, Any]:
    """获取并发配置。"""
    return dict(get_config().get("concurrent", {}))


def get_test_mode() -> str:
    """获取测试模式。"""
    return str(get_config().get("mode", "single_tenant"))


def get_environment() -> str:
    """获取环境。"""
    return str(get_config().get("environment", "local"))


def get_max_workers() -> int:
    """获取最大工作线程数。"""
    return int(get_concurrent_config().get("max_workers", 10))


def get_timeout() -> int:
    """获取超时时间。"""
    return int(get_concurrent_config().get("timeout", 30))


def get_retry_count() -> int:
    """获取重试次数。"""
    return int(get_concurrent_config().get("retry_count", 3))


def update_config(server_url=None, username=None, password=None, namespace=None) -> bool:
    """更新配置文件。"""
    global _config_cache

    config = get_config()

    if server_url:
        config["default_server_url"] = server_url
    if username:
        config.setdefault("credentials", {})["username"] = username
    if password:
        config.setdefault("credentials", {})["password"] = password
    if namespace:
        config["request_namespace"] = namespace

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _config_cache = None
        return True
    except Exception as exc:
        logger.error("保存配置文件失败: %s", exc)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("当前配置:")
    logger.info("  运行模式: %s", get_test_mode())
    logger.info("  环境: %s", get_environment())
    logger.info("  服务器地址: %s", get_server_url())
    logger.info("  用户名: %s", get_username())
    logger.info("  命名空间: %s", get_namespace())
    logger.info("  多租户目标: %s", get_tenant_targets() or DEFAULT_TENANT_TARGETS)
