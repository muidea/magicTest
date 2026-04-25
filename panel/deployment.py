import logging
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class DeploymentClient:
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

    def filter_application_releases(
        self,
        filter_param: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/application/releases/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤应用发布", response)
            return None
        return response.get("values", [])

    def filter_application_packages(
        self,
        filter_param: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/application/packages/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤应用安装包", response)
            return None
        return response.get("values", [])

    def filter_database_instances(
        self,
        filter_param: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/database/instances/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤数据库实例", response)
            return None
        return response.get("values", [])

    def install_online_application(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.post("/panel/application/install/online", payload)
        if self._error(response) is not None:
            self._log_error("在线安装应用", response)
            return None
        return response.get("task") or response.get("value")
