import os
import unittest
from typing import Optional, Tuple

from cas import Cas
from session import MagicSession


def _network_like_error(err):
    if not err:
        return False
    message = err.get("message", "")
    status_code = err.get("status_code", 0)
    return status_code == 0 or "HTTP请求失败" in message or "NameResolutionError" in message


def panel_base_url() -> str:
    return os.getenv("MAGICTEST_PANEL_BASE_URL", "https://autotest.local.vpc/api/v1")


def panel_namespace() -> str:
    return os.getenv("MAGICTEST_PANEL_NAMESPACE", "panel")


def cas_base_url_from_panel_base(panel_url: str) -> str:
    suffix = "/api/v1"
    if panel_url.endswith(suffix):
        return panel_url[:-len(suffix)]
    return panel_url.rstrip("/")


def bind_panel_auth(work_session: MagicSession) -> Tuple[MagicSession, Optional[Cas]]:
    bearer_token = os.getenv("MAGICTEST_PANEL_BEARER_TOKEN", "")
    if bearer_token:
        work_session.bind_token(bearer_token)
        return work_session, None

    auth_endpoint = os.getenv("MAGICTEST_PANEL_AUTH_ENDPOINT", "")
    auth_token = os.getenv("MAGICTEST_PANEL_AUTH_TOKEN", "")
    if auth_endpoint and auth_token:
        work_session.bind_auth_secret(auth_endpoint, auth_token)
        return work_session, None

    login_account = os.getenv("MAGICTEST_PANEL_LOGIN_ACCOUNT", "administrator")
    login_password = os.getenv("MAGICTEST_PANEL_LOGIN_PASSWORD", "administrator")
    cas_session = MagicSession(cas_base_url_from_panel_base(work_session.base_url), work_session.namespace)
    cas_client = Cas(cas_session)
    if not cas_client.login(login_account, login_password):
        err = cas_client.get_last_error()
        if _network_like_error(err):
            raise unittest.SkipTest(f"panel e2e environment unavailable: {err.get('message')}")
        raise AssertionError(f"panel login failed: {err}")

    work_session.bind_token(cas_client.get_session_token())
    return work_session, cas_client


class PanelE2EBase(unittest.TestCase):
    server_url = panel_base_url()
    namespace = panel_namespace()

    @classmethod
    def setUpClass(cls):
        cls.work_session = MagicSession(cls.server_url, cls.namespace)
        cls.work_session, cls.cas_client = bind_panel_auth(cls.work_session)
