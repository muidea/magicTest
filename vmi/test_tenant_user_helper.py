#!/usr/bin/env python3

import unittest
from unittest.mock import patch


class FakeSession:
    def __init__(self, server_url, namespace=""):
        self.server_url = server_url
        self.namespace = namespace
        self.token = None

    def bind_token(self, token):
        self.token = token


class FakeCas:
    def __init__(self, session):
        self.session = session
        self._token = "fake-token"
        self._last_error = None

    def login(self, account, password):
        self._token = f"token-{account}"
        return True

    def get_session_token(self):
        return self._token

    def get_last_error(self):
        return self._last_error


class FakeRoleApp:
    roles = {}

    def __init__(self, session):
        self.session = session

    def filter_role(self, param):
        role = self.roles.get(param.get("name"))
        return [dict(role)] if role else []

    def create_role(self, param):
        role = dict(param)
        role["id"] = len(self.roles) + 1
        self.roles[param["name"]] = dict(role)
        return dict(role)


class FakeAccountApp:
    accounts = {}

    def __init__(self, session):
        self.session = session

    def filter_account(self, param):
        account = self.accounts.get(param.get("account"))
        return [dict(account)] if account else []

    def create_account(self, param):
        account = dict(param)
        account["id"] = len(self.accounts) + 1
        self.accounts[param["account"]] = dict(account)
        return dict(account)


class TestTenantUserProvisioner(unittest.TestCase):
    def setUp(self):
        FakeRoleApp.roles = {}
        FakeAccountApp.accounts = {}

    @patch(
        "tenant_user_helper.get_multi_tenant_user_configs",
        return_value={
            "t001": [
                {
                    "tenant_id": "t001",
                    "server_url": "https://t001.local.vpc",
                    "username": "loaduser_t001_001",
                    "password": "Test@123",
                    "role_name": "load_role_t001",
                    "user_index": 1,
                    "namespace": "",
                    "enabled": True,
                },
                {
                    "tenant_id": "t001",
                    "server_url": "https://t001.local.vpc",
                    "username": "loaduser_t001_002",
                    "password": "Test@123",
                    "role_name": "load_role_t001",
                    "user_index": 2,
                    "namespace": "",
                    "enabled": True,
                },
            ]
        },
    )
    @patch(
        "tenant_user_helper.get_tenant_user_pool_config",
        return_value={"enabled": True, "verify_login": True},
    )
    def test_prepare_creates_missing_users(self, _pool_mock, _config_mock):
        from tenant_user_helper import TenantUserProvisioner

        provisioner = TenantUserProvisioner(
            session_factory=FakeSession,
            cas_factory=FakeCas,
            role_factory=FakeRoleApp,
            account_factory=FakeAccountApp,
        )
        report = provisioner.prepare()
        self.assertTrue(report["enabled"])
        self.assertEqual(report["summary"]["tenant_count"], 1)
        self.assertEqual(report["summary"]["user_count"], 2)
        self.assertEqual(report["summary"]["created_accounts"], 2)
        self.assertEqual(report["summary"]["reused_accounts"], 0)
        self.assertEqual(report["summary"]["verified_accounts"], 2)
        self.assertIn("load_role_t001", FakeRoleApp.roles)
        self.assertIn("loaduser_t001_001", FakeAccountApp.accounts)

    @patch(
        "tenant_user_helper.get_multi_tenant_user_configs",
        return_value={
            "t001": [
                {
                    "tenant_id": "t001",
                    "server_url": "https://t001.local.vpc",
                    "username": "loaduser_t001_001",
                    "password": "Test@123",
                    "role_name": "load_role_t001",
                    "user_index": 1,
                    "namespace": "",
                    "enabled": True,
                }
            ]
        },
    )
    @patch(
        "tenant_user_helper.get_tenant_user_pool_config",
        return_value={"enabled": True, "verify_login": False},
    )
    def test_prepare_reuses_existing_users(self, _pool_mock, _config_mock):
        from tenant_user_helper import TenantUserProvisioner

        FakeRoleApp.roles["load_role_t001"] = {
            "id": 11,
            "name": "load_role_t001",
            "status": 2,
        }
        FakeAccountApp.accounts["loaduser_t001_001"] = {
            "id": 21,
            "account": "loaduser_t001_001",
            "status": 2,
        }

        provisioner = TenantUserProvisioner(
            session_factory=FakeSession,
            cas_factory=FakeCas,
            role_factory=FakeRoleApp,
            account_factory=FakeAccountApp,
        )
        report = provisioner.prepare()
        self.assertEqual(report["summary"]["created_accounts"], 0)
        self.assertEqual(report["summary"]["reused_accounts"], 1)
        self.assertEqual(report["summary"]["verified_accounts"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
