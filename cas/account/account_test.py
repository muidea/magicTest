import unittest

from test_support import CasE2EBase, STATUS_DISABLE, STATUS_ENABLE, unique_name


class AccountTestCase(CasE2EBase):
    def setUp(self):
        super().setUp()
        self.tenant = self.create_namespace(scope=None)
        self.tenant_apps = self.bind_namespace_apps(self.tenant["name"])

    def test_account_must_bind_enabled_role(self):
        disabled_role = self.create_role(self.tenant_apps["role"], status=STATUS_DISABLE)

        account = self.tenant_apps["account"].create_account({
            "account": unique_name("account"),
            "password": "Test@123",
            "email": f"{unique_name('mail')}@example.com",
            "description": "disabled role binding should fail",
            "role": {
                "id": disabled_role["id"],
                "name": disabled_role["name"],
                "status": disabled_role["status"],
            },
        })
        self.assertIsNone(account, "account 绑定禁用 role 时应创建失败")

    def test_account_create_and_update_keep_role_binding(self):
        role = self.create_role(self.tenant_apps["role"])
        account = self.create_account(self.tenant_apps["account"], role)

        self.assertIn("role", account)
        self.assertEqual(account["role"]["id"], role["id"])
        self.assertEqual(account["status"], STATUS_ENABLE)

        update_payload = dict(account)
        update_payload["description"] = "updated account"
        updated_account = self.tenant_apps["account"].update_account(update_payload)
        self.assertIsNotNone(updated_account)
        self.assertEqual(updated_account["description"], "updated account")
        self.assertEqual(updated_account["role"]["id"], role["id"], "更新 account 时不应丢失 role 绑定")

    def test_disabled_role_blocks_account_login(self):
        role = self.create_role(self.tenant_apps["role"])
        password = "Test@123"
        account = self.create_account(self.tenant_apps["account"], role, password=password)

        role_update = dict(role)
        role_update["status"] = STATUS_DISABLE
        disabled_role = self.tenant_apps["role"].update_role(role_update)
        self.assertIsNotNone(disabled_role)
        self.assertEqual(disabled_role["status"], STATUS_DISABLE)

        account_login_session = self.bind_namespace_cas(self.tenant["name"], token=None)
        login_ok = account_login_session.login(account["account"], password)
        self.assertFalse(login_ok, "绑定禁用 role 的 account 不应能登录")

    def test_account_filter_respects_current_namespace(self):
        role = self.create_role(self.tenant_apps["role"])
        account = self.create_account(self.tenant_apps["account"], role)

        filtered_accounts = self.tenant_apps["account"].filter_account({"account": account["account"]})
        self.assertIsNotNone(filtered_accounts)
        self.assertTrue(any(item["id"] == account["id"] for item in filtered_accounts))

        panel_accounts = self.account_app.filter_account({"account": account["account"]})
        if panel_accounts:
            self.assertFalse(any(item["id"] == account["id"] for item in panel_accounts), "panel namespace 查询不应直接返回 tenant account")

    def test_duplicate_account_name_is_rejected_in_same_namespace(self):
        role = self.create_role(self.tenant_apps["role"])
        account_name = unique_name("dup")
        first_account = self.create_account(self.tenant_apps["account"], role, name=account_name)
        self.assertIsNotNone(first_account)

        second_account = self.tenant_apps["account"].create_account({
            "account": account_name,
            "password": "Test@123",
            "email": f"{unique_name('mail')}@example.com",
            "description": "duplicate account",
            "role": {
                "id": role["id"],
                "name": role["name"],
                "status": role["status"],
            },
        })
        self.assertIsNone(second_account, "同 namespace 下重复 account 名称应被拒绝")


if __name__ == "__main__":
    unittest.main()
