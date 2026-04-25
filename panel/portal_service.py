import logging
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class PortalServiceClient:
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
        response = self.session.get("/portal/services/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤门户服务", response)
            return None
        return response.get("values", [])

    def query_service_debug_metadata(self, service_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/portal/service/debug/{service_id}")
        if self._error(response) is not None:
            self._log_error("查询门户服务调试元数据", response)
            return None
        return response.get("value")

    def create_subscription(self, service_id: int, lease_term: int = 30) -> Optional[Dict[str, Any]]:
        response = self.session.post(
            "/portal/service/subscriptions/",
            {"service": service_id, "leaseTerm": lease_term},
        )
        if self._error(response) is not None:
            self._log_error("创建门户订阅", response)
            return None
        return response.get("value")

    def delete_subscription(self, service_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.delete(f"/portal/service/subscriptions/{service_id}")
        if self._error(response) is not None:
            self._log_error("删除门户订阅", response)
            return None
        return response.get("value")

    def filter_endpoints(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/portal/service/endpoints/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤服务 endpoint", response)
            return None
        return response.get("values", [])

    def create_endpoint(self, service_id: int, endpoint_name: str) -> Optional[Dict[str, Any]]:
        response = self.session.post(
            "/portal/service/endpoints/",
            {"service": service_id, "endpointName": endpoint_name},
        )
        if self._error(response) is not None:
            self._log_error("创建服务 endpoint", response)
            return None
        return response.get("value")

    def delete_endpoint(self, service_id: int, endpoint_name: str) -> Optional[Dict[str, Any]]:
        response = self.session.delete(
            f"/portal/service/endpoints/{service_id}",
            {"endpointName": endpoint_name},
        )
        if self._error(response) is not None:
            self._log_error("删除服务 endpoint", response)
            return None
        return response.get("value")
