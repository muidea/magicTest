import unittest

from session import MagicSession

from test_support import (
    CasE2EBase,
    STATUS_DISABLE,
    STATUS_ENABLE,
    UNSET,
    auth_secret_param,
    unique_name,
)


class CasAPITestCase(CasE2EBase):
    def setUp(self):
        super().setUp()
        self.tenant = self.create_namespace(scope=UNSET)
        self.tenant_apps = self.bind_namespace_apps(self.tenant["name"])
        self.role = self.create_role(self.tenant_apps["role"])
        self.account = self.create_account(self.tenant_apps["account"], self.role, password="Test@123")
        self.endpoint = self.create_endpoint(
            self.tenant_apps["endpoint"],
            self.account,
            self.role,
            f"{self.tenant['name']}:orders(r)",
        )

    def _find_entity(self, eid, etype):
        entity_list = self.tenant_apps["cas"].filter_entity()
        self.assertIsNotNone(entity_list, "查询实体列表失败")
        return next(
            (item for item in entity_list if item.get("eID") == eid and item.get("eType") == etype),
            None,
        )

    def _issue_runtime_endpoint_secret(self, name_prefix, scope):
        source_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(source_entity, "未找到 endpoint 对应实体")

        secret = self.tenant_apps["cas"].allocate_auth_secret(auth_secret_param(
            endpoint_name=unique_name(name_prefix),
            entity_id=source_entity["id"],
            scope=scope,
        ))
        self.assertIsNotNone(secret, "签发 endpoint AuthSecret 失败")

        created_endpoints = self.tenant_apps["endpoint"].filter_endpoint({"name": secret["endpoint"]})
        self.assertIsNotNone(created_endpoints)
        self.assertEqual(len(created_endpoints), 1)
        runtime_endpoint = created_endpoints[0]
        self.cleanup_delete(self.tenant_apps["endpoint"], runtime_endpoint["id"], "delete_endpoint")

        runtime_entity = self._find_entity(runtime_endpoint["id"], "endpoint")
        self.assertIsNotNone(runtime_entity, "未找到签发后 endpoint 实体")
        return secret, runtime_endpoint, runtime_entity

    def _jwt_verify_param(self):
        account_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(account_login.login(self.account["account"], "Test@123"), "account 登录失败")
        session_id = account_login.get_session_id()
        self.assertIsNotNone(session_id, "无法从 session token 提取 sessionID")
        return account_login, {
            "sessionID": session_id,
            "authScope": self.tenant["scope"],
            "remoteAddress": "127.0.0.1",
            "userAgent": "magicTest-cas-e2e",
            "authType": "jwt",
            "entityID": account_login.get_current_entity()["id"],
        }

    def test_verify_account_and_update_password(self):
        verify_session = MagicSession(self.server_url, self.tenant["name"])
        verify_cas = self.tenant_apps["cas"].__class__(verify_session)

        entity = verify_cas.verify_account(self.account["account"], "Test@123")
        self.assertIsNotNone(entity, "verifyAccount 应返回 account 实体")
        self.assertEqual(entity["eType"], "account")
        self.assertIsNone(
            verify_cas.verify_account(self.account["account"], "wrong-password"),
            "错误密码不应通过 verifyAccount",
        )

        account_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(account_login.login(self.account["account"], "Test@123"), "account 登录失败")

        self.assertIsNone(
            account_login.update_account_password({
                "account": self.account["account"],
                "curPassword": "wrong-password",
                "newPassword": "ShouldFail@123",
            }),
            "错误旧密码不应允许更新密码",
        )

        updated = account_login.update_account_password({
            "account": self.account["account"],
            "curPassword": "Test@123",
            "newPassword": "NewPass@123",
        })
        self.assertIsNotNone(updated, "更新密码失败")
        self.assertEqual(updated["id"], self.account["id"])

        old_login = self.bind_namespace_apps(self.tenant["name"])["cas"].login(self.account["account"], "Test@123")
        self.assertFalse(old_login, "旧密码不应继续可用")

        new_login = self.bind_namespace_apps(self.tenant["name"])["cas"].login(self.account["account"], "NewPass@123")
        self.assertTrue(new_login, "新密码应可用于登录")

    def test_update_account_password_requires_bound_account_session(self):
        panel_tenant_session = MagicSession(self.server_url, self.tenant["name"])
        panel_tenant_session.bind_token(self.panel_cas.get_session_token())
        panel_tenant_cas = self.panel_cas.__class__(panel_tenant_session)

        self.assertIsNone(
            panel_tenant_cas.update_account_password({
                "account": self.account["account"],
                "curPassword": "Test@123",
                "newPassword": "ShouldNotPass@123",
            }),
            "非当前 account 本人 session 不应修改该 account 密码",
        )

        tenant_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(tenant_login.login(self.account["account"], "Test@123"), "account 登录失败")
        self.assertIsNotNone(
            tenant_login.update_account_password({
                "account": self.account["account"],
                "curPassword": "Test@123",
                "newPassword": "NewPass@123",
            }),
            "当前 account 本人 session 应允许修改自己的密码",
        )

    def test_update_account_password_rejects_endpoint_session(self):
        secret, _, _ = self._issue_runtime_endpoint_secret(
            "pwdendpoint",
            f"{self.tenant['name']}:profile(w)",
        )

        endpoint_session = MagicSession(self.server_url, self.tenant["name"])
        endpoint_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
        endpoint_cas = self.tenant_apps["cas"].__class__(endpoint_session)

        self.assertIsNone(
            endpoint_cas.update_account_password({
                "account": self.account["account"],
                "curPassword": "Test@123",
                "newPassword": "ShouldNotPass@123",
            }),
            "endpoint session 不应修改绑定 account 的密码",
        )

    def test_low_privilege_role_cannot_access_privileged_cas_routes(self):
        restricted_role = self.create_role(self.tenant_apps["role"], privilege=[])
        restricted_account = self.create_account(
            self.tenant_apps["account"],
            restricted_role,
            password="Restricted@123",
        )

        restricted_login = self.bind_namespace_apps(self.tenant["name"])["cas"]
        self.assertTrue(restricted_login.login(restricted_account["account"], "Restricted@123"), "低权限 account 登录失败")

        current_entity = restricted_login.get_current_entity()
        self.assertIsNotNone(current_entity, "低权限 account 登录后应拿到当前实体")

        self.assertIsNone(
            restricted_login.filter_entity(),
            "无 read 权限的 role 不应访问 filterEntity",
        )
        self.assertIsNone(
            restricted_login.query_entity(current_entity["id"]),
            "无 read 权限的 role 不应访问 queryEntity",
        )
        self.assertIsNone(
            restricted_login.query_entity_role(current_entity["id"]),
            "无 read 权限的 role 不应访问 queryEntityRole",
        )
        self.assertIsNone(
            restricted_login.update_account_password({
                "account": restricted_account["account"],
                "curPassword": "Restricted@123",
                "newPassword": "Denied@123",
            }),
            "无 write 权限的 role 不应访问 updateAccountPassword",
        )

    def test_query_entity_and_query_entity_role_for_account(self):
        account_login, verify_param = self._jwt_verify_param()

        queried_entity = account_login.query_entity(verify_param["entityID"])
        self.assertIsNotNone(queried_entity, "queryEntity 失败")
        self.assertEqual(queried_entity["eType"], "account")

        queried_pair = account_login.query_entity_role(verify_param["entityID"])
        self.assertIsNotNone(queried_pair, "queryEntityRole 失败")
        self.assertEqual(queried_pair["entity"]["id"], verify_param["entityID"])
        self.assertEqual(queried_pair["role"]["id"], self.role["id"])

    def test_query_entity_role_for_endpoint_entity(self):
        endpoint_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(endpoint_entity, "未找到 endpoint 实体")

        queried_entity = self.tenant_apps["cas"].query_entity(endpoint_entity["id"])
        self.assertIsNotNone(queried_entity, "queryEntity(endpoint) 失败")
        self.assertEqual(queried_entity["eType"], "endpoint")

        queried_pair = self.tenant_apps["cas"].query_entity_role(endpoint_entity["id"])
        self.assertIsNotNone(queried_pair, "queryEntityRole(endpoint) 失败")
        self.assertEqual(queried_pair["entity"]["id"], endpoint_entity["id"])
        self.assertEqual(queried_pair["role"]["id"], self.role["id"])

    def test_query_entity_and_role_reject_cross_namespace_entity(self):
        endpoint_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(endpoint_entity, "未找到 endpoint 实体")

        other_namespace = self.create_namespace(scope=UNSET)
        cross_session = MagicSession(self.server_url, other_namespace["name"])
        cross_session.bind_token(self.panel_cas.get_session_token())
        cross_cas = self.panel_cas.__class__(cross_session)

        self.assertIsNone(
            cross_cas.query_entity(endpoint_entity["id"]),
            "跨 namespace 不应查询到其他 namespace 的实体",
        )
        self.assertIsNone(
            cross_cas.query_entity_role(endpoint_entity["id"]),
            "跨 namespace 不应查询到其他 namespace 的实体角色绑定",
        )

    def test_allocate_auth_secret_rejects_cross_namespace_entity(self):
        endpoint_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(endpoint_entity, "未找到 endpoint 实体")

        other_namespace = self.create_namespace(scope=UNSET)
        cross_session = MagicSession(self.server_url, other_namespace["name"])
        cross_session.bind_token(self.panel_cas.get_session_token())
        cross_cas = self.panel_cas.__class__(cross_session)

        self.assertIsNone(
            cross_cas.allocate_auth_secret(auth_secret_param(
                endpoint_name=unique_name("crosssecret"),
                entity_id=endpoint_entity["id"],
                scope=f"{other_namespace['name']}:audit(r)",
            )),
            "跨 namespace 不应对其他 namespace 实体签发 AuthSecret",
        )

    def test_verify_session_namespace_entity_and_role_for_jwt_account(self):
        account_login, verify_param = self._jwt_verify_param()

        self.assertTrue(account_login.verify_session_namespace(), "当前 namespace 的 session 校验应通过")

        verified_entity = account_login.verify_session_entity(verify_param)
        self.assertIsNotNone(verified_entity, "verifySessionEntity 应返回当前 account entity")
        self.assertEqual(verified_entity["id"], verify_param["entityID"])

        verified_pair = account_login.verify_session_entity_role(verify_param)
        self.assertIsNotNone(verified_pair, "verifySessionEntityRole 应返回 entity-role 绑定")
        self.assertEqual(verified_pair["entity"]["id"], verify_param["entityID"])
        self.assertEqual(verified_pair["role"]["id"], self.role["id"])

        other_namespace = self.create_namespace(scope=UNSET)
        cross_session = MagicSession(self.server_url, other_namespace["name"])
        cross_session.bind_token(account_login.get_session_token())
        cross_cas = account_login.__class__(cross_session)
        self.assertFalse(cross_cas.verify_session_namespace(), "scope 外 namespace 的 session 校验应失败")

    def test_verify_session_entity_rejects_mismatched_entity_id(self):
        account_login, verify_param = self._jwt_verify_param()
        endpoint_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(endpoint_entity, "未找到 endpoint 实体")

        verify_param["entityID"] = endpoint_entity["id"]
        self.assertIsNone(
            account_login.verify_session_entity(verify_param),
            "JWT session 不应通过错误 entityID 的实体校验",
        )
        self.assertIsNone(
            account_login.verify_session_entity_role(verify_param),
            "JWT session 不应通过错误 entityID 的实体角色校验",
        )

    def test_panel_jwt_session_can_verify_scoped_namespace(self):
        tenant_session = MagicSession(self.server_url, self.tenant["name"])
        tenant_session.bind_token(self.panel_cas.get_session_token())
        tenant_cas = self.panel_cas.__class__(tenant_session)
        self.assertTrue(tenant_cas.verify_session_namespace(), "panel 全局 namespace token 应可访问租户 namespace")

    def test_refresh_updates_jwt_scope_after_namespace_scope_change(self):
        target_namespace = self.create_namespace(scope=UNSET)
        account_login, _ = self._jwt_verify_param()
        self.assertEqual(account_login.get_session_scope(), self.tenant["scope"])

        target_session = MagicSession(self.server_url, target_namespace["name"])
        target_session.bind_token(account_login.get_session_token())
        target_cas = account_login.__class__(target_session)
        self.assertFalse(target_cas.verify_session_namespace(), "scope 外 namespace 的 session 校验应失败")

        tenant_payload = dict(self.tenant)
        tenant_payload["scope"] = f"{self.tenant['name']};{target_namespace['name']}:*"
        updated_tenant = self.namespace_app.update_namespace(tenant_payload)
        self.assertIsNotNone(updated_tenant, "更新 tenant namespace scope 失败")

        self.assertTrue(
            target_cas.verify_session_namespace(),
            "运行态鉴权应回源使用最新 namespace scope，而不是继续信任旧 token claim",
        )
        self.assertEqual(
            account_login.get_session_scope(),
            self.tenant["scope"],
            "未 refresh 前当前 JWT claim 仍应保留旧 scope",
        )

        new_token = account_login.refresh(account_login.get_session_token())
        self.assertIsNotNone(new_token, "scope 变更后 refresh 应成功")
        self.assertEqual(account_login.get_session_scope(), updated_tenant["scope"])

        refreshed_target_session = MagicSession(self.server_url, target_namespace["name"])
        refreshed_target_session.bind_token(new_token)
        refreshed_target_cas = account_login.__class__(refreshed_target_session)
        self.assertTrue(refreshed_target_cas.verify_session_namespace(), "refresh 后新 token 应具备最新 namespace scope")

    def test_verify_session_entity_and_role_for_endpoint_auth(self):
        secret, runtime_endpoint, runtime_entity = self._issue_runtime_endpoint_secret(
            "verifyep",
            f"{self.tenant['name']}:verify(r)",
        )

        endpoint_session = MagicSession(self.server_url, self.tenant["name"])
        endpoint_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
        endpoint_cas = self.tenant_apps["cas"].__class__(endpoint_session)

        verify_param = {
            "sessionID": unique_name("endpointsid"),
            "authScope": runtime_endpoint["scope"],
            "remoteAddress": "127.0.0.1",
            "userAgent": "magicTest-cas-endpoint",
            "authType": "endpoint",
            "entityID": runtime_entity["id"],
        }

        self.assertTrue(endpoint_cas.verify_session_namespace(), "endpoint 凭证的 namespace 校验应通过")
        verified_entity = endpoint_cas.verify_session_entity(verify_param)
        self.assertIsNotNone(verified_entity, "endpoint 会话实体校验应通过")
        self.assertEqual(verified_entity["id"], runtime_entity["id"])

        verified_pair = endpoint_cas.verify_session_entity_role(verify_param)
        self.assertIsNotNone(verified_pair, "endpoint 会话角色校验应通过")
        self.assertEqual(verified_pair["entity"]["id"], runtime_entity["id"])
        self.assertEqual(verified_pair["role"]["id"], self.role["id"])

    def test_allocate_auth_secret_rejects_role_override_for_endpoint_entity(self):
        source_entity = self._find_entity(self.endpoint["id"], "endpoint")
        self.assertIsNotNone(source_entity, "未找到 endpoint 对应实体")

        override_role = self.create_role(self.tenant_apps["role"])
        secret = self.tenant_apps["cas"].allocate_auth_secret(auth_secret_param(
            endpoint_name=unique_name("overrideep"),
            entity_id=source_entity["id"],
            scope=f"{self.tenant['name']}:override(r)",
            role=override_role,
        ))
        self.assertIsNone(secret, "以 endpoint 实体签发 AuthSecret 时不应允许显式 role 覆盖")

    def test_endpoint_auth_secret_is_rejected_after_endpoint_or_binding_disabled(self):
        secret, runtime_endpoint, _ = self._issue_runtime_endpoint_secret(
            "runtime",
            f"{self.tenant['name']}:reports(r)",
        )

        def endpoint_can_access():
            endpoint_session = MagicSession(self.server_url, self.tenant["name"])
            endpoint_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
            endpoint_cas = self.tenant_apps["cas"].__class__(endpoint_session)
            return endpoint_cas.verify_session_namespace()

        self.assertTrue(endpoint_can_access(), "有效 endpoint AuthSecret 应可通过 session namespace 校验")

        endpoint_payload = dict(runtime_endpoint)
        endpoint_payload["status"] = STATUS_DISABLE
        disabled_endpoint = self.tenant_apps["endpoint"].update_endpoint(endpoint_payload)
        self.assertIsNotNone(disabled_endpoint)
        self.assertFalse(endpoint_can_access(), "禁用 endpoint 后 AuthSecret 应失效")

        endpoint_payload["status"] = STATUS_ENABLE
        restored_endpoint = self.tenant_apps["endpoint"].update_endpoint(endpoint_payload)
        self.assertIsNotNone(restored_endpoint)
        self.assertTrue(endpoint_can_access(), "恢复 endpoint 后 AuthSecret 应重新有效")

        account_payload = dict(self.account)
        account_payload["status"] = STATUS_DISABLE
        disabled_account = self.tenant_apps["account"].update_account(account_payload)
        self.assertIsNotNone(disabled_account)
        self.assertFalse(endpoint_can_access(), "禁用绑定 account 后 AuthSecret 应失效")

    def test_refresh_is_rejected_after_bound_role_disabled(self):
        account_login, _ = self._jwt_verify_param()

        role_payload = dict(self.role)
        role_payload["status"] = STATUS_DISABLE
        disabled_role = self.tenant_apps["role"].update_role(role_payload)
        self.assertIsNotNone(disabled_role)

        self.assertIsNone(
            account_login.refresh(account_login.get_session_token()),
            "绑定 role 失效后 refresh 不应继续成功",
        )

    def test_endpoint_auth_secret_is_rejected_after_bound_role_disabled(self):
        secret, _, _ = self._issue_runtime_endpoint_secret(
            "rolebound",
            f"{self.tenant['name']}:audit(r)",
        )

        endpoint_session = MagicSession(self.server_url, self.tenant["name"])
        endpoint_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
        endpoint_cas = self.tenant_apps["cas"].__class__(endpoint_session)
        self.assertTrue(endpoint_cas.verify_session_namespace())

        role_payload = dict(self.role)
        role_payload["status"] = STATUS_DISABLE
        disabled_role = self.tenant_apps["role"].update_role(role_payload)
        self.assertIsNotNone(disabled_role)

        self.assertFalse(endpoint_cas.verify_session_namespace(), "禁用绑定 role 后 AuthSecret 应失效")

    def test_endpoint_auth_secret_is_rejected_after_runtime_endpoint_deleted(self):
        secret, runtime_endpoint, _ = self._issue_runtime_endpoint_secret(
            "deletedep",
            f"{self.tenant['name']}:archive(r)",
        )

        endpoint_session = MagicSession(self.server_url, self.tenant["name"])
        endpoint_session.bind_auth_secret(secret["endpoint"], secret["authToken"])
        endpoint_cas = self.tenant_apps["cas"].__class__(endpoint_session)
        self.assertTrue(endpoint_cas.verify_session_namespace())

        delete_result = self.tenant_apps["endpoint"].delete_endpoint(runtime_endpoint["id"])
        self.assertIsNotNone(delete_result)
        self.assertFalse(endpoint_cas.verify_session_namespace(), "删除 runtime endpoint 后 AuthSecret 应失效")


if __name__ == "__main__":
    unittest.main()
