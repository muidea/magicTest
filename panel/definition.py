import logging
import uuid
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class DefinitionClient:
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

    def filter_application_definitions(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/application/definitions/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤 application definition", response)
            return None
        return response.get("values", [])

    def query_application_definition(self, definition_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/application/definitions/{definition_id}")
        if self._error(response) is not None:
            self._log_error("查询 application definition", response)
            return None
        return response.get("value")

    def create_application_definition(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.post("/panel/application/definitions/", param)
        if self._error(response) is not None:
            self._log_error("创建 application definition", response)
            return None
        return response.get("value")

    def update_application_definition(self, definition_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/application/definitions/{definition_id}", param)
        if self._error(response) is not None:
            self._log_error("更新 application definition", response)
            return None
        return response.get("value")

    def delete_application_definition(self, definition_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.delete(f"/panel/application/definitions/{definition_id}")
        if self._error(response) is not None:
            self._log_error("删除 application definition", response)
            return None
        return response.get("value")

    def query_application_pkg_tree(self, definition_id: int) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get(f"/panel/application/definition/pkgTrees/{definition_id}")
        if self._error(response) is not None:
            self._log_error("查询 application pkg tree", response)
            return None
        return response.get("values", [])

    def filter_entity_definitions(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/application/definition/entitys/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤 entity definition", response)
            return None
        return response.get("values", [])

    def query_entity_definition(self, entity_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/application/definition/entitys/{entity_id}")
        if self._error(response) is not None:
            self._log_error("查询 entity definition", response)
            return None
        return response.get("value")

    def create_entity_definition(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.post("/panel/application/definition/entitys/", param)
        if self._error(response) is not None:
            self._log_error("创建 entity definition", response)
            return None
        return response.get("value")

    def update_entity_definition(self, entity_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/application/definition/entitys/{entity_id}", param)
        if self._error(response) is not None:
            self._log_error("更新 entity definition", response)
            return None
        return response.get("value")

    def delete_entity_definition(self, entity_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.delete(f"/panel/application/definition/entitys/{entity_id}")
        if self._error(response) is not None:
            self._log_error("删除 entity definition", response)
            return None
        return response.get("value")


def mock_application_definition_param() -> Dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "uuid": str(uuid.uuid4()),
        "name": f"panel_definition_{suffix}",
        "showName": f"Panel Definition {suffix}",
        "icon": "/static/files/share/panel/app.svg",
        "catalog": "panel-e2e",
        "version": "1.0.0",
        "email": f"panel_{suffix}@example.com",
        "author": "panel-e2e",
        "description": f"panel definition e2e {suffix}",
    }


def mock_entity_definition_param(application_definition: Dict[str, Any]) -> Dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "name": f"entity_{suffix}",
        "showName": f"Entity {suffix}",
        "pkgPath": f"/panel/e2e/{suffix}",
        "description": f"entity definition e2e {suffix}",
        "version": "1.0.0",
        "object": {},
        "blockInfo": [],
        "application": {
            "id": application_definition["id"],
            "uuid": application_definition["uuid"],
            "name": application_definition["name"],
            "showName": application_definition["showName"],
            "icon": application_definition.get("icon", ""),
            "catalog": application_definition.get("catalog", ""),
            "version": application_definition.get("version", ""),
        },
    }
