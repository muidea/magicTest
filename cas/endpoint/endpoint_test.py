import unittest

from session import MagicSession

from test_support import (
    CasE2EBase,
    STATUS_DISABLE,
    STATUS_ENABLE,
    UNSET,
    auth_secret_param,
    endpoint_param,
    unique_name,
)


class EndpointTestCase(CasE2EBase):
    def setUp(self):
        super().setUp()
        self.tenant = self.create_namespace(scope=UNSET)
        self.tenant_apps = self.bind_namespace_apps(self.tenant["name"])
        self.role = self.create_role(self.tenant_apps["role"])
        self.account = self.create_account(self.tenant_apps["account"], self.role)

    def _find_entity(self, eid, etype):
        entity_list = self.tenant_apps["cas"].filter_entity()
        self.assertIsNotNone(entity_list, "查询实体列表失败")
        for entity in entity_list:
            if entity.get("eID") == eid and entity.get("eType") == etype:
                return entity
        self.fail(f"entity not found, eid={eid}, etype={etype}")

    def test_endpoint_is_explicit_auth_object(self):
        scope = f"{self.tenant['name']}:orders(r);{self.tenant['name']}:inventory(w)"
        endpoint = self.create_endpoint(self.tenant_apps["endpoint"], self.account, self.role, scope)

        self.assertEqual(endpoint["account"]["id"], self.account["id"])
        self.assertEqual(endpoint["role"]["id"], self.role["id"])
        self.assertEqual(endpoint["scope"], scope)
        self.assertEqual(endpoint["status"], STATUS_ENABLE)
        self.assertTrue(endpoint.get("authToken"), "endpoint 应生成 authToken")

    def test_endpoint_binding_requires_enabled_account_and_role(self):
        missing_scope_endpoint = self.tenant_apps["endpoint"].create_endpoint(endpoint_param(
            unique_name("endpoint"),
            self.account,
            self.role,
            "",
        ))
        self.assertIsNone(missing_scope_endpoint, "未显式提供 scope 的 endpoint 不应创建成功")

        disabled_role_payload = dict(self.role)
        disabled_role_payload["status"] = STATUS_DISABLE
        disabled_role = self.tenant_apps["role"].update_role(disabled_role_payload)
        self.assertIsNotNone(disabled_role)

        endpoint = self.tenant_apps["endpoint"].create_endpoint(endpoint_param(
            unique_name("endpoint"),
            self.account,
            disabled_role,
            f"{self.tenant['name']}:*",
        ))
        self.assertIsNone(endpoint, "绑定禁用 role 的 endpoint 不应创建成功")

        disabled_account_payload = dict(self.account)
        disabled_account_payload["status"] = STATUS_DISABLE
        disabled_account = self.tenant_apps["account"].update_account(disabled_account_payload)
        self.assertIsNotNone(disabled_account)

        account_blocked_endpoint = self.tenant_apps["endpoint"].create_endpoint(endpoint_param(
            unique_name("endpoint"),
            disabled_account,
            self.role,
            f"{self.tenant['name']}:orders(r)",
        ))
        self.assertIsNone(account_blocked_endpoint, "绑定禁用 account 的 endpoint 不应创建成功")

    def test_allocate_auth_secret_from_account_entity_creates_endpoint(self):
        account_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(account_login.login(self.account["account"], "Test@123"), "account 登录失败")
        account_entity = account_login.get_current_entity()
        self.assertIsNotNone(account_entity)

        secret = self.tenant_apps["cas"].allocate_auth_secret(auth_secret_param(
            endpoint_name=unique_name("secret"),
            entity_id=account_entity["id"],
            role=self.role,
            scope=f"{self.tenant['name']}:*",
        ))
        self.assertIsNotNone(secret, "为 account entity 签发 AuthSecret 失败")
        self.assertTrue(secret["endpoint"])
        self.assertTrue(secret["authToken"])

        created_endpoints = self.tenant_apps["endpoint"].filter_endpoint({"name": secret["endpoint"]})
        self.assertIsNotNone(created_endpoints)
        self.assertEqual(len(created_endpoints), 1)
        created_endpoint = created_endpoints[0]
        self.cleanup_delete(self.tenant_apps["endpoint"], created_endpoint["id"], "delete_endpoint")

        self.assertEqual(created_endpoint["account"]["id"], self.account["id"])
        self.assertEqual(created_endpoint["role"]["id"], self.role["id"])
        self.assertEqual(created_endpoint["scope"], f"{self.tenant['name']}:*")

        secret_session = MagicSession(self.server_url, self.tenant["name"])
        secret_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
        secret_endpoint_app = self.tenant_apps["endpoint"].__class__(secret_session)
        visible_endpoints = secret_endpoint_app.filter_endpoint({"name": created_endpoint["name"]})
        self.assertIsNotNone(visible_endpoints, "AuthSecret 应能作为 endpoint 凭证访问受权接口")

    def test_allocate_auth_secret_from_endpoint_entity_reuses_endpoint_binding(self):
        source_endpoint = self.create_endpoint(
            self.tenant_apps["endpoint"],
            self.account,
            self.role,
            f"{self.tenant['name']}:orders(r)",
        )
        endpoint_entity = self._find_entity(source_endpoint["id"], "endpoint")

        secret = self.tenant_apps["cas"].allocate_auth_secret(auth_secret_param(
            endpoint_name=unique_name("derived"),
            entity_id=endpoint_entity["id"],
            role=None,
            scope=f"{self.tenant['name']}:reports(r)",
        ))
        self.assertIsNotNone(secret, "为 endpoint entity 签发 AuthSecret 失败")

        created_endpoints = self.tenant_apps["endpoint"].filter_endpoint({"name": secret["endpoint"]})
        self.assertIsNotNone(created_endpoints)
        self.assertEqual(len(created_endpoints), 1)
        derived_endpoint = created_endpoints[0]
        self.cleanup_delete(self.tenant_apps["endpoint"], derived_endpoint["id"], "delete_endpoint")

        self.assertEqual(derived_endpoint["account"]["id"], source_endpoint["account"]["id"])
        self.assertEqual(derived_endpoint["role"]["id"], source_endpoint["role"]["id"])
        self.assertEqual(derived_endpoint["scope"], f"{self.tenant['name']}:reports(r)")

    def test_allocate_auth_secret_from_account_entity_allows_role_override(self):
        override_role = self.create_role(self.tenant_apps["role"], name=unique_name("override_role"))

        account_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(account_login.login(self.account["account"], "Test@123"), "account 登录失败")
        account_entity = account_login.get_current_entity()
        self.assertIsNotNone(account_entity)

        secret = self.tenant_apps["cas"].allocate_auth_secret(auth_secret_param(
            endpoint_name=unique_name("override"),
            entity_id=account_entity["id"],
            role=override_role,
            scope=f"{self.tenant['name']}:audit(r)",
        ))
        self.assertIsNotNone(secret, "带显式 role override 的 AuthSecret 签发失败")

        created_endpoints = self.tenant_apps["endpoint"].filter_endpoint({"name": secret["endpoint"]})
        self.assertIsNotNone(created_endpoints)
        self.assertEqual(len(created_endpoints), 1)
        created_endpoint = created_endpoints[0]
        self.cleanup_delete(self.tenant_apps["endpoint"], created_endpoint["id"], "delete_endpoint")

        self.assertEqual(created_endpoint["account"]["id"], self.account["id"])
        self.assertEqual(created_endpoint["role"]["id"], override_role["id"], "显式 role override 应写入新 endpoint")
        self.assertEqual(created_endpoint["scope"], f"{self.tenant['name']}:audit(r)")

    def test_duplicate_endpoint_name_is_rejected(self):
        endpoint_name = unique_name("dup_endpoint")
        first_endpoint = self.create_endpoint(
            self.tenant_apps["endpoint"],
            self.account,
            self.role,
            f"{self.tenant['name']}:*",
            name=endpoint_name,
        )
        self.assertIsNotNone(first_endpoint)

        second_endpoint = self.tenant_apps["endpoint"].create_endpoint(endpoint_param(
            endpoint_name,
            self.account,
            self.role,
            f"{self.tenant['name']}:reports(r)",
        ))
        self.assertIsNone(second_endpoint, "同 namespace 下重复 endpoint 名称应被拒绝")


if __name__ == "__main__":
    unittest.main()
