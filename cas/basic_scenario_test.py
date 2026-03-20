import unittest

from session import MagicSession

from cas import Cas
from test_support import CasE2EBase, UNSET


class BasicScenarioTestCase(CasE2EBase):
    def test_panel_default_bootstrap_chain_is_visible(self):
        roles = self.role_app.filter_role({"name": "superRole"})
        self.assertIsNotNone(roles, "查询默认 role 失败")
        self.assertTrue(roles, "默认 superRole 不存在")
        role = roles[0]

        accounts = self.account_app.filter_account({"account": "administrator"})
        self.assertIsNotNone(accounts, "查询默认 account 失败")
        self.assertTrue(accounts, "默认 administrator 不存在")
        account = accounts[0]

        endpoints = self.endpoint_app.filter_endpoint({"name": "defaultEndpoint"})
        self.assertIsNotNone(endpoints, "查询默认 endpoint 失败")
        self.assertTrue(endpoints, "默认 endpoint 不存在")
        endpoint = endpoints[0]

        self.assertEqual(account["role"]["id"], role["id"])
        self.assertEqual(endpoint["account"]["id"], account["id"])
        self.assertEqual(endpoint["role"]["id"], role["id"])
        self.assertEqual(endpoint["scope"], self.panel_namespace)
        self.assertTrue(endpoint.get("authToken"), "默认 endpoint 应持有 authToken")

        endpoint_session = MagicSession(self.server_url, self.panel_namespace)
        endpoint_session.bind_auth_secret(endpoint["name"], endpoint["authToken"])
        endpoint_cas = Cas(endpoint_session)
        self.assertTrue(endpoint_cas.verify_session_namespace(), "默认 endpoint AuthSecret 应可访问 panel namespace")

    def test_end_to_end_namespace_role_account_endpoint_chain(self):
        tenant = self.create_namespace(scope=UNSET)
        self.assertEqual(tenant["scope"], tenant["name"])

        tenant_apps = self.bind_namespace_apps(tenant["name"])
        role = self.create_role(tenant_apps["role"])
        account = self.create_account(tenant_apps["account"], role)
        endpoint = self.create_endpoint(
            tenant_apps["endpoint"],
            account,
            role,
            f"{tenant['name']}:inventory(r);{tenant['name']}:orders(w)",
        )

        self.assertEqual(endpoint["account"]["id"], account["id"])
        self.assertEqual(endpoint["role"]["id"], role["id"])
        self.assertEqual(endpoint["scope"], f"{tenant['name']}:inventory(r);{tenant['name']}:orders(w)")
        self.assertTrue(endpoint.get("authToken"))

    def test_account_login_refresh_and_logout_flow(self):
        tenant = self.create_namespace(scope=UNSET)
        tenant_apps = self.bind_namespace_apps(tenant["name"])
        role = self.create_role(tenant_apps["role"])
        account = self.create_account(tenant_apps["account"], role, password="Test@123")

        account_session = tenant_apps["cas"]
        self.assertTrue(account_session.login(account["account"], "Test@123"), "account 登录失败")
        self.assertIsNotNone(account_session.get_current_entity())

        old_token = account_session.get_session_token()
        new_token = account_session.refresh(old_token)
        self.assertIsNotNone(new_token, "刷新会话失败")
        self.assertTrue(account_session.logout(new_token), "登出失败")


if __name__ == "__main__":
    unittest.main()
