import logging
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class ServiceRegistryClient:
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

    def filter_services(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/hub/services/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤服务定义", response)
            return None
        return response.get("values", [])

    def query_service(self, service_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/hub/services/{service_id}")
        if self._error(response) is not None:
            self._log_error("查询服务定义", response)
            return None
        return response.get("value")

    def query_service_debug_metadata(self, service_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/hub/service/debug/{service_id}")
        if self._error(response) is not None:
            self._log_error("查询服务调试元数据", response)
            return None
        return response.get("value")

    def filter_publications(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/hub/publications/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤服务发布", response)
            return None
        return response.get("values", [])
