import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from session import MagicSession


logger = logging.getLogger(__name__)


class AppsRuntimeClient:
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

    def query_runtime_metadata(self, runtime_key: str) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/apps/application/runtimes/{quote(runtime_key, safe='')}")
        if self._error(response) is not None:
            self._log_error(f"查询应用运行期元数据({runtime_key})", response)
            return None
        return response.get("value")

    def query_entity_list(self, api_path: str) -> Optional[List[Dict[str, Any]]]:
        relative_path = _to_relative_api_path(api_path)
        response = self.session.get(relative_path)
        if self._error(response) is not None:
            self._log_error(f"查询实体列表({relative_path})", response)
            return None
        return response.get("values", [])

    def query_entity_detail(self, api_path: str, entity_id: Any) -> Optional[Dict[str, Any]]:
        relative_path = _format_detail_api_path(api_path, entity_id)
        response = self.session.get(relative_path)
        if self._error(response) is not None:
            self._log_error(f"查询实体详情({relative_path})", response)
            return None
        return response.get("value")

    def create_entity_value(self, api_path: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        relative_path = _to_relative_api_path(api_path)
        response = self.session.post(relative_path, payload)
        if self._error(response) is not None:
            self._log_error(f"创建实体({relative_path})", response)
            return None
        return response.get("value")

    def update_entity_value(self, api_path: str, entity_id: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        relative_path = _format_detail_api_path(api_path, entity_id)
        response = self.session.put(relative_path, payload)
        if self._error(response) is not None:
            self._log_error(f"更新实体({relative_path})", response)
            return None
        return response.get("value")

    def delete_entity_value(self, api_path: str, entity_id: Any) -> Tuple[bool, Optional[Dict[str, Any]]]:
        relative_path = _format_detail_api_path(api_path, entity_id)
        response = self.session.delete(relative_path)
        if self._error(response) is not None:
            self._log_error(f"删除实体({relative_path})", response)
            return False, response
        return True, response.get("value")


def _to_relative_api_path(api_path: str) -> str:
    if api_path.startswith("/api/v1"):
        return api_path[len("/api/v1"):]
    return api_path


def _format_detail_api_path(api_path: str, entity_id: Any) -> str:
    relative_path = _to_relative_api_path(api_path)
    return relative_path.replace("{id}", str(entity_id))
