import os
import re
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
for path in (PROJECT_ROOT, os.path.join(PROJECT_ROOT, "cas")):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import expect, sync_playwright
except ImportError:  # pragma: no cover - optional browser dependency.
    PlaywrightTimeoutError = None
    expect = None
    sync_playwright = None

from cas import Cas
from registration_test import RegistrationClient
from session import MagicSession
from test_support import ALL_PERMISSION, CasE2EBase, STATUS_ENABLE, unique_name


def _bool_env(name, default=True):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


class PortalRegistrationBrowserTestCase(CasE2EBase):
    web_base_url = os.getenv("MAGICTEST_WEB_BASE_URL", "https://panel.local.vpc")
    browser_headless = _bool_env("MAGICTEST_UI_HEADLESS", True)

    @classmethod
    def setUpClass(cls):
        if sync_playwright is None:
            raise unittest.SkipTest(
                "Playwright is not installed. Install it in ~/codespace/venv to run UI tests."
            )

    @staticmethod
    def _policy_payload(policy, fallback_profile_key, enabled):
        return {
            "enabled": bool(policy.get("enabled", enabled)) if policy else enabled,
            "defaultProfileKey": (policy or {}).get("defaultProfileKey") or fallback_profile_key,
            "requireApproval": bool((policy or {}).get("requireApproval", True)),
            "captchaEnabled": bool((policy or {}).get("captchaEnabled", False)),
            "allowedEmailDomains": (policy or {}).get("allowedEmailDomains") or [],
            "status": (policy or {}).get("status", STATUS_ENABLE),
        }

    def _query_policy(self, namespace):
        response = self.panel_session.get(
            f"/api/v1/cas/namespaces/{namespace}/registration/policys/"
        )
        if response is None or response.get("error") is not None:
            return None
        return response.get("value")

    def _create_registration_role(self, role_module, role_key):
        role = self.tenant_apps["role"].create_role(
            {
                "name": unique_name("ui_registration_role"),
                "module": role_module,
                "key": role_key,
                "description": "portal registration ui role",
                "group": "registration-ui",
                "privilege": [
                    {
                        "module": "*",
                        "uriPath": "*",
                        "value": ALL_PERMISSION,
                        "description": "portal registration ui all permission",
                    }
                ],
                "status": STATUS_ENABLE,
            }
        )
        self.assertIsNotNone(role, "创建 UI 注册测试角色失败")
        self.cleanup_delete(self.tenant_apps["role"], role["id"], "delete_role")
        return role

    def _prepare_registration_policy(self, registration):
        old_policy = self._query_policy(self.panel_namespace)
        role_module = "registration-ui"
        role_key = unique_name("portal_user")
        role = self._create_registration_role(role_module, role_key)

        profile_key = unique_name("ui_profile")
        profile = registration.create_profile(
            self.panel_namespace,
            {
                "key": profile_key,
                "name": "portal registration ui profile",
                "description": "portal registration ui profile",
                "roleRefs": [{"module": role_module, "roleKey": role_key}],
                "status": STATUS_ENABLE,
            },
        )
        self.assertEqual(profile["key"], profile_key)
        self._cleanup_actions.append(
            lambda: registration.delete_profile(self.panel_namespace, profile["id"])
        )

        registration.update_policy(
            self.panel_namespace,
            {
                "enabled": True,
                "defaultProfileKey": profile_key,
                "requireApproval": True,
                "captchaEnabled": False,
                "allowedEmailDomains": [],
                "status": STATUS_ENABLE,
            },
        )
        restore_payload = self._policy_payload(old_policy, profile_key, False)
        self._cleanup_actions.append(
            lambda: registration.update_policy(self.panel_namespace, restore_payload)
        )
        return profile_key

    def _approve_registered_account(self, registration, account_name):
        registrations = registration.filter_registration(
            self.panel_namespace, {"account": account_name}
        )
        self.assertEqual(len(registrations), 1, f"注册申请数量不正确: {registrations}")
        approved = registration.approve_registration(
            self.panel_namespace, registrations[0]["id"], "approved by ui e2e"
        )
        self.assertEqual(approved["status"], "approved")
        return approved

    def _cleanup_registered_account(self, account_name):
        accounts = self.tenant_apps["account"].filter_account({"account": account_name})
        if accounts:
            self.cleanup_delete(
                self.tenant_apps["account"], accounts[0]["id"], "delete_account"
            )

    def test_portal_registration_approval_login_browser_flow(self):
        self.tenant_apps = self.bind_namespace_apps(self.panel_namespace)
        registration = RegistrationClient(self.tenant_apps["session"])
        self._prepare_registration_policy(registration)

        account_name = unique_name("ui_reg")
        password = "UiReg@123456"

        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=self.browser_headless)
            except Exception as exc:
                raise unittest.SkipTest(f"Chromium is unavailable for UI test: {exc}") from exc

            context = browser.new_context(ignore_https_errors=True, locale="zh-CN")
            page = context.new_page()
            try:
                page.goto(f"{self.web_base_url}/register/", wait_until="networkidle")
                expect(page.get_by_text("注册账号")).to_be_visible(timeout=15_000)
                expect(page.get_by_text("提交后需等待管理员审核")).to_be_visible(
                    timeout=10_000
                )

                page.get_by_placeholder("请输入账号").fill(account_name)
                page.get_by_placeholder("请输入显示名称").fill("UI 注册用户")
                page.get_by_placeholder("请输入邮箱").fill(f"{account_name}@example.com")
                page.get_by_placeholder("请输入密码").fill(password)
                page.get_by_placeholder("请再次输入密码").fill(password)
                page.get_by_role("button", name="提交注册").click()
                expect(page.get_by_text("注册申请已提交")).to_be_visible(timeout=15_000)

                self._approve_registered_account(registration, account_name)

                page.get_by_role("button", name="返回登录").click()
                page.wait_for_url(re.compile(r".*/login/.*"), timeout=15_000)
                page.get_by_placeholder(re.compile("请输入或选择用户名|请输入用户名")).fill(
                    account_name
                )
                page.get_by_placeholder("请输入密码").fill(password)
                page.get_by_role("button", name="登录").click()
                page.wait_for_url(re.compile(r".*/portal/.*|.*/$"), timeout=20_000)
                page.wait_for_load_state("networkidle")

                body_text = page.locator("body").inner_text(timeout=10_000)
                self.assertIn("我的应用", body_text)
                self.assertNotIn("403", body_text)
                self.assertNotIn("Forbidden", body_text)
            except PlaywrightTimeoutError as exc:
                self.fail(f"Portal 注册 UI 链路超时: {exc}")
            finally:
                context.close()
                browser.close()

        portal_login = Cas(MagicSession(self.server_url, self.panel_namespace))
        self.assertTrue(portal_login.login(account_name, password), "UI 注册账号登录失败")
        self._cleanup_registered_account(account_name)


if __name__ == "__main__":
    unittest.main()
