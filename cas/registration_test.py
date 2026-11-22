import unittest

from cas import Cas
from session import MagicSession
from test_support import (
    CasE2EBase,
    STATUS_ENABLE,
    UNSET,
    unique_name,
)


PORTAL_REGISTRATION_PROFILES = [
    "portal-usage-core",
    "portal-usage-apps",
    "portal-usage-services",
]


class RegistrationClient:
    def __init__(self, work_session: MagicSession):
        self.session = work_session

    @staticmethod
    def _value(response, message):
        if response is None or response.get("error") is not None:
            raise AssertionError(f"{message}: {response}")
        return response.get("value")

    @staticmethod
    def _values(response, message):
        if response is None or response.get("error") is not None:
            raise AssertionError(f"{message}: {response}")
        return response.get("values") or []

    def list_role_templates(self, namespace):
        return self._values(
            self.session.get(
                f"/api/v1/cas/namespaces/{namespace}/role-templates/",
                {"_pageSize": 100},
            ),
            "查询权限模板列表失败",
        )

    def create_profile(self, namespace, payload):
        return self._value(
            self.session.post(
                f"/api/v1/cas/namespaces/{namespace}/registration/profiles/",
                payload,
            ),
            "创建注册模板失败",
        )

    def delete_profile(self, namespace, profile_id):
        return self._value(
            self.session.delete(
                f"/api/v1/cas/namespaces/{namespace}/registration/profiles/{profile_id}"
            ),
            "删除注册模板失败",
        )

    def update_policy(self, namespace, payload):
        return self._value(
            self.session.put(
                f"/api/v1/cas/namespaces/{namespace}/registration/policies/",
                payload,
            ),
            "更新注册策略失败",
        )

    def query_public_policy(self):
        return self._value(
            self.session.get("/api/v1/cas/registration/policy/public/"),
            "查询公开注册策略失败",
        )

    def submit_registration(self, payload):
        return self._value(
            self.session.post("/api/v1/cas/registration/account/submit/", payload),
            "提交注册申请失败",
        )

    def approve_registration(self, namespace, registration_id, message="approved by e2e"):
        return self._value(
            self.session.put(
                f"/api/v1/cas/namespaces/{namespace}/registration/account/approve/{registration_id}",
                {"approvalMessage": message},
            ),
            "审核通过注册申请失败",
        )

    def filter_registration(self, namespace, payload):
        return self._values(
            self.session.get(
                f"/api/v1/cas/namespaces/{namespace}/registration/accounts/",
                payload,
            ),
            "查询注册申请失败",
        )


class PortalAccessClient:
    def __init__(self, work_session: MagicSession):
        self.session = work_session

    @staticmethod
    def _value(response, message):
        if response is None or response.get("error") is not None:
            raise AssertionError(f"{message}: {response}")
        return response.get("value")

    @staticmethod
    def _values(response, message):
        if response is None or response.get("error") is not None:
            raise AssertionError(f"{message}: {response}")
        return response.get("values") or []

    def query_system_context(self, surface="portal"):
        return self._value(
            self.session.get("/api/v1/system/context/", {"surface": surface}),
            "查询 system context 失败",
        )

    def query_profile(self):
        return self._value(
            self.session.get("/api/v1/portal/profile"),
            "查询 portal profile 失败",
        )

    def filter_applications(self):
        return self._values(
            self.session.get("/api/v1/portal/applications/"),
            "查询 portal applications 失败",
        )

    def filter_services(self):
        return self._values(
            self.session.get("/api/v1/portal/services/"),
            "查询 portal services 失败",
        )


