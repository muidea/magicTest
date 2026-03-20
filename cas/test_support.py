import os
import time
import unittest
import uuid

from session import MagicSession
from cas import Cas
from namespace.namespace import Namespace as NamespaceApp
from role.role import Role as RoleApp
from account.account import Account as AccountApp
from endpoint.endpoint import Endpoint as EndpointApp


STATUS_DISABLE = 1
STATUS_ENABLE = 2
ALL_PERMISSION = 5
UNSET = object()


def now_ms():
    return int(time.time() * 1000)


def unique_name(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def default_time_window():
    current = now_ms()
    return current - 60_000, current + 86_400_000


def all_privilege():
    return [{
        "module": "*",
        "uriPath": "*",
        "value": ALL_PERMISSION,
        "description": "e2e all permission",
    }]


def _network_like_error(err):
    if not err:
        return False
    message = err.get("message", "")
    status_code = err.get("status_code", 0)
    return status_code == 0 or "HTTP请求失败" in message or "NameResolutionError" in message


def login_or_skip(server_url, namespace, account="administrator", password="administrator"):
    work_session = MagicSession(server_url, namespace)
    cas_client = Cas(work_session)
    if cas_client.login(account, password):
        work_session.bind_token(cas_client.get_session_token())
        return work_session, cas_client

    err = cas_client.get_last_error()
    if _network_like_error(err):
        raise unittest.SkipTest(f"CAS e2e environment unavailable: {err.get('message')}")
    raise AssertionError(f"CAS login failed: {err}")


def namespace_param(name, scope=UNSET, description=None, status=STATUS_ENABLE):
    start_time, expire_time = default_time_window()
    payload = {
        "name": name,
        "description": description or f"namespace {name}",
        "status": status,
        "startTime": start_time,
        "expireTime": expire_time,
    }
    if scope is not UNSET and scope is not None:
        payload["scope"] = scope
    return payload


def role_param(name, status=STATUS_ENABLE, privilege=None, group="e2e", description=None):
    return {
        "name": name,
        "description": description or f"role {name}",
        "group": group,
        "privilege": privilege if privilege is not None else all_privilege(),
        "status": status,
    }


def account_param(name, role, password="Test@123", status=STATUS_ENABLE, description=None):
    return {
        "account": name,
        "password": password,
        "email": f"{name}@example.com",
        "description": description or f"account {name}",
        "status": status,
        "role": {
            "id": role["id"],
            "name": role["name"],
            "status": role.get("status", STATUS_ENABLE),
        },
    }


def endpoint_param(name, account, role, scope, status=STATUS_ENABLE, description=None):
    start_time, expire_time = default_time_window()
    return {
        "name": name,
        "description": description or f"endpoint {name}",
        "account": {
            "id": account["id"],
            "account": account["account"],
            "status": account.get("status", STATUS_ENABLE),
        },
        "role": {
            "id": role["id"],
            "name": role["name"],
            "status": role.get("status", STATUS_ENABLE),
        },
        "scope": scope,
        "status": status,
        "startTime": start_time,
        "expireTime": expire_time,
    }


def auth_secret_param(endpoint_name, entity_id, scope, role=None, description=None):
    start_time, expire_time = default_time_window()
    payload = {
        "endpoint": endpoint_name,
        "description": description or f"auth secret {endpoint_name}",
        "entity": entity_id,
        "scope": scope,
        "startTime": start_time,
        "expireTime": expire_time,
    }
    if role is not None:
        payload["role"] = {
            "id": role["id"],
            "name": role["name"],
            "status": role.get("status", STATUS_ENABLE),
        }
    return payload


class CasE2EBase(unittest.TestCase):
    server_url = os.getenv("MAGICTEST_CAS_BASE_URL", "https://panel.local.vpc")
    panel_namespace = os.getenv("MAGICTEST_CAS_PANEL_NAMESPACE", "panel")

    @classmethod
    def setUpClass(cls):
        pass

    def setUp(self):
        self.panel_session, self.panel_cas = login_or_skip(self.server_url, self.panel_namespace)
        self.namespace_app = NamespaceApp(self.panel_session)
        self.role_app = RoleApp(self.panel_session)
        self.account_app = AccountApp(self.panel_session)
        self.endpoint_app = EndpointApp(self.panel_session)
        self._cleanup_actions = []

    def tearDown(self):
        for cleanup in reversed(self._cleanup_actions):
            try:
                cleanup()
            except Exception:
                pass

    def cleanup_delete(self, app, object_id, delete_method):
        self._cleanup_actions.append(lambda: getattr(app, delete_method)(object_id))

    def create_namespace(self, name=None, scope=UNSET):
        namespace_name = name or unique_name("ns")
        namespace = self.namespace_app.create_namespace(namespace_param(namespace_name, scope=scope))
        self.assertIsNotNone(namespace, "创建 namespace 失败")
        self.cleanup_delete(self.namespace_app, namespace["id"], "delete_namespace")
        return namespace

    def bind_namespace_apps(self, namespace_name):
        work_session = MagicSession(self.server_url, namespace_name)
        work_session.bind_token(self.panel_cas.get_session_token())
        return {
            "session": work_session,
            "cas": Cas(work_session),
            "namespace": NamespaceApp(work_session),
            "role": RoleApp(work_session),
            "account": AccountApp(work_session),
            "endpoint": EndpointApp(work_session),
        }

    def create_role(self, app, name=None, status=STATUS_ENABLE, privilege=None):
        role_name = name or unique_name("role")
        role = app.create_role(role_param(role_name, status=status, privilege=privilege))
        self.assertIsNotNone(role, "创建 role 失败")
        self.cleanup_delete(app, role["id"], "delete_role")
        return role

    def create_account(self, app, role, name=None, password="Test@123", status=STATUS_ENABLE):
        account_name = name or unique_name("account")
        account = app.create_account(account_param(account_name, role, password=password, status=status))
        self.assertIsNotNone(account, "创建 account 失败")
        self.cleanup_delete(app, account["id"], "delete_account")
        return account

    def create_endpoint(self, app, account, role, scope, name=None, status=STATUS_ENABLE):
        endpoint_name = name or unique_name("endpoint")
        endpoint = app.create_endpoint(endpoint_param(endpoint_name, account, role, scope, status=status))
        self.assertIsNotNone(endpoint, "创建 endpoint 失败")
        self.cleanup_delete(app, endpoint["id"], "delete_endpoint")
        return endpoint
