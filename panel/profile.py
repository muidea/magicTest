import logging
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class ProfileClient:
    def __init__(self, work_session: MagicSession) -> None:
        self.session = work_session

    def _error(self, response: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if response is None:
            return {"code": 100, "message": "无响应"}
        return response.get("error")

    def _log_error(self, action: str, response: Optional[Dict[str, Any]]) -> None:
        err = self._error(response)
        if err is None:
            return
        logger.error("%s失败: %s", action, err.get("message"))

    def get_system_notifications(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/system/notifications/", filter_param)
        if self._error(response) is not None:
            self._log_error("查询系统通知", response)
            return None
        return response.get("values", [])

    def get_profile(self) -> Optional[Dict[str, Any]]:
        response = self.session.get("/panel/profile")
        if self._error(response) is not None:
            self._log_error("查询 profile", response)
            return None
        return response.get("value")
