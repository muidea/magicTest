import json
import logging
from typing import Any, Dict, Optional, Tuple

from session import MagicSession


logger = logging.getLogger(__name__)


class ServiceAccessClient:
    def __init__(self, work_session: MagicSession) -> None:
        self.session = work_session

    def _compose_url(self, path: str) -> str:
        return f"{self.session.base_url}{path}"

    def _decode_response_body(self, response) -> Dict[str, Any]:
        if response is None:
            return {"error": {"code": 100, "message": "无响应"}}
        if not getattr(response, "text", ""):
            return {}
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        request_headers = self.session.header()
        if headers:
            request_headers.update(headers)
        response = self.session.current_session.request(
            method,
            self._compose_url(path),
            params=params,
            json=json_body,
            headers=request_headers,
            verify=self.session.verify_ssl,
            timeout=self.session.timeout,
        )
        body = self._decode_response_body(response)
        return response.status_code, body

    def get_service(
        self,
        service_key: str,
        capability_key: Optional[str] = None,
        suffix: Any = "",
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        path = f"/gateway/services/{service_key}"
        if capability_key:
            path += f"/{capability_key}"
        normalized_suffix = str(suffix).strip("/") if suffix is not None else ""
        if normalized_suffix:
            path += f"/{normalized_suffix}"
        return self.request("GET", path, params=params)

    def create_service(
        self,
        service_key: str,
        capability_key: str,
        payload: Dict[str, Any],
    ) -> Tuple[int, Dict[str, Any]]:
        path = f"/gateway/services/{service_key}/{capability_key}"
        return self.request("POST", path, json_body=payload)

    def update_service(
        self,
        service_key: str,
        capability_key: str,
        entity_id: Any,
        payload: Dict[str, Any],
    ) -> Tuple[int, Dict[str, Any]]:
        path = f"/gateway/services/{service_key}/{capability_key}/{entity_id}"
        return self.request("PUT", path, json_body=payload)

    def delete_service(
        self,
        service_key: str,
        capability_key: str,
        entity_id: Any,
    ) -> Tuple[int, Dict[str, Any]]:
        path = f"/gateway/services/{service_key}/{capability_key}/{entity_id}"
        return self.request("DELETE", path)


def extract_error_message(payload: Dict[str, Any]) -> str:
    if not payload:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or "")
    if "raw" in payload:
        return str(payload.get("raw") or "")
    return json.dumps(payload, ensure_ascii=False)


def extract_first_entity_id(payload: Dict[str, Any]) -> Optional[int]:
    if not isinstance(payload, dict):
        return None

    values = payload.get("values")
    if isinstance(values, list):
        for item in values:
            if not isinstance(item, dict):
                continue
            entity_id = item.get("id")
            if isinstance(entity_id, int):
                return entity_id
            nested_value = item.get("value")
            if isinstance(nested_value, dict):
                nested_id = nested_value.get("id")
                if isinstance(nested_id, int):
                    return nested_id

    value = payload.get("value")
    if isinstance(value, dict):
        entity_id = value.get("id")
        if isinstance(entity_id, int):
            return entity_id

    return None