class RegistrationScenarioTestCase(CasE2EBase):
    def test_public_registration_requires_approval_then_login_after_approve(self):
        self.tenant = self.create_namespace(scope=UNSET)
        self.tenant_apps = self.bind_namespace_apps(self.tenant["name"])
        registration = RegistrationClient(self.tenant_apps["session"])

        templates = {
            item.get("key"): item
            for item in registration.list_role_templates(self.tenant["name"])
            if item.get("key")
        }
        for required_key in PORTAL_REGISTRATION_PROFILES:
            item = templates.get(required_key)
            self.assertIsNotNone(item, f"缺少受控注册子模板: {required_key}")
            self.assertEqual(item.get("scene"), "usage")
            self.assertEqual(item.get("subjectType"), "account")
            self.assertEqual(item.get("status"), STATUS_ENABLE)

        profile_key = unique_name("profile")
        profile = registration.create_profile(
            self.tenant["name"],
            {
                "key": profile_key,
                "name": "registration e2e profile",
                "description": "registration e2e profile",
                "accessProfileKeys": list(PORTAL_REGISTRATION_PROFILES),
                "status": STATUS_ENABLE,
            },
        )
        self.assertEqual(profile["key"], profile_key)
        self._cleanup_actions.append(
            lambda: registration.delete_profile(self.tenant["name"], profile["id"])
        )

        policy = registration.update_policy(
            self.tenant["name"],
            {
                "enabled": True,
                "defaultProfileKey": profile_key,
                "requireApproval": True,
                "captchaEnabled": False,
                "allowedEmailDomains": [],
                "status": STATUS_ENABLE,
            },
        )
        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["requireApproval"])
        self.assertEqual(policy["defaultProfileKey"], profile_key)

        public_session = MagicSession(self.server_url, self.tenant["name"])
        public_registration = RegistrationClient(public_session)
        public_policy = public_registration.query_public_policy()
        self.assertTrue(public_policy["enabled"])
        self.assertTrue(public_policy["requireApproval"])
        self.assertEqual(public_policy["defaultProfileKey"], profile_key)

        account_name = unique_name("reg_account")
        password = "Reg@123456"
        submitted = public_registration.submit_registration(
            {
                "account": account_name,
                "password": password,
                "email": f"{account_name}@example.com",
                "displayName": "registration e2e account",
            }
        )
        self.assertEqual(submitted["status"], "pending")
        self.assertEqual(submitted["account"], account_name)

        pending_login = Cas(MagicSession(self.server_url, self.tenant["name"]))
        self.assertFalse(
            pending_login.login(account_name, password),
            "待审核账号不应在审核前登录成功",
        )

        registrations = registration.filter_registration(
            self.tenant["name"], {"account": account_name}
        )
        self.assertEqual(len(registrations), 1)
        self.assertEqual(registrations[0]["status"], "pending")

        approved = registration.approve_registration(
            self.tenant["name"], registrations[0]["id"]
        )
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["account"], account_name)

        approved_login = Cas(MagicSession(self.server_url, self.tenant["name"]))
        self.assertTrue(
            approved_login.login(account_name, password),
            "审核通过后账号应可登录",
        )

        portal_session = MagicSession(self.server_url, self.tenant["name"])
        portal_session.bind_token(approved_login.get_session_token())
        portal_client = PortalAccessClient(portal_session)

        system_context = portal_client.query_system_context()
        self.assertEqual(system_context.get("namespace"), self.tenant["name"])
        self.assertEqual(system_context.get("surface"), "portal")
        self.assertIsInstance(
            system_context.get("entryVisibility"),
            dict,
            "system context.entryVisibility 不是对象",
        )
        self.assertIsInstance(
            system_context.get("areaVisibility"),
            dict,
            "system context.areaVisibility 不是对象",
        )

        profile = portal_client.query_profile()
        self.assertIn("summary", profile, "portal profile 缺少 summary")
        self.assertIsInstance(profile.get("summary"), list, "portal profile.summary 不是列表")

        portal_applications = portal_client.filter_applications()
        self.assertIsInstance(portal_applications, list, "portal applications 结果不是列表")

        portal_services = portal_client.filter_services()
        self.assertIsInstance(portal_services, list, "portal services 结果不是列表")

        accounts = self.tenant_apps["account"].filter_account({"account": account_name})
        self.assertIsNotNone(accounts, "查询注册账号失败")
        self.assertEqual(len(accounts), 1)
        effective_keys = {
            r.get("key")
            for r in (accounts[0].get("effectiveRoles") or [])
            if isinstance(r, dict)
        }
        self.assertTrue(
            {
                "portal-app-catalog-viewer",
                "portal-service-catalog-viewer",
                "portal-service-invoker",
            }.issubset(effective_keys),
            f"注册账号缺少受控门户初始角色: {accounts[0]}",
        )
        self.assertEqual(accounts[0].get("templateRefs") or [], [])
        self.cleanup_delete(
            self.tenant_apps["account"], accounts[0]["id"], "delete_account"
        )


if __name__ == "__main__":
    unittest.main()
