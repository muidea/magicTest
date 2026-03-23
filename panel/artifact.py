import logging
import uuid
from typing import Any, Dict, List, Optional

from session import MagicSession


logger = logging.getLogger(__name__)


class ArtifactClient:
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

    def filter_application_artifacts(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/artifact/application/filter/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤 application artifact", response)
            return None
        return response.get("values", [])

    def query_application_artifact(self, artifact_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/artifact/application/query/{artifact_id}")
        if self._error(response) is not None:
            self._log_error("查询 application artifact", response)
            return None
        return response.get("value")

    def create_application_artifact(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.post("/panel/artifact/application/insert/", param)
        if self._error(response) is not None:
            self._log_error("创建 application artifact", response)
            return None
        return response.get("value")

    def update_application_artifact(self, artifact_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/artifact/application/update/{artifact_id}", param)
        if self._error(response) is not None:
            self._log_error("更新 application artifact", response)
            return None
        return response.get("value")

    def delete_application_artifact(self, artifact_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.delete(f"/panel/artifact/application/delete/{artifact_id}")
        if self._error(response) is not None:
            self._log_error("删除 application artifact", response)
            return None
        return response.get("value")

    def query_application_pkg_tree(self, artifact_id: int) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get(f"/panel/artifact/application/pkgTree/query/{artifact_id}")
        if self._error(response) is not None:
            self._log_error("查询 application pkg tree", response)
            return None
        return response.get("values", [])

    def filter_entities(self, filter_param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        response = self.session.get("/panel/artifact/entity/filter/", filter_param)
        if self._error(response) is not None:
            self._log_error("过滤 entity artifact", response)
            return None
        return response.get("values", [])

    def query_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.get(f"/panel/artifact/entity/query/{entity_id}")
        if self._error(response) is not None:
            self._log_error("查询 entity artifact", response)
            return None
        return response.get("value")

    def create_entity(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.post("/panel/artifact/entity/insert/", param)
        if self._error(response) is not None:
            self._log_error("创建 entity artifact", response)
            return None
        return response.get("value")

    def update_entity(self, entity_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        response = self.session.put(f"/panel/artifact/entity/update/{entity_id}", param)
        if self._error(response) is not None:
            self._log_error("更新 entity artifact", response)
            return None
        return response.get("value")

    def delete_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
        response = self.session.delete(f"/panel/artifact/entity/delete/{entity_id}")
        if self._error(response) is not None:
            self._log_error("删除 entity artifact", response)
            return None
        return response.get("value")


def mock_application_artifact_param() -> Dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "uuid": str(uuid.uuid4()),
        "name": f"panel_artifact_{suffix}",
        "showName": f"Panel Artifact {suffix}",
        "icon": "/static/files/share/panel/app.svg",
        "catalog": "panel-e2e",
        "version": "1.0.0",
        "email": f"panel_{suffix}@example.com",
        "author": "panel-e2e",
        "description": f"panel artifact e2e {suffix}",
    }


def mock_entity_artifact_param(application_artifact: Dict[str, Any]) -> Dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    return {
        "name": f"entity_{suffix}",
        "showName": f"Entity {suffix}",
        "pkgPath": f"/panel/e2e/{suffix}",
        "description": f"entity artifact e2e {suffix}",
        "version": "1.0.0",
        "object": {},
        "blockInfo": [],
        "application": {
            "id": application_artifact["id"],
            "uuid": application_artifact["uuid"],
            "name": application_artifact["name"],
            "showName": application_artifact["showName"],
            "icon": application_artifact.get("icon", ""),
            "catalog": application_artifact.get("catalog", ""),
            "version": application_artifact.get("version", ""),
        },
    }
