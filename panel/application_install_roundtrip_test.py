import os
import time
import unittest
import uuid
from typing import Dict, List, Optional, Tuple

from deployment import DeploymentClient
from lifecycle import LifecycleClient
from panel_test_support import PanelE2EBase


TASK_STATUS_SUCCEEDED = "succeeded"
TASK_STATUS_FAILED = "failed"
RUNNING_STATUS = 3
STOPPED_STATUS = 4


class PanelApplicationInstallRoundtripTestCase(PanelE2EBase):
    release_id = int(os.getenv("MAGICTEST_PANEL_INSTALL_RELEASE_ID", "0") or "0")
    package_id = int(os.getenv("MAGICTEST_PANEL_INSTALL_PACKAGE_ID", "0") or "0")
    source_uuid = os.getenv("MAGICTEST_PANEL_INSTALL_SOURCE_UUID", "").strip()
    source_pkg_prefix = os.getenv("MAGICTEST_PANEL_INSTALL_SOURCE_PKG_PREFIX", "").strip()
    database_instance_id = int(os.getenv("MAGICTEST_PANEL_INSTALL_DATABASE_INSTANCE_ID", "0") or "0")
    task_timeout_seconds = int(os.getenv("MAGICTEST_PANEL_INSTALL_TASK_TIMEOUT", "240") or "240")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.deployment_client = DeploymentClient(cls.work_session)
        cls.lifecycle_client = LifecycleClient(cls.work_session)

    def _wait_for_task(self, task_id: str) -> Dict:
        deadline = time.time() + self.task_timeout_seconds
        latest_task: Optional[Dict] = None
        while time.time() < deadline:
            latest_task = self.lifecycle_client.query_install_task(task_id)
            self.assertIsNotNone(latest_task, f"查询任务失败: {task_id}")
            status = latest_task.get("status")
            if status in (TASK_STATUS_SUCCEEDED, TASK_STATUS_FAILED):
                return latest_task
            time.sleep(2)
        self.fail(f"等待任务结束超时: {task_id}, latest={latest_task}")

    def _find_runtime(self, runtime_uuid: str) -> Optional[Dict]:
        running_list = self.lifecycle_client.fetch_running_applications()
        self.assertIsNotNone(running_list, "查询运行中应用失败")
        for item in running_list or []:
            if item.get("uuid") == runtime_uuid:
                return item
        return None

    def _wait_for_runtime_state(self, runtime_uuid: str, expect_present: bool) -> Optional[Dict]:
        deadline = time.time() + self.task_timeout_seconds
        latest_runtime: Optional[Dict] = None
        while time.time() < deadline:
            latest_runtime = self._find_runtime(runtime_uuid)
            if expect_present and latest_runtime is not None:
                return latest_runtime
            if not expect_present and latest_runtime is None:
                return None
            time.sleep(2)
        if expect_present:
            self.fail(f"等待应用实例出现超时: {runtime_uuid}")
        self.fail(f"等待应用实例卸载完成超时: {runtime_uuid}, latest={latest_runtime}")

    def _wait_for_runtime_status(self, runtime_uuid: str, expected_status: int) -> Dict:
        deadline = time.time() + self.task_timeout_seconds
        latest_runtime: Optional[Dict] = None
        while time.time() < deadline:
            latest_runtime = self._find_runtime(runtime_uuid)
            self.assertIsNotNone(latest_runtime, f"应用实例不存在: {runtime_uuid}")
            if latest_runtime.get("status") == expected_status:
                return latest_runtime
            time.sleep(2)
        self.fail(f"等待应用实例状态变更超时: runtime={runtime_uuid}, expected={expected_status}, latest={latest_runtime}")

    def _database_instance(self) -> Dict:
        if self.database_instance_id > 0:
            instances = self.deployment_client.filter_database_instances({})
            self.assertIsNotNone(instances, "查询数据库实例失败")
            matched = next((item for item in (instances or []) if item.get("id") == self.database_instance_id), None)
            if matched is None:
                self.fail(f"未找到显式指定的数据库实例: {self.database_instance_id}")
            return matched

        instances = self.deployment_client.filter_database_instances({})
        self.assertIsNotNone(instances, "查询数据库实例失败")
        if not instances:
            raise unittest.SkipTest("当前环境未配置数据库实例，跳过在线安装回归")
        return instances[0]

    @staticmethod
    def _match_source_runtime(runtime: Dict, package: Dict) -> bool:
        candidates = {
            package.get("appUUID"),
            package.get("appPkgPrefix"),
            package.get("appName"),
        }
        candidates.discard(None)
        return (
            runtime.get("uuid") in candidates
            or runtime.get("pkgPrefix") in candidates
            or runtime.get("name") in candidates
        )

    def _resolve_install_source(self) -> Tuple[Dict, Dict, Dict]:
        release_list = self.deployment_client.filter_application_releases({"status": 2})
        self.assertIsNotNone(release_list, "查询应用发布失败")
        package_list = self.deployment_client.filter_application_packages({"status": 2})
        self.assertIsNotNone(package_list, "查询应用安装包失败")
        running_list = self.lifecycle_client.fetch_running_applications()
        self.assertIsNotNone(running_list, "查询运行中应用失败")

        package_by_id = {item.get("id"): item for item in package_list or [] if item.get("id")}
        non_bootstrap_running = [
            item
            for item in (running_list or [])
            if item.get("installSource") != "bootstrap"
        ]

        if self.release_id > 0 and self.package_id > 0:
            matched_release = next((item for item in (release_list or []) if item.get("id") == self.release_id), None)
            if matched_release is None:
                self.fail(f"未找到显式指定的发布: {self.release_id}")
            matched_package = package_by_id.get(self.package_id)
            if matched_package is None:
                self.fail(f"未找到显式指定的安装包: {self.package_id}")
            matched_runtime = next(
                (
                    item
                    for item in non_bootstrap_running
                    if (not self.source_uuid or item.get("uuid") == self.source_uuid)
                    and (not self.source_pkg_prefix or item.get("pkgPrefix") == self.source_pkg_prefix)
                    and self._match_source_runtime(item, matched_package)
                ),
                None,
            )
            if matched_runtime is None:
                raise unittest.SkipTest("未找到与显式安装源匹配的已运行实例，跳过多实例安装回归")
            return matched_release, matched_package, matched_runtime

        for release in release_list or []:
            package = package_by_id.get(release.get("packageID"))
            if package is None:
                continue
            matched_runtime = next(
                (item for item in non_bootstrap_running if self._match_source_runtime(item, package)),
                None,
            )
            if matched_runtime is None:
                continue
            return release, package, matched_runtime

        raise unittest.SkipTest("当前环境未发现可用于多实例在线安装的非 bootstrap 发布与实例")

    def _build_install_payload(self, release: Dict, package: Dict, runtime_name: str, db_instance_id: int) -> Dict:
        show_name = package.get("appShowName") or package.get("appName") or runtime_name
        icon = package.get("appIcon") or ""
        source_uuid = self.source_uuid or package.get("appUUID") or ""
        source_pkg_prefix = self.source_pkg_prefix or package.get("appPkgPrefix") or ""
        if not source_uuid or not source_pkg_prefix:
            self.fail(f"安装源信息不完整: package={package}")

        return {
            "uuid": runtime_name,
            "name": runtime_name,
            "showName": f"{show_name}-e2e",
            "pkgPrefix": runtime_name,
            "icon": icon,
            "domain": "",
            "sourceUUID": source_uuid,
            "sourcePkgPrefix": source_pkg_prefix,
            "releaseID": release.get("id"),
            "releaseVersion": release.get("version"),
            "packageID": package.get("id"),
            "appID": runtime_name,
            "schema": {
                "dbName": "",
                "username": "",
                "password": "",
                "hostBy": {"id": db_instance_id},
            },
        }

    def _install_instance(self, release: Dict, package: Dict, runtime_name: str, db_instance_id: int) -> Dict:
        task = self.deployment_client.install_online_application(
            self._build_install_payload(release, package, runtime_name, db_instance_id)
        )
        self.assertIsNotNone(task, f"提交在线安装任务失败: runtime={runtime_name}")
        task_id = task.get("id")
        self.assertTrue(task_id, f"在线安装任务缺少任务 ID: {task}")
        finished_task = self._wait_for_task(task_id)
        self.assertEqual(
            finished_task.get("status"),
            TASK_STATUS_SUCCEEDED,
            f"在线安装失败: task={finished_task}",
        )
        runtime = self._wait_for_runtime_state(runtime_name, expect_present=True)
        self.assertIsNotNone(runtime, "安装完成后未发现新运行期实例")
        self.assertEqual(runtime.get("status"), RUNNING_STATUS, f"新实例未处于运行状态: {runtime}")
        return finished_task

    def _uninstall_instance(self, runtime_name: str) -> Dict:
        runtime = self._find_runtime(runtime_name)
        if runtime is not None and runtime.get("status") == RUNNING_STATUS:
            stopped = self.lifecycle_client.stop_application(runtime_name)
            self.assertIsNotNone(stopped, f"提交停止任务失败: runtime={runtime_name}")
            self._wait_for_runtime_status(runtime_name, STOPPED_STATUS)

        task = self.lifecycle_client.uninstall_application(runtime_name)
        self.assertIsNotNone(task, f"提交卸载任务失败: runtime={runtime_name}")
        task_id = task.get("id")
        self.assertTrue(task_id, f"卸载任务缺少任务 ID: {task}")
        finished_task = self._wait_for_task(task_id)
        self.assertEqual(
            finished_task.get("status"),
            TASK_STATUS_SUCCEEDED,
            f"卸载失败: task={finished_task}",
        )
        self._wait_for_runtime_state(runtime_name, expect_present=False)
        return finished_task

    def test_online_install_uninstall_repeat_install_is_idempotent(self):
        release, package, source_runtime = self._resolve_install_source()
        database_instance = self._database_instance()
        source_runtime_uuid = source_runtime.get("uuid")
        self.assertTrue(source_runtime_uuid, f"源运行期实例缺少 uuid: {source_runtime}")
        self.assertIsNotNone(self._find_runtime(source_runtime_uuid), "源运行期实例不存在，无法验证多实例安装")

        runtime_a = f"e2e{uuid.uuid4().hex[:8]}"
        runtime_b = f"e2e{uuid.uuid4().hex[:8]}"
        cleanup_targets: List[str] = []

        try:
            self._install_instance(release, package, runtime_a, int(database_instance.get("id") or 0))
            cleanup_targets.append(runtime_a)
            self.assertIsNotNone(
                self._find_runtime(source_runtime_uuid),
                "安装第二实例后不应影响原实例",
            )

            self._uninstall_instance(runtime_a)
            cleanup_targets.remove(runtime_a)
            self.assertIsNotNone(
                self._find_runtime(source_runtime_uuid),
                "卸载第二实例后不应误删原实例",
            )

            self._install_instance(release, package, runtime_b, int(database_instance.get("id") or 0))
            cleanup_targets.append(runtime_b)
            self.assertIsNotNone(
                self._find_runtime(source_runtime_uuid),
                "重复安装同一发布后原实例不应受影响",
            )
        finally:
            for runtime_name in list(cleanup_targets):
                try:
                    self._uninstall_instance(runtime_name)
                except AssertionError:
                    pass
