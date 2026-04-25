#!/usr/bin/env python3
"""
多租户多用户准备器

职责：
1. 基于 tenant_targets + tenant_user_pool 生成用户矩阵
2. 在指定租户列表内按需创建测试 role / account
3. 可选验证新建账号登录
4. 输出后续测试可直接消费的用户矩阵报告
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent
for component in ("session", "cas", "mock"):
    component_path = str(PROJECT_ROOT / component)
    if component_path not in sys.path:
        sys.path.insert(0, component_path)
package_dir = str(PACKAGE_DIR)
if package_dir not in sys.path:
    sys.path.insert(0, package_dir)

from config_helper import get_credentials, get_tenant_user_pool_config
from tenant_config_helper import get_multi_tenant_user_configs


STATUS_ENABLE = 2
ALL_PERMISSION = 5


def _all_privilege() -> List[Dict[str, Any]]:
    return [
        {
            "module": "*",
            "uriPath": "*",
            "value": ALL_PERMISSION,
            "description": "tenant multi-user test privilege",
        }
    ]


class TenantUserProvisioner:
    """在指定租户列表下创建并校验测试用户。"""

    def __init__(
        self,
        session_factory: Optional[Callable[..., Any]] = None,
        cas_factory: Optional[Callable[..., Any]] = None,
        role_factory: Optional[Callable[..., Any]] = None,
        account_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        if session_factory is None:
            from session import MagicSession

            session_factory = MagicSession
        if cas_factory is None:
            from cas.cas import Cas

            cas_factory = Cas
        if role_factory is None:
            from role.role import Role

            role_factory = Role
        if account_factory is None:
            from account.account import Account

            account_factory = Account

        self.session_factory = session_factory
        self.cas_factory = cas_factory
        self.role_factory = role_factory
        self.account_factory = account_factory

    def _login_admin(self, server_url: str):
        credentials = get_credentials()
        work_session = self.session_factory(server_url, credentials.get("namespace", ""))
        cas_client = self.cas_factory(work_session)
        if not cas_client.login(credentials["username"], credentials["password"]):
            raise RuntimeError(
                f"租户管理账号登录失败: server={server_url}, error={cas_client.get_last_error()}"
            )
        work_session.bind_token(cas_client.get_session_token())
        return work_session

    def _find_role(self, role_app, role_name: str) -> Optional[Dict[str, Any]]:
        roles = role_app.filter_role({"name": role_name}) or []
        for role in roles:
            if role.get("name") == role_name:
                return role
        return None

    def _ensure_role(self, role_app, role_name: str) -> Dict[str, Any]:
        role = self._find_role(role_app, role_name)
        if role is not None:
            return role
        role = role_app.create_role(
            {
                "name": role_name,
                "description": f"multi-tenant test role {role_name}",
                "group": "e2e",
                "privilege": _all_privilege(),
                "status": STATUS_ENABLE,
            }
        )
        if role is None:
            raise RuntimeError(f"创建角色失败: role={role_name}")
        return role

    def _find_account(self, account_app, username: str) -> Optional[Dict[str, Any]]:
        accounts = account_app.filter_account({"account": username}) or []
        for account in accounts:
            if account.get("account") == username:
                return account
        return None

    def _ensure_account(
        self,
        account_app,
        username: str,
        password: str,
        role: Dict[str, Any],
    ) -> Dict[str, Any]:
        account = self._find_account(account_app, username)
        if account is not None:
            return account
        account = account_app.create_account(
            {
                "account": username,
                "password": password,
                "email": f"{username}@example.com",
                "description": f"multi-tenant test user {username}",
                "status": STATUS_ENABLE,
                "role": {
                    "id": role["id"],
                    "name": role["name"],
                    "status": role.get("status", STATUS_ENABLE),
                },
            }
        )
        if account is None:
            raise RuntimeError(f"创建账号失败: account={username}")
        return account

    def _verify_login(self, server_url: str, username: str, password: str) -> None:
        verify_session = self.session_factory(server_url, "")
        verify_cas = self.cas_factory(verify_session)
        if not verify_cas.login(username, password):
            raise RuntimeError(
                f"校验账号登录失败: server={server_url}, account={username}, error={verify_cas.get_last_error()}"
            )

    def prepare(
        self,
        target_tenant_ids: Optional[List[str]] = None,
        verify_login: Optional[bool] = None,
    ) -> Dict[str, Any]:
        user_pool = get_tenant_user_pool_config()
        desired_users = get_multi_tenant_user_configs(target_tenant_ids=target_tenant_ids)
        if not desired_users:
            return {
                "enabled": False,
                "tenants": {},
                "summary": {
                    "tenant_count": 0,
                    "user_count": 0,
                    "created_accounts": 0,
                    "reused_accounts": 0,
                    "verified_accounts": 0,
                },
            }

        verify_enabled = user_pool.get("verify_login", True) if verify_login is None else verify_login
        report: Dict[str, Any] = {
            "enabled": True,
            "tenants": {},
            "summary": {
                "tenant_count": 0,
                "user_count": 0,
                "created_accounts": 0,
                "reused_accounts": 0,
                "verified_accounts": 0,
            },
        }

        for tenant_id, user_specs in desired_users.items():
            if not user_specs:
                continue

            server_url = user_specs[0]["server_url"]
            admin_session = self._login_admin(server_url)
            role_app = self.role_factory(admin_session)
            account_app = self.account_factory(admin_session)
            role = self._ensure_role(role_app, user_specs[0]["role_name"])

            tenant_report = {
                "server_url": server_url,
                "role": {
                    "id": role.get("id"),
                    "name": role.get("name"),
                },
                "users": [],
            }

            for user_spec in user_specs:
                existing_account = self._find_account(account_app, user_spec["username"])
                account = self._ensure_account(
                    account_app=account_app,
                    username=user_spec["username"],
                    password=user_spec["password"],
                    role=role,
                )
                created = existing_account is None
                if created:
                    report["summary"]["created_accounts"] += 1
                else:
                    report["summary"]["reused_accounts"] += 1

                if verify_enabled:
                    self._verify_login(
                        server_url=user_spec["server_url"],
                        username=user_spec["username"],
                        password=user_spec["password"],
                    )
                    report["summary"]["verified_accounts"] += 1

                tenant_report["users"].append(
                    {
                        "tenant_id": tenant_id,
                        "account_id": account.get("id"),
                        "username": user_spec["username"],
                        "password": user_spec["password"],
                        "user_index": user_spec["user_index"],
                        "role_name": user_spec["role_name"],
                        "created": created,
                    }
                )
                report["summary"]["user_count"] += 1

            report["tenants"][tenant_id] = tenant_report
            report["summary"]["tenant_count"] += 1
            logger.info(
                "租户用户准备完成 tenant=%s users=%s role=%s",
                tenant_id,
                len(tenant_report["users"]),
                tenant_report["role"]["name"],
            )
        return report


def save_report(report: Dict[str, Any], report_file: str) -> None:
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("租户用户矩阵已写入: %s", report_file)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="多租户多用户准备器")
    parser.add_argument("--tenant-targets", help="指定租户列表，格式 t001,t002")
    parser.add_argument(
        "--report-file",
        default="tenant-user-matrix.generated.json",
        help="输出用户矩阵报告文件",
    )
    parser.add_argument(
        "--no-verify-login",
        action="store_true",
        help="创建账号后不额外校验登录",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="只打印当前将要使用的租户用户矩阵，不执行创建",
    )
    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    target_tenant_ids = None
    if args.tenant_targets:
        target_tenant_ids = [
            tenant_id.strip()
            for tenant_id in args.tenant_targets.split(",")
            if tenant_id.strip()
        ]

    planned_users = get_multi_tenant_user_configs(target_tenant_ids=target_tenant_ids)
    if args.print_only:
        print(json.dumps(planned_users, indent=2, ensure_ascii=False))
        return 0

    provisioner = TenantUserProvisioner()
    report = provisioner.prepare(
        target_tenant_ids=target_tenant_ids,
        verify_login=not args.no_verify_login,
    )
    save_report(report, args.report_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
