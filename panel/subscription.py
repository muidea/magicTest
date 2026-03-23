import logging
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class SubscriptionClient:
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

    def filter_subscriptions(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/hub/subscription/filter/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤订阅", response)
            return None
        return response.get("values", [])

    def query_subscription(self, subscription_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/hub/subscription/query/{subscription_id}")
        if self._error(response) is not None:
            self._log_error("查询订阅", response)
            return None
        return response.get("value")

    def enable_subscription(self, subscription_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/hub/subscriptions/enable/{subscription_id}", {})
        if self._error(response) is not None:
            self._log_error("启用订阅", response)
            return None
        return response.get("value")

    def disable_subscription(self, subscription_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/hub/subscriptions/disable/{subscription_id}", {})
        if self._error(response) is not None:
            self._log_error("停用订阅", response)
            return None
        return response.get("value")

    def approve_subscription(self, subscription_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/hub/subscriptions/approve/{subscription_id}", {})
        if self._error(response) is not None:
            self._log_error("审批订阅", response)
            return None
        return response.get("value")

    def filter_endpoints(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/hub/subscription/endpoint/filter/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤订阅 endpoint", response)
            return None
        return response.get("values", [])

    def query_endpoint(self, subscription_id: int, endpoint_name: str) -> Optional[Dict[str, Any]]:
        response = self.session.get(
            f"/panel/hub/subscription/endpoint/query/{subscription_id}",
            {"endpointName": endpoint_name},
        )
        if self._error(response) is not None:
            self._log_error("查询订阅 endpoint", response)
            return None
        return response.get("value")

    def create_endpoint(self, subscription_id: int, endpoint_name: str) -> Optional[Dict[str, Any]]:
        response = self.session.post(
            "/panel/hub/subscription/endpoint/insert/",
            {"subscription": subscription_id, "endpointName": endpoint_name},
        )
        if self._error(response) is not None:
            self._log_error("创建订阅 endpoint", response)
            return None
        return response.get("value")

    def delete_endpoint(self, subscription_id: int, endpoint_name: str) -> Optional[Dict[str, Any]]:
        response = self.session.delete(
            f"/panel/hub/subscription/endpoint/delete/{subscription_id}",
            {"endpointName": endpoint_name},
        )
        if self._error(response) is not None:
            self._log_error("删除订阅 endpoint", response)
            return None
        return response.get("value")
