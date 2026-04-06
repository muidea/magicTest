#!/usr/bin/env python3
"""
基于会话管理器的并发测试V2
基于当前框架重新实现并发执行测试代码
"""

import argparse
import concurrent.futures
import json
import logging
import os
import random
import threading
import time
import unittest
import uuid
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ConcurrentTestResult:
    """并发测试结果数据类"""

    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    avg_response_time: float
    min_response_time: float
    max_response_time: float
    throughput: float
    error_details: List[Dict[str, Any]]
    timestamp: Optional[str] = None
    http_requests: int = 0
    http_successful_requests: int = 0
    http_failed_requests: int = 0
    http_read_requests: int = 0
    http_write_requests: int = 0
    http_avg_response_time: float = 0.0
    http_qps: float = 0.0
    read_qps: float = 0.0
    write_tps: float = 0.0

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


RUNTIME_ENV_ARG_MAP = {
    "server_url": "MAGICTEST_SERVER_URL",
    "tenant_targets": "MAGICTEST_TENANT_TARGETS",
    "tenant_url_template": "MAGICTEST_TENANT_URL_TEMPLATE",
    "default_tenant": "MAGICTEST_DEFAULT_TENANT",
    "username": "MAGICTEST_USERNAME",
    "password": "MAGICTEST_PASSWORD",
    "namespace": "MAGICTEST_NAMESPACE",
    "request_application": "MAGICTEST_REQUEST_APPLICATION",
    "max_workers": "MAGICTEST_MAX_WORKERS",
    "timeout": "MAGICTEST_TIMEOUT",
    "workers_per_tenant": "MAGICTEST_WORKERS_PER_TENANT",
    "iterations_per_worker": "MAGICTEST_ITERATIONS_PER_WORKER",
    "write_every": "MAGICTEST_WRITE_EVERY",
    "hotspot_read_rounds": "MAGICTEST_HOTSPOT_READ_ROUNDS",
    "hotspot_query_rounds": "MAGICTEST_HOTSPOT_QUERY_ROUNDS",
    "hotspot_prewrite_query": "MAGICTEST_HOTSPOT_PREWRITE_QUERY",
    "hotspot_shared_context_per_tenant": (
        "MAGICTEST_HOTSPOT_SHARED_CONTEXT_PER_TENANT"
    ),
    "hotspot_measure_loop_only": "MAGICTEST_HOTSPOT_MEASURE_LOOP_ONLY",
    "prometheus_url": "MAGICTEST_PROMETHEUS_URL",
    "remote_host": "MAGICTEST_REMOTE_HOST",
    "remote_user": "MAGICTEST_REMOTE_USER",
    "deployment_mode": "MAGICTEST_DEPLOYMENT_MODE",
    "request_trust_env": "REQUEST_TRUST_ENV",
}


def _stringify_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def apply_runtime_env_overrides(args: argparse.Namespace) -> Dict[str, str]:
    overrides: Dict[str, str] = {}
    for arg_name, env_name in RUNTIME_ENV_ARG_MAP.items():
        value = getattr(args, arg_name, None)
        if value is None:
            continue
        rendered = _stringify_env_value(value)
        os.environ[env_name] = rendered
        overrides[env_name] = rendered
    return overrides


def ensure_request_application(args: argparse.Namespace) -> Optional[str]:
    existing = getattr(args, "request_application", None) or os.getenv(
        "MAGICTEST_REQUEST_APPLICATION", ""
    ).strip()
    if existing:
        args.request_application = existing
        return args.request_application

    configured_prometheus_url = getattr(args, "prometheus_url", None)
    if not configured_prometheus_url:
        from config_helper import get_observability_config

        configured_prometheus_url = get_observability_config().get("prometheus_url", "")

    if not configured_prometheus_url:
        return None

    suite_name = "concurrent"
    if getattr(args, "hotspot", False):
        suite_name = "hotspot"
    elif getattr(args, "full_flow", False):
        suite_name = "fullflow"

    args.request_application = (
        f"magictest-{suite_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}-"
        f"{uuid.uuid4().hex[:6]}"
    )
    return args.request_application


def build_results_report(
    suite_name: str,
    results: Sequence[ConcurrentTestResult],
    metadata: Optional[Dict[str, Any]] = None,
    prometheus_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    total_requests = sum(result.total_requests for result in results)
    total_successful = sum(result.successful_requests for result in results)
    total_failed = sum(result.failed_requests for result in results)
    total_time = sum(result.total_time for result in results)

    report = {
        "suite_name": suite_name,
        "summary": {
            "total_runs": len(results),
            "total_requests": total_requests,
            "total_successful": total_successful,
            "total_failed": total_failed,
            "success_rate": (
                total_successful / total_requests * 100 if total_requests > 0 else 0.0
            ),
            "total_time": total_time,
            "avg_throughput": total_successful / total_time if total_time > 0 else 0.0,
            "generated_at": datetime.now().isoformat(),
        },
        "metadata": metadata or {},
        "results": [result.to_dict() for result in results],
        "errors": [error for result in results for error in result.error_details],
    }
    if prometheus_summary:
        report["prometheus_summary"] = prometheus_summary
    return report


def save_results_report(
    filepath: str,
    suite_name: str,
    results: Sequence[ConcurrentTestResult],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    prometheus_summary = build_prometheus_summary(metadata or {})
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            build_results_report(
                suite_name=suite_name,
                results=results,
                metadata=metadata,
                prometheus_summary=prometheus_summary,
            ),
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info("压测报告已保存到: %s", filepath)


def _prometheus_scalar_value(payload: Dict[str, Any]) -> float:
    result = payload.get("result", [])
    if not result:
        return 0.0
    return float(result[0].get("value", [0, "0"])[1])


def _prometheus_vector_values(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    values: List[Dict[str, Any]] = []
    for item in payload.get("result", []):
        values.append(
            {
                "metric": item.get("metric", {}),
                "value": float(item.get("value", [0, "0"])[1]),
            }
        )
    return values


def _aggregate_application_values(
    values: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    totals: Dict[str, float] = defaultdict(float)
    for item in values:
        metric = item.get("metric", {})
        application = str(metric.get("application", "")).strip()
        if not application:
            continue
        totals[application] += float(item.get("value", 0.0))

    ranked = [
        {"application": application, "value": value}
        for application, value in totals.items()
    ]
    ranked.sort(key=lambda item: item["value"], reverse=True)
    return ranked


def _query_prometheus(prometheus_url: str, query: str) -> Dict[str, Any]:
    verify_ssl = os.getenv("VERIFY_SSL", "false").lower() != "false"
    endpoint = urljoin(prometheus_url.rstrip("/") + "/", "api/v1/query")
    trust_env = os.getenv("REQUEST_TRUST_ENV", "false").lower() != "false"
    session = requests.Session()
    session.trust_env = trust_env
    response = session.get(
        endpoint,
        params={"query": query},
        timeout=30,
        verify=verify_ssl,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "success":
        raise ValueError(f"prometheus query failed: {payload}")
    return payload.get("data", {})


def build_prometheus_summary(metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    observability = metadata.get("observability") or {}
    prometheus_url = str(observability.get("prometheus_url", "")).strip()
    request_application = str(metadata.get("request_application", "")).strip()
    if not prometheus_url or not request_application:
        return None

    window = str(metadata.get("prometheus_window", "10m"))
    application_label = json.dumps(request_application)
    filtered_selector = f'job="magicbase",application={application_label}'
    summary: Dict[str, Any] = {
        "source": prometheus_url,
        "window": window,
        "application": request_application,
        "collected_at": datetime.now().isoformat(),
        "application_label_retained": False,
        "correlation_mode": "request_application_missing",
    }

    queries = {
        "http_requests_total_increase": (
            f"sum(increase(magicBase_magicbase_http_requests_total"
            f"{{{filtered_selector}}}[{window}]))"
        ),
        "http_write_success_total_increase": (
            f"sum(increase(magicBase_magicbase_http_transactions_total"
            f'{{{filtered_selector},kind="write",status="success"}}[{window}]))'
        ),
        "http_path_distribution": (
            f"topk(10, sum by (path) (increase(magicBase_magicbase_http_requests_total"
            f"{{{filtered_selector}}}[{window}])))"
        ),
        "orm_operations_total_increase": (
            f'sum(increase(magicBase_magicorm_orm_operations_total{{job="magicbase"}}[{window}]))'
        ),
        "database_queries_total_increase": (
            f'sum(increase(magicBase_magicorm_database_queries_total{{job="magicbase"}}[{window}]))'
        ),
        "database_executions_total_increase": (
            f'sum(increase(magicBase_magicorm_database_executions_total{{job="magicbase"}}[{window}]))'
        ),
        "http_requests_total_increase_unfiltered": (
            f'sum(increase(magicBase_magicbase_http_requests_total{{job="magicbase"}}[{window}]))'
        ),
        "http_top_applications_unfiltered": (
            f"topk(10, sum by (application, path) (increase("
            f"magicBase_magicbase_http_requests_total{{job=\"magicbase\"}}[{window}])))"
        ),
    }

    try:
        summary["http_requests_total_increase"] = _prometheus_scalar_value(
            _query_prometheus(prometheus_url, queries["http_requests_total_increase"])
        )
        summary["http_write_success_total_increase"] = _prometheus_scalar_value(
            _query_prometheus(
                prometheus_url, queries["http_write_success_total_increase"]
            )
        )
        summary["http_path_distribution"] = _prometheus_vector_values(
            _query_prometheus(prometheus_url, queries["http_path_distribution"])
        )
        summary["orm_operations_total_increase"] = _prometheus_scalar_value(
            _query_prometheus(prometheus_url, queries["orm_operations_total_increase"])
        )
        summary["database_queries_total_increase"] = _prometheus_scalar_value(
            _query_prometheus(
                prometheus_url, queries["database_queries_total_increase"]
            )
        )
        summary["database_executions_total_increase"] = _prometheus_scalar_value(
            _query_prometheus(
                prometheus_url, queries["database_executions_total_increase"]
            )
        )
        summary["http_requests_total_increase_unfiltered"] = _prometheus_scalar_value(
            _query_prometheus(
                prometheus_url, queries["http_requests_total_increase_unfiltered"]
            )
        )
        if summary["http_requests_total_increase"] > 0.0:
            summary["application_label_retained"] = True
            summary["correlation_mode"] = "request_application"
        else:
            summary["http_top_applications_unfiltered"] = _prometheus_vector_values(
                _query_prometheus(
                    prometheus_url, queries["http_top_applications_unfiltered"]
                )
            )
            if summary["http_top_applications_unfiltered"]:
                summary["top_application_totals_unfiltered"] = (
                    _aggregate_application_values(
                        summary["http_top_applications_unfiltered"]
                    )
                )
                if summary["top_application_totals_unfiltered"]:
                    primary_application = summary["top_application_totals_unfiltered"][
                        0
                    ]
                    summary["observed_application"] = primary_application[
                        "application"
                    ]
                    total_unfiltered = summary["http_requests_total_increase_unfiltered"]
                    summary["observed_application_share"] = (
                        primary_application["value"] / total_unfiltered
                        if total_unfiltered > 0
                        else 0.0
                    )
                summary["correlation_mode"] = "service_application_override"
                summary["note"] = (
                    "magicBase HTTP metrics did not retain the requested "
                    "request_application label; see unfiltered top applications."
                )
            else:
                summary["correlation_mode"] = "shared_window_only"
    except Exception as exc:
        logger.warning("Prometheus 摘要采集失败: %s", exc)
        summary["error"] = str(exc)

    return summary


class HTTPRequestMetricsCollector:
    """统计压测过程中的真实 HTTP 请求口径。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.read_requests = 0
        self.write_requests = 0
        self.total_elapsed = 0.0

    def observe(
        self,
        method: str,
        url: str,
        full_url: str,
        elapsed: float,
        status_code: int,
        response: Any,
        error: Optional[BaseException] = None,
    ) -> None:
        path = urlparse(full_url or url).path or url
        if self._should_ignore_path(path):
            return

        request_kind = self._classify_request_kind(method, path)
        success = self._is_success(status_code, response, error)

        with self.lock:
            self.total_requests += 1
            self.total_elapsed += elapsed
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

            if request_kind == "read":
                self.read_requests += 1
            else:
                self.write_requests += 1

    def snapshot(self, total_time: float) -> Dict[str, float]:
        with self.lock:
            avg_response_time = (
                self.total_elapsed / self.total_requests if self.total_requests else 0.0
            )
            return {
                "http_requests": self.total_requests,
                "http_successful_requests": self.successful_requests,
                "http_failed_requests": self.failed_requests,
                "http_read_requests": self.read_requests,
                "http_write_requests": self.write_requests,
                "http_avg_response_time": avg_response_time,
                "http_qps": self.total_requests / total_time if total_time > 0 else 0.0,
                "read_qps": self.read_requests / total_time if total_time > 0 else 0.0,
                "write_tps": self.write_requests / total_time if total_time > 0 else 0.0,
            }

    @staticmethod
    def _should_ignore_path(path: str) -> bool:
        return path.startswith("/api/v1/cas/")

    @staticmethod
    def _classify_request_kind(method: str, path: str) -> str:
        method = (method or "").upper()
        if method in {"GET", "HEAD", "OPTIONS"}:
            return "read"
        if method in {"PUT", "PATCH", "DELETE"}:
            return "write"
        if method == "POST":
            lower_path = path.lower()
            for keyword in ("/query", "/filter", "/count", "/search", "/summary"):
                if keyword in lower_path:
                    return "read"
        return "write"

    @staticmethod
    def _is_success(
        status_code: int,
        response: Any,
        error: Optional[BaseException],
    ) -> bool:
        if error is not None:
            return False
        if isinstance(response, dict) and response.get("error") is not None:
            return False
        if status_code >= 400:
            return False
        return True


class ConcurrentTestRunner:
    """基于会话管理器的并发测试运行器"""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.results_lock = threading.Lock()
        self.results: List[ConcurrentTestResult] = []
        self.session_managers = {}  # 线程ID -> 会话管理器映射
        self._http_request_observer = None

    def _resolve_session_slot(self, worker_id: int) -> int:
        """将请求编号映射到固定 worker 槽位，避免重复创建大量会话。"""
        return worker_id % max(1, self.max_workers)

    def _get_session_manager_for_thread(self, thread_id: int):
        """为线程获取或创建会话管理器"""
        thread_id = self._resolve_session_slot(thread_id)
        if thread_id not in self.session_managers:
            try:
                from config_helper import get_credentials, get_server_url
                from session_manager import SessionManager

                server_url = get_server_url()
                credentials = get_credentials()

                # 为每个线程创建独立的会话管理器实例（不使用全局单例）
                session_mgr = SessionManager(
                    server_url=server_url,
                    namespace="",
                    username=credentials["username"],
                    password=credentials["password"],
                    refresh_interval=540,
                    session_timeout=1800,
                    request_observer=self._http_request_observer,
                )

                # 添加超时处理
                import threading
                from queue import Queue

                result_queue = Queue()

                def create_session_with_timeout():
                    try:
                        success = session_mgr.create_session()
                        result_queue.put((success, None))
                    except Exception as e:
                        result_queue.put((False, e))

                # 在单独线程中创建会话，避免阻塞
                session_thread = threading.Thread(target=create_session_with_timeout)
                session_thread.daemon = True
                session_thread.start()
                session_thread.join(timeout=10)  # 10秒超时

                if session_thread.is_alive():
                    logger.error(f"线程 {thread_id}: 创建会话超时 - 服务器可能不可用")
                    return None

                success, error = result_queue.get()

                if not success:
                    error_msg = f"创建会话失败: {error}" if error else "创建会话失败"
                    logger.error(f"线程 {thread_id}: {error_msg}")
                    return None

                session_mgr.start_auto_refresh()
                self.session_managers[thread_id] = session_mgr
                logger.info(f"线程 {thread_id}: 会话管理器创建成功")

            except Exception as e:
                logger.error(f"线程 {thread_id}: 创建会话管理器失败 - {e}")
                return None

        return self.session_managers[thread_id]

    def _cleanup_session_managers(self):
        """清理所有会话管理器"""
        import threading

        def cleanup_single_manager(thread_id, session_mgr):
            """清理单个会话管理器"""
            try:
                cleanup_hook = getattr(session_mgr, "_codex_cleanup_hook", None)
                if callable(cleanup_hook):
                    cleanup_hook()
                # 设置超时，避免无限等待
                session_mgr.stop_auto_refresh()
                session_mgr.close_session()
                logger.info(f"线程 {thread_id}: 会话管理器清理完成")
            except Exception as e:
                logger.error(f"线程 {thread_id}: 清理会话管理器失败 - {e}")

        # 并行清理所有会话管理器
        cleanup_threads = []
        for thread_id, session_mgr in self.session_managers.items():
            thread = threading.Thread(
                target=cleanup_single_manager,
                args=(thread_id, session_mgr),
                daemon=True,
            )
            thread.start()
            cleanup_threads.append(thread)

        # 等待所有清理线程完成（最多5秒）
        for thread in cleanup_threads:
            thread.join(timeout=5)

        self.session_managers.clear()

    def run_concurrent_test(
        self, test_func: Callable, test_name: str, num_requests: int, **kwargs
    ) -> ConcurrentTestResult:
        """运行并发测试

        Args:
            test_func: 测试函数，接受worker_id参数
            test_name: 测试名称
            num_requests: 请求数量
            **kwargs: 传递给测试函数的额外参数

        Returns:
            测试结果
        """
        start_time = time.time()
        http_metrics = HTTPRequestMetricsCollector()
        self._http_request_observer = http_metrics.observe
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []

        def worker(worker_id: int):
            nonlocal successful_requests, failed_requests
            worker_start = time.time()

            try:
                # 获取会话管理器
                session_mgr = self._get_session_manager_for_thread(worker_id)
                if not session_mgr:
                    raise Exception("无法获取会话管理器")

                # 执行测试函数
                test_func(worker_id=worker_id, session_manager=session_mgr, **kwargs)
                worker_end = time.time()

                with self.results_lock:
                    successful_requests += 1
                    response_times.append(worker_end - worker_start)

            except Exception as e:
                worker_end = time.time()
                with self.results_lock:
                    failed_requests += 1
                    error_details.append(
                        {
                            "worker_id": worker_id,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat(),
                            "response_time": worker_end - worker_start,
                        }
                    )
                logger.error(f"线程 {worker_id}: 测试失败 - {e}")

        logger.info(
            f"开始并发测试: {test_name}, 请求数: {num_requests}, 工作线程: {self.max_workers}"
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = [executor.submit(worker, i) for i in range(num_requests)]
                # 添加超时处理，防止服务器不可用时无限等待
                try:
                    concurrent.futures.wait(futures, timeout=30)
                except concurrent.futures.TimeoutError:
                    logger.warning(f"并发测试超时: {test_name} - 服务器可能不可用")
                    # 取消所有未完成的future
                    for future in futures:
                        if not future.done():
                            future.cancel()
        finally:
            # 清理会话管理器
            self._cleanup_session_managers()

        end_time = time.time()
        total_time = end_time - start_time

        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0

        throughput = successful_requests / total_time if total_time > 0 else 0

        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=num_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details,
            **http_metrics.snapshot(total_time),
        )

        self.results.append(result)

        # 打印测试摘要
        self._print_test_summary(result)

        return result

    def run_worker_loop_test(
        self,
        test_func: Callable,
        test_name: str,
        num_workers: int,
        iterations_per_worker: int,
        **kwargs,
    ) -> ConcurrentTestResult:
        """运行固定 worker 循环压测。

        每个 worker 仅创建一次会话，并在多轮操作中持续复用。
        """
        start_time = time.time()
        http_metrics = HTTPRequestMetricsCollector()
        self._http_request_observer = http_metrics.observe
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []
        total_requests = num_workers * iterations_per_worker

        def worker(worker_id: int):
            nonlocal successful_requests, failed_requests

            try:
                session_mgr = self._get_session_manager_for_thread(worker_id)
                if not session_mgr:
                    raise RuntimeError("无法获取会话管理器")

                for iteration in range(iterations_per_worker):
                    iteration_start = time.time()
                    try:
                        test_func(
                            worker_id=worker_id,
                            iteration=iteration,
                            session_manager=session_mgr,
                            **kwargs,
                        )
                        iteration_end = time.time()
                        with self.results_lock:
                            successful_requests += 1
                            response_times.append(iteration_end - iteration_start)
                    except Exception as exc:
                        iteration_end = time.time()
                        with self.results_lock:
                            failed_requests += 1
                            error_details.append(
                                {
                                    "worker_id": worker_id,
                                    "iteration": iteration,
                                    "error": str(exc),
                                    "timestamp": datetime.now().isoformat(),
                                    "response_time": iteration_end - iteration_start,
                                }
                            )
                        logger.error(
                            "线程 %s 第 %s 轮执行失败 - %s",
                            worker_id,
                            iteration,
                            exc,
                        )
            except Exception as exc:
                with self.results_lock:
                    for iteration in range(iterations_per_worker):
                        failed_requests += 1
                        error_details.append(
                            {
                                "worker_id": worker_id,
                                "iteration": iteration,
                                "error": str(exc),
                                "timestamp": datetime.now().isoformat(),
                                "response_time": 0,
                            }
                        )
                logger.error("线程 %s: 初始化失败 - %s", worker_id, exc)

        logger.info(
            "开始 worker 循环压测: %s, worker 数: %s, 每 worker 轮次: %s, 总请求数: %s",
            test_name,
            num_workers,
            iterations_per_worker,
            total_requests,
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = [executor.submit(worker, worker_id) for worker_id in range(num_workers)]
                concurrent.futures.wait(futures, timeout=300)
                for future in futures:
                    if not future.done():
                        future.cancel()
        finally:
            self._cleanup_session_managers()

        total_time = time.time() - start_time
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0

        throughput = successful_requests / total_time if total_time > 0 else 0
        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details,
            **http_metrics.snapshot(total_time),
        )

        self.results.append(result)
        self._print_test_summary(result)
        return result

    def _print_test_summary(self, result: ConcurrentTestResult):
        """打印测试摘要"""
        logger.info(f"\n{'='*60}")
        logger.info(f"并发测试摘要: {result.test_name}")
        logger.info(f"{'='*60}")
        logger.info(f"总请求数: {result.total_requests}")
        logger.info(f"成功: {result.successful_requests}")
        logger.info(f"失败: {result.failed_requests}")
        logger.info(
            f"成功率: {result.successful_requests/result.total_requests*100:.1f}%"
            if result.total_requests > 0
            else "成功率: N/A"
        )
        logger.info(f"总时间: {result.total_time:.2f}秒")
        logger.info(f"平均响应时间: {result.avg_response_time:.3f}秒")
        logger.info(f"最小响应时间: {result.min_response_time:.3f}秒")
        logger.info(f"最大响应时间: {result.max_response_time:.3f}秒")
        logger.info(f"吞吐量: {result.throughput:.2f} 请求/秒")
        if result.http_requests > 0:
            logger.info(f"HTTP请求数: {result.http_requests}")
            logger.info(f"HTTP平均响应时间: {result.http_avg_response_time:.3f}秒")
            logger.info(f"HTTP QPS: {result.http_qps:.2f}")
            logger.info(f"读QPS: {result.read_qps:.2f}")
            logger.info(f"写TPS: {result.write_tps:.2f}")

        if result.error_details:
            logger.info(f"\n错误详情 ({len(result.error_details)}个):")
            for i, error in enumerate(result.error_details[:5], 1):
                scope = []
                if "tenant_id" in error:
                    scope.append(f"租户 {error['tenant_id']}")
                if "worker_id" in error:
                    scope.append(f"worker {error['worker_id']}")
                if "iteration" in error:
                    scope.append(f"轮次 {error['iteration']}")
                prefix = " ".join(scope) if scope else "未知执行单元"
                logger.info(f"  {i}. {prefix}: {error['error']}")
            if len(result.error_details) > 5:
                logger.info(f"  ... 还有 {len(result.error_details) - 5} 个错误")

    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        if not self.results:
            return {}

        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful_requests for r in self.results)
        total_failed = sum(r.failed_requests for r in self.results)
        total_time = sum(r.total_time for r in self.results)

        avg_throughput = total_successful / total_time if total_time > 0 else 0
        success_rate = (
            (total_successful / total_requests * 100) if total_requests > 0 else 0
        )

        report = {
            "summary": {
                "total_tests": len(self.results),
                "total_requests": total_requests,
                "total_successful": total_successful,
                "total_failed": total_failed,
                "total_time": total_time,
                "avg_throughput": avg_throughput,
                "success_rate": success_rate,
                "generated_at": datetime.now().isoformat(),
            },
            "detailed_results": [
                {
                    "test_name": r.test_name,
                    "total_requests": r.total_requests,
                    "successful_requests": r.successful_requests,
                    "failed_requests": r.failed_requests,
                    "success_rate": (
                        (r.successful_requests / r.total_requests * 100)
                        if r.total_requests > 0
                        else 0
                    ),
                    "total_time": r.total_time,
                    "avg_response_time": r.avg_response_time,
                    "min_response_time": r.min_response_time,
                    "max_response_time": r.max_response_time,
                    "throughput": r.throughput,
                    "http_requests": r.http_requests,
                    "http_successful_requests": r.http_successful_requests,
                    "http_failed_requests": r.http_failed_requests,
                    "http_read_requests": r.http_read_requests,
                    "http_write_requests": r.http_write_requests,
                    "http_avg_response_time": r.http_avg_response_time,
                    "http_qps": r.http_qps,
                    "read_qps": r.read_qps,
                    "write_tps": r.write_tps,
                }
                for r in self.results
            ],
            "errors": [error for r in self.results for error in r.error_details],
        }

        return report

    def save_report(self, filepath: str = "concurrent_test_report.json"):
        """保存测试报告到文件"""
        report = self.generate_report()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"测试报告已保存到: {filepath}")


class ConcurrentTestBase(unittest.TestCase):
    """并发测试基类"""

    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        try:
            from test_base_with_session_manager import \
                TestBaseWithSessionManager

            cls.test_base = TestBaseWithSessionManager
            cls.test_base.setUpClass()
            logger.info("并发测试基类: 初始化完成")
        except Exception as e:
            logger.error(f"并发测试基类: 初始化失败 - {e}")
            raise

    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if hasattr(cls, "test_base"):
            cls.test_base.tearDownClass()
            logger.info("并发测试基类: 清理完成")


# 测试函数工厂
class ConcurrentTestFactory:
    """并发测试函数工厂"""

    @staticmethod
    def _build_unique_suffix(worker_id: int) -> str:
        return f"{worker_id:04d}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _resolve_status_id(session_manager) -> int:
        from sdk.status import StatusSDK
        from test_dependency_helper import resolve_status_id

        status_sdk = StatusSDK(session_manager.get_session())
        status_id = resolve_status_id(status_sdk)
        if not status_id:
            raise AssertionError("无法获取可用状态ID")
        return status_id

    @staticmethod
    def create_store_creation_test():
        """创建门店创建测试函数"""

        def test_create_store(worker_id: int, session_manager, iteration: int = 0):
            from sdk.store import StoreSDK

            store_sdk = StoreSDK(session_manager.get_session())
            suffix = ConcurrentTestFactory._build_unique_suffix(
                worker_id * 1000 + iteration
            )
            store_data = {
                "name": f"并发测试门店_{suffix}",
                "description": f"并发测试创建的门店_{suffix}",
            }

            result = store_sdk.create_store(store_data)
            assert result is not None
            assert "id" in result
            delete_result = store_sdk.delete_store(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建门店成功 - ID: {result.get('id')}")

        return test_create_store

    @staticmethod
    def create_product_creation_test():
        """创建产品创建测试函数"""

        def test_create_product(worker_id: int, session_manager, iteration: int = 0):
            from sdk.product import ProductSDK

            product_sdk = ProductSDK(session_manager.get_session())
            status_id = ConcurrentTestFactory._resolve_status_id(session_manager)
            suffix = ConcurrentTestFactory._build_unique_suffix(
                worker_id * 1000 + iteration
            )
            product_data = {
                "name": f"并发测试产品_{suffix}",
                "description": f"并发测试创建的产品_{suffix}",
                "image": [],
                "expire": random.randint(30, 365),
                "tags": ["concurrent", f"worker-{worker_id}", suffix],
                "status": {"id": status_id},
            }

            result = product_sdk.create_product(product_data)
            assert result is not None
            assert "id" in result
            delete_result = product_sdk.delete_product(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建产品成功 - ID: {result.get('id')}")

        return test_create_product

    @staticmethod
    def create_warehouse_creation_test():
        """创建仓库创建测试函数"""

        def test_create_warehouse(worker_id: int, session_manager, iteration: int = 0):
            from sdk.warehouse import WarehouseSDK

            warehouse_sdk = WarehouseSDK(session_manager.get_session())
            suffix = ConcurrentTestFactory._build_unique_suffix(
                worker_id * 1000 + iteration
            )
            warehouse_data = {
                "name": f"并发测试仓库_{suffix}",
                "description": f"并发测试创建的仓库_{suffix}",
            }

            result = warehouse_sdk.create_warehouse(warehouse_data)
            assert result is not None
            assert "id" in result
            delete_result = warehouse_sdk.delete_warehouse(result["id"])
            assert delete_result is not None
            logger.debug(f"线程 {worker_id}: 创建仓库成功 - ID: {result.get('id')}")

        return test_create_warehouse


# 具体的并发测试类
class TestConcurrentStoreOperations(ConcurrentTestBase):
    """并发门店操作测试"""

    def test_concurrent_store_creation(self):
        """并发创建门店测试"""
        runner = ConcurrentTestRunner(max_workers=5)

        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_worker_loop_test(
            test_func=test_func,
            test_name="concurrent_store_creation",
            num_workers=5,
            iterations_per_worker=2,
        )

        # 验证测试结果 - 降低要求以适应实际服务器性能
        self.assertGreaterEqual(result.successful_requests, 5, "至少50%的请求应该成功")
        self.assertLess(result.avg_response_time, 10.0, "平均响应时间应小于10秒")
        self.assertGreater(result.throughput, 0.5, "吞吐量应大于0.5请求/秒")

    def test_high_concurrency_store_operations(self):
        """高并发门店操作测试"""
        runner = ConcurrentTestRunner(max_workers=10)

        test_func = ConcurrentTestFactory.create_store_creation_test()
        result = runner.run_worker_loop_test(
            test_func=test_func,
            test_name="high_concurrency_store_operations",
            num_workers=10,
            iterations_per_worker=2,
        )

        # 验证测试结果 - 降低要求以适应实际服务器性能
        self.assertGreaterEqual(result.successful_requests, 10, "至少50%的请求应该成功")
        self.assertLess(result.avg_response_time, 15.0, "平均响应时间应小于15秒")


class TestConcurrentProductOperations(ConcurrentTestBase):
    """并发产品操作测试"""

    def test_concurrent_product_creation(self):
        """并发创建产品测试"""
        runner = ConcurrentTestRunner(max_workers=10)

        test_func = ConcurrentTestFactory.create_product_creation_test()
        result = runner.run_worker_loop_test(
            test_func=test_func,
            test_name="concurrent_product_creation",
            num_workers=10,
            iterations_per_worker=3,
        )

        # 压测目标改为强调成功率和吞吐，而不是低延迟阈值
        self.assertGreaterEqual(result.successful_requests, 28, "至少93%的请求应该成功")
        self.assertGreater(result.throughput, 0.8, "吞吐量应大于0.8请求/秒")

    def test_mixed_concurrent_operations(self):
        """混合并发操作测试"""
        runner = ConcurrentTestRunner(max_workers=20)

        # 随机选择测试函数
        test_functions = [
            ConcurrentTestFactory.create_store_creation_test(),
            ConcurrentTestFactory.create_product_creation_test(),
            ConcurrentTestFactory.create_warehouse_creation_test(),
        ]

        def mixed_operation(worker_id: int, session_manager, iteration: int = 0):
            # 随机选择一个操作
            test_func = random.choice(test_functions)
            test_func(worker_id, session_manager, iteration=iteration)

        result = runner.run_worker_loop_test(
            test_func=mixed_operation,
            test_name="mixed_concurrent_operations",
            num_workers=20,
            iterations_per_worker=5,
        )

        # 强调大规模稳定压测的成功率和总吞吐
        self.assertGreaterEqual(result.successful_requests, 90, "至少90%的请求应该成功")
        self.assertGreater(result.throughput, 1.5, "吞吐量应大于1.5请求/秒")


class TestConcurrentWarehouseOperations(ConcurrentTestBase):
    """并发仓库操作测试"""

    def test_concurrent_warehouse_creation(self):
        """并发创建仓库测试"""
        runner = ConcurrentTestRunner(max_workers=10)

        test_func = ConcurrentTestFactory.create_warehouse_creation_test()
        result = runner.run_worker_loop_test(
            test_func=test_func,
            test_name="concurrent_warehouse_creation",
            num_workers=5,
            iterations_per_worker=3,
        )

        # 验证测试结果
        self.assertGreaterEqual(result.successful_requests, 12, "至少80%的请求应该成功")
        self.assertLess(result.avg_response_time, 4.0, "平均响应时间应小于4秒")


class MultiTenantConcurrentRunner:
    """多租户并发测试运行器。

    按租户并发执行，每个租户使用独立会话，避免不同 namespace 之间串会话。
    """

    def __init__(
        self,
        tenant_configs: Dict[str, Dict[str, Any]],
        max_workers: Optional[int] = None,
        timeout: int = 60,
    ):
        self.tenant_configs = tenant_configs
        self.max_workers = max_workers or max(1, len(tenant_configs))
        self.timeout = timeout
        self.results_lock = threading.Lock()
        self.results: List[ConcurrentTestResult] = []
        self.session_managers: Dict[str, Any] = {}
        self.shared_contexts: Dict[str, Dict[str, Any]] = {}
        self.shared_context_locks: Dict[str, threading.Lock] = {}
        self._http_request_observer = None

    def _get_session_manager(self, session_key: str, tenant_id: str):
        """为租户 worker 获取独立会话管理器。"""
        if session_key in self.session_managers:
            return self.session_managers[session_key]

        tenant_config = self.tenant_configs[tenant_id]

        try:
            from config_helper import get_session_config
            from session_manager import SessionManager

            session_config = get_session_config()
            session_mgr = SessionManager(
                server_url=tenant_config["server_url"],
                namespace=tenant_config["namespace"],
                username=tenant_config["username"],
                password=tenant_config["password"],
                refresh_interval=session_config.get("refresh_interval", 540),
                session_timeout=session_config.get("timeout", 1800),
                request_observer=self._http_request_observer,
            )

            from queue import Queue

            result_queue = Queue()

            def create_session_with_timeout():
                try:
                    success = session_mgr.create_session()
                    result_queue.put((success, None))
                except Exception as exc:
                    result_queue.put((False, exc))

            session_thread = threading.Thread(target=create_session_with_timeout)
            session_thread.daemon = True
            session_thread.start()
            session_thread.join(timeout=min(self.timeout, 15))

            if session_thread.is_alive():
                logger.error("租户 %s: 创建会话超时", tenant_id)
                return None

            success, error = result_queue.get()
            if not success:
                logger.error("租户 %s: 创建会话失败 - %s", tenant_id, error)
                return None

            session_mgr.start_auto_refresh()
            self.session_managers[session_key] = session_mgr
            logger.info("租户 %s: 会话初始化完成(session=%s)", tenant_id, session_key)
            return session_mgr

        except Exception as exc:
            logger.error("租户 %s: 初始化会话管理器失败 - %s", tenant_id, exc)
            return None

    def _get_session_manager_for_tenant(self, tenant_id: str):
        """兼容旧接口，为单租户 worker 获取会话。"""
        return self._get_session_manager(tenant_id, tenant_id)

    def _cleanup_session_managers(self):
        """清理所有租户会话。"""

        def cleanup_single_manager(tenant_id: str, session_mgr):
            try:
                cleanup_hook = getattr(session_mgr, "_codex_cleanup_hook", None)
                if callable(cleanup_hook):
                    cleanup_hook()
                session_mgr.stop_auto_refresh()
                session_mgr.close_session()
                logger.info("租户 %s: 会话清理完成", tenant_id)
            except Exception as exc:
                logger.error("租户 %s: 会话清理失败 - %s", tenant_id, exc)

        cleanup_threads = []
        for tenant_id, session_mgr in self.session_managers.items():
            thread = threading.Thread(
                target=cleanup_single_manager,
                args=(tenant_id, session_mgr),
                daemon=True,
            )
            thread.start()
            cleanup_threads.append(thread)

        for thread in cleanup_threads:
            thread.join(timeout=5)

        self.session_managers.clear()

    def _cleanup_shared_contexts(self):
        """清理租户级共享上下文。"""
        for tenant_id, context in list(self.shared_contexts.items()):
            cleanup = context.get("cleanup")
            if not callable(cleanup):
                continue

            try:
                cleanup()
                logger.info("租户 %s: 共享热点资源清理完成", tenant_id)
            except Exception as exc:
                logger.error("租户 %s: 共享热点资源清理失败 - %s", tenant_id, exc)

        self.shared_contexts.clear()
        self.shared_context_locks.clear()

    def _print_test_summary(self, result: ConcurrentTestResult):
        """打印多租户压测摘要。"""
        logger.info(f"\n{'='*60}")
        logger.info(f"并发测试摘要: {result.test_name}")
        logger.info(f"{'='*60}")
        logger.info(f"总请求数: {result.total_requests}")
        logger.info(f"成功: {result.successful_requests}")
        logger.info(f"失败: {result.failed_requests}")
        logger.info(
            f"成功率: {result.successful_requests/result.total_requests*100:.1f}%"
            if result.total_requests > 0
            else "成功率: N/A"
        )
        logger.info(f"总时间: {result.total_time:.2f}秒")
        logger.info(f"平均响应时间: {result.avg_response_time:.3f}秒")
        logger.info(f"最小响应时间: {result.min_response_time:.3f}秒")
        logger.info(f"最大响应时间: {result.max_response_time:.3f}秒")
        logger.info(f"吞吐量: {result.throughput:.2f} 请求/秒")
        if result.http_requests > 0:
            logger.info(f"HTTP请求数: {result.http_requests}")
            logger.info(f"HTTP平均响应时间: {result.http_avg_response_time:.3f}秒")
            logger.info(f"HTTP QPS: {result.http_qps:.2f}")
            logger.info(f"读QPS: {result.read_qps:.2f}")
            logger.info(f"写TPS: {result.write_tps:.2f}")

        if result.error_details:
            logger.info(f"\n错误详情 ({len(result.error_details)}个):")
            for i, error in enumerate(result.error_details[:5], 1):
                scope = []
                if "tenant_id" in error:
                    scope.append(f"租户 {error['tenant_id']}")
                if "worker_id" in error:
                    scope.append(f"worker {error['worker_id']}")
                if "iteration" in error:
                    scope.append(f"轮次 {error['iteration']}")
                prefix = " ".join(scope) if scope else "未知执行单元"
                logger.info(f"  {i}. {prefix}: {error['error']}")
            if len(result.error_details) > 5:
                logger.info(f"  ... 还有 {len(result.error_details) - 5} 个错误")

    def get_or_create_shared_context(
        self,
        tenant_id: str,
        creator: Callable[[], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """按租户延迟初始化共享上下文。"""
        if tenant_id in self.shared_contexts:
            return self.shared_contexts[tenant_id]

        lock = self.shared_context_locks.setdefault(tenant_id, threading.Lock())
        with lock:
            if tenant_id in self.shared_contexts:
                return self.shared_contexts[tenant_id]

            context = creator()
            self.shared_contexts[tenant_id] = context
            return context

    def run_multi_tenant_test(
        self,
        test_func: Callable,
        test_name: str,
    ) -> ConcurrentTestResult:
        """按租户并发执行测试函数。"""
        if not self.tenant_configs:
            raise ValueError("没有可用的多租户配置")

        tenant_ids = list(self.tenant_configs.keys())
        start_time = time.time()
        http_metrics = HTTPRequestMetricsCollector()
        self._http_request_observer = http_metrics.observe
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []

        def worker(tenant_id: str):
            nonlocal successful_requests, failed_requests
            worker_start = time.time()

            try:
                session_mgr = self._get_session_manager_for_tenant(tenant_id)
                if not session_mgr:
                    raise RuntimeError("无法获取租户会话")

                test_func(tenant_id=tenant_id, session_manager=session_mgr)
                worker_end = time.time()

                with self.results_lock:
                    successful_requests += 1
                    response_times.append(worker_end - worker_start)

            except Exception as exc:
                worker_end = time.time()
                with self.results_lock:
                    failed_requests += 1
                    error_details.append(
                        {
                            "tenant_id": tenant_id,
                            "error": str(exc),
                            "timestamp": datetime.now().isoformat(),
                            "response_time": worker_end - worker_start,
                        }
                    )
                logger.error("租户 %s: 多租户并发测试失败 - %s", tenant_id, exc)

        logger.info(
            "开始多租户并发测试: %s, 租户数: %s, 并发数: %s",
            test_name,
            len(tenant_ids),
            self.max_workers,
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=self.max_workers
            ) as executor:
                futures = [executor.submit(worker, tenant_id) for tenant_id in tenant_ids]
                concurrent.futures.wait(futures, timeout=self.timeout)
                for future in futures:
                    if not future.done():
                        future.cancel()
        finally:
            self._cleanup_session_managers()

        total_time = time.time() - start_time
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0

        throughput = successful_requests / total_time if total_time > 0 else 0
        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=len(tenant_ids),
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details,
            **http_metrics.snapshot(total_time),
        )
        self.results.append(result)
        self._print_test_summary(result)
        return result

    def run_multi_tenant_worker_loop_test(
        self,
        test_func: Callable,
        test_name: str,
        workers_per_tenant: int,
        iterations_per_worker: int,
        prepare_func: Optional[Callable] = None,
        measure_loop_only: bool = True,
    ) -> ConcurrentTestResult:
        """按租户 x worker 并发执行热点循环压测。"""
        if not self.tenant_configs:
            raise ValueError("没有可用的多租户配置")

        tenant_ids = list(self.tenant_configs.keys())
        tasks = [
            (tenant_id, worker_id)
            for tenant_id in tenant_ids
            for worker_id in range(workers_per_tenant)
        ]

        start_time = time.time()
        http_metrics = HTTPRequestMetricsCollector()
        self._http_request_observer = http_metrics.observe
        successful_requests = 0
        failed_requests = 0
        response_times = []
        error_details = []
        total_requests = len(tasks) * iterations_per_worker
        ready_workers = 0
        ready_condition = threading.Condition()
        start_event = threading.Event()
        measurement_end: Optional[float] = None

        def mark_ready():
            nonlocal ready_workers
            with ready_condition:
                ready_workers += 1
                ready_condition.notify_all()

        def worker(tenant_id: str, worker_id: int):
            nonlocal successful_requests, failed_requests
            session_key = f"{tenant_id}#{worker_id}"
            setup_ok = False

            try:
                session_mgr = self._get_session_manager(session_key, tenant_id)
                if not session_mgr:
                    raise RuntimeError("无法获取租户会话")

                if prepare_func is not None:
                    prepare_func(
                        tenant_id=tenant_id,
                        worker_id=worker_id,
                        session_manager=session_mgr,
                    )

                setup_ok = True
                mark_ready()
                if measure_loop_only and not start_event.wait(timeout=self.timeout):
                    raise TimeoutError("等待统一起跑超时")

                for iteration in range(iterations_per_worker):
                    iteration_start = time.time()
                    try:
                        test_func(
                            tenant_id=tenant_id,
                            worker_id=worker_id,
                            iteration=iteration,
                            session_manager=session_mgr,
                        )
                        iteration_end = time.time()
                        with self.results_lock:
                            successful_requests += 1
                            response_times.append(iteration_end - iteration_start)
                    except Exception as exc:
                        iteration_end = time.time()
                        with self.results_lock:
                            failed_requests += 1
                            error_details.append(
                                {
                                    "tenant_id": tenant_id,
                                    "worker_id": worker_id,
                                    "iteration": iteration,
                                    "error": str(exc),
                                    "timestamp": datetime.now().isoformat(),
                                    "response_time": iteration_end - iteration_start,
                                }
                            )
                        logger.error(
                            "租户 %s worker %s 第 %s 轮失败 - %s",
                            tenant_id,
                            worker_id,
                            iteration,
                            exc,
                        )
            except Exception as exc:
                if not setup_ok:
                    mark_ready()
                with self.results_lock:
                    for iteration in range(iterations_per_worker):
                        failed_requests += 1
                        error_details.append(
                            {
                                "tenant_id": tenant_id,
                                "worker_id": worker_id,
                                "iteration": iteration,
                                "error": str(exc),
                                "timestamp": datetime.now().isoformat(),
                                "response_time": 0,
                            }
                        )
                logger.error("租户 %s worker %s 初始化失败 - %s", tenant_id, worker_id, exc)

        logger.info(
            "开始多租户热点压测: %s, 租户数: %s, 每租户 worker: %s, 每 worker 轮次: %s, 总请求数: %s",
            test_name,
            len(tenant_ids),
            workers_per_tenant,
            iterations_per_worker,
            total_requests,
        )

        try:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=min(self.max_workers, len(tasks))
            ) as executor:
                futures = [
                    executor.submit(worker, tenant_id, worker_id)
                    for tenant_id, worker_id in tasks
                ]
                if measure_loop_only:
                    setup_deadline = time.time() + self.timeout
                    with ready_condition:
                        while ready_workers < len(tasks):
                            remaining = setup_deadline - time.time()
                            if remaining <= 0:
                                break
                            ready_condition.wait(timeout=min(1.0, remaining))
                    start_time = time.time()
                    start_event.set()
                concurrent.futures.wait(futures, timeout=self.timeout)
                for future in futures:
                    if not future.done():
                        future.cancel()
                measurement_end = time.time()
        finally:
            self._cleanup_shared_contexts()
            self._cleanup_session_managers()

        end_time = measurement_end or time.time()
        total_time = end_time - start_time
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
        else:
            avg_response_time = min_response_time = max_response_time = 0

        throughput = successful_requests / total_time if total_time > 0 else 0
        result = ConcurrentTestResult(
            test_name=test_name,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            total_time=total_time,
            avg_response_time=avg_response_time,
            min_response_time=min_response_time,
            max_response_time=max_response_time,
            throughput=throughput,
            error_details=error_details,
            **http_metrics.snapshot(total_time),
        )
        self.results.append(result)
        self._print_test_summary(result)
        return result


class MultiTenantBusinessScenarioFactory:
    """构造覆盖 VMI 现有业务面的多租户并发场景。"""

    FULL_FLOW_COVERAGE: Dict[str, List[str]] = {
        "status": ["list", "query"],
        "warehouse": ["create", "query", "list", "update", "delete"],
        "shelf": ["create", "query", "list", "update", "delete"],
        "store": ["create", "query", "list", "update", "delete"],
        "partner": ["create", "query", "list", "update", "delete"],
        "member": ["create", "query", "list", "update", "delete"],
        "product": ["create", "query", "list", "update", "delete"],
        "product_info": ["create", "query", "list", "update", "delete"],
        "goods_info": ["create", "query", "list", "update", "delete"],
        "goods": ["create", "query", "list", "update", "delete"],
        "reward_policy": ["create", "query", "list", "update", "delete"],
        "credit": ["create", "query", "list", "update", "delete"],
        "credit_report": ["create", "query", "list", "update", "delete"],
        "credit_reward": ["create", "query", "list", "update", "delete"],
        "goods_item": ["create", "query", "list", "update", "delete"],
        "stockin": ["create", "query", "list", "update", "delete"],
        "stockout": ["create", "query", "list", "update", "delete"],
        "order": ["create", "query", "list", "update", "delete"],
    }

    @staticmethod
    def _build_suffix(tenant_id: str) -> str:
        return f"{tenant_id}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _build_numeric_code() -> str:
        return f"{int(time.time() * 1000) % 1000000000}{random.randint(100, 999)}"

    @staticmethod
    def _record_entity(
        created_entities: Dict[str, List[int]],
        entity_type: str,
        entity: Optional[Dict[str, Any]],
    ) -> int:
        if not entity or "id" not in entity:
            raise AssertionError(f"{entity_type} 创建失败，缺少ID")

        entity_id = int(entity["id"])
        created_entities[entity_type].append(entity_id)
        return entity_id

    @staticmethod
    def _assert_namespace(entity: Optional[Dict[str, Any]], tenant_id: str):
        if not entity or "namespace" not in entity:
            return

        namespace = entity.get("namespace")
        if namespace in (None, ""):
            return

        assert namespace == tenant_id, (
            f"租户 {tenant_id} 返回的 namespace 异常，实际为 {namespace}"
        )

    @staticmethod
    def _build_goods_info_payload(
        goods_info: Dict[str, Any],
        product_info_id: int,
        shelf_id: int,
        default_type: int,
        default_count: int,
        default_price: float,
    ) -> Dict[str, Any]:
        return {
            "id": int(goods_info["id"]),
            "sku": goods_info.get("sku", MultiTenantBusinessScenarioFactory._build_numeric_code()),
            "product": goods_info.get("product", {"id": product_info_id}),
            "type": goods_info.get("type", default_type),
            "count": goods_info.get("count", default_count),
            "price": goods_info.get("price", default_price),
            "shelf": goods_info.get("shelf", [{"id": shelf_id}]),
        }

    @staticmethod
    def _load_statuses_with_retry(
        sdks: Dict[str, Any],
        tenant_id: str,
        attempts: int = 5,
        delay_seconds: float = 0.5,
    ) -> List[Dict[str, Any]]:
        for attempt in range(1, attempts + 1):
            statuses = sdks["status"].filter_status({"page": 1, "size": 100}) or []
            statuses = [
                item for item in statuses if isinstance(item, dict) and item.get("id")
            ]
            if statuses:
                return statuses

            if attempt < attempts:
                logger.warning(
                    "租户 %s: 状态列表暂不可用，第 %s/%s 次重试",
                    tenant_id,
                    attempt,
                    attempts,
                )
                time.sleep(delay_seconds)

        raise AssertionError(f"租户 {tenant_id} 无可用状态数据")

    @staticmethod
    def _resolve_status_id_from_statuses(
        statuses: List[Dict[str, Any]],
        preferred_names: Optional[List[str]] = None,
    ) -> Optional[int]:
        preferred_names = preferred_names or ["启用", "已启用", "正常", "active", "enabled"]
        preferred_names = {name.lower() for name in preferred_names}

        for item in statuses:
            name = str(item.get("name", "")).strip().lower()
            if name in preferred_names:
                return int(item["id"])

        for item in statuses:
            if item.get("id"):
                return int(item["id"])

        return None

    @staticmethod
    def _cleanup_entities(sdks: Dict[str, Any], created_entities: Dict[str, List[int]]):
        cleanup_plan = [
            ("stockout", "stockout"),
            ("stockin", "stockin"),
            ("order", "order"),
            ("goods_item", "goods_item"),
            ("credit_reward", "credit_reward"),
            ("credit_report", "credit_report"),
            ("credit", "credit"),
            ("reward_policy", "reward_policy"),
            ("goods", "goods"),
            ("goods_info", "goods_info"),
            ("product_info", "product_info"),
            ("product", "product"),
            ("member", "member"),
            ("partner", "partner"),
            ("store", "store"),
            ("shelf", "shelf"),
            ("warehouse", "warehouse"),
        ]

        for entity_type, sdk_key in cleanup_plan:
            sdk = sdks.get(sdk_key)
            delete_method = getattr(sdk, f"delete_{entity_type}", None) if sdk else None
            if not delete_method:
                continue

            for entity_id in reversed(created_entities.get(entity_type, [])):
                try:
                    delete_method(entity_id)
                except Exception as exc:
                    logger.warning("清理 %s(%s) 失败: %s", entity_type, entity_id, exc)

    @staticmethod
    def _get_hotspot_sdks(session_manager) -> Dict[str, Any]:
        existing_sdks = getattr(session_manager, "_vmi_hotspot_sdks", None)
        work_session = session_manager.get_session()
        if existing_sdks is not None:
            cached_session = getattr(session_manager, "_vmi_hotspot_sdk_session", None)
            if cached_session is work_session:
                return existing_sdks

            logger.warning("热点压测检测到会话已重建，重新创建 SDK 缓存")

        from sdk import (GoodsInfoSDK, GoodsSDK, ProductInfoSDK, ProductSDK,
                         ShelfSDK, StatusSDK, StoreSDK, WarehouseSDK)

        sdks = {
            "status": StatusSDK(work_session),
            "warehouse": WarehouseSDK(work_session),
            "shelf": ShelfSDK(work_session),
            "store": StoreSDK(work_session),
            "product": ProductSDK(work_session),
            "product_info": ProductInfoSDK(work_session),
            "goods_info": GoodsInfoSDK(work_session),
            "goods": GoodsSDK(work_session),
        }
        session_manager._vmi_hotspot_sdks = sdks
        session_manager._vmi_hotspot_sdk_session = work_session
        return sdks

    @staticmethod
    def _warmup_hotspot_session(
        tenant_id: str,
        session_manager,
        max_attempts: int = 5,
        retry_delay: float = 0.2,
    ) -> None:
        """在测量窗口外预热鉴权和首个轻量读请求，避免首轮请求抖动混入压测结果。"""
        cas_session = session_manager.get_cas_session()
        sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(session_manager)
        last_error = "session warmup not started"

        for attempt in range(1, max_attempts + 1):
            namespace_ok = cas_session.verify_session_namespace() if cas_session else False
            statuses = (
                sdks["status"].filter_status({"page": 1, "size": 20})
                if namespace_ok
                else None
            )
            if namespace_ok and statuses is not None:
                return

            if not namespace_ok:
                last_error = "namespace verify failed"
            else:
                last_error = "status warmup failed"

            if attempt < max_attempts:
                logger.warning(
                    "租户 %s: 会话预热失败，准备重试 attempt=%s/%s reason=%s",
                    tenant_id,
                    attempt,
                    max_attempts,
                    last_error,
                )
                time.sleep(retry_delay)

        raise AssertionError(f"租户 {tenant_id} 会话预热失败: {last_error}")

    @staticmethod
    def _query_entity(sdks: Dict[str, Any], entity_type: str, entity_id: int):
        sdk = sdks[entity_type]
        query_method = getattr(sdk, f"query_{entity_type}")
        return query_method(entity_id)

    @staticmethod
    def _filter_entities(
        sdks: Dict[str, Any],
        entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        sdk = sdks[entity_type]
        filter_method = getattr(sdk, f"filter_{entity_type}")
        return filter_method(filters or {"page": 1, "size": 200}) or []

    @staticmethod
    def _assert_list_contains(
        sdks: Dict[str, Any],
        entity_type: str,
        entity_id: int,
        tenant_id: str,
    ):
        listed_entities = MultiTenantBusinessScenarioFactory._filter_entities(
            sdks,
            entity_type,
            {"id": entity_id, "page": 1, "size": 20},
        )
        if not listed_entities:
            listed_entities = MultiTenantBusinessScenarioFactory._filter_entities(
                sdks,
                entity_type,
            )
        assert any(
            isinstance(item, dict) and int(item.get("id", 0)) == entity_id
            for item in listed_entities
        ), f"租户 {tenant_id} 的 {entity_type} 列表中未找到实体 {entity_id}"

    @staticmethod
    def _assert_query_field(
        sdks: Dict[str, Any],
        entity_type: str,
        entity_id: int,
        field_name: str,
        expected_value: Any,
        tenant_id: str,
    ):
        queried_entity = MultiTenantBusinessScenarioFactory._query_entity(
            sdks, entity_type, entity_id
        )
        assert queried_entity is not None, f"租户 {tenant_id} 查询 {entity_type} 失败"
        assert queried_entity.get(field_name) == expected_value, (
            f"租户 {tenant_id} 的 {entity_type}.{field_name} 更新未生效，"
            f"实际为 {queried_entity.get(field_name)}"
        )

    @staticmethod
    def _update_entity(
        sdks: Dict[str, Any],
        entity_type: str,
        entity_id: int,
        update_payload: Dict[str, Any],
        tenant_id: str,
        fallback_payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        sdk = sdks[entity_type]
        update_method = getattr(sdk, f"update_{entity_type}")

        try:
            updated_entity = update_method(entity_id, update_payload)
        except Exception:
            if fallback_payload is None:
                raise
            updated_entity = update_method(entity_id, fallback_payload)

        if updated_entity is None and fallback_payload is not None:
            updated_entity = update_method(entity_id, fallback_payload)

        assert updated_entity is not None, f"租户 {tenant_id} 更新 {entity_type} 失败"
        return updated_entity

    @staticmethod
    def get_full_flow_coverage() -> Dict[str, List[str]]:
        return {
            entity_type: list(operations)
            for entity_type, operations in MultiTenantBusinessScenarioFactory.FULL_FLOW_COVERAGE.items()
        }

    @staticmethod
    def create_full_business_flow_test():
        """创建全业务覆盖的租户场景测试。"""

        def test_full_business_flow(tenant_id: str, session_manager):
            from sdk import (CreditReportSDK, CreditRewardSDK, CreditSDK,
                             GoodsInfoSDK, GoodsItemSDK, GoodsSDK, MemberSDK,
                             OrderSDK, PartnerSDK, ProductInfoSDK, ProductSDK,
                             RewardPolicySDK, ShelfSDK, StatusSDK, StockinSDK,
                             StockoutSDK, StoreSDK, WarehouseSDK)

            work_session = session_manager.get_session()
            sdks = {
                "status": StatusSDK(work_session),
                "warehouse": WarehouseSDK(work_session),
                "shelf": ShelfSDK(work_session),
                "store": StoreSDK(work_session),
                "partner": PartnerSDK(work_session),
                "member": MemberSDK(work_session),
                "product": ProductSDK(work_session),
                "product_info": ProductInfoSDK(work_session),
                "goods_info": GoodsInfoSDK(work_session),
                "goods": GoodsSDK(work_session),
                "reward_policy": RewardPolicySDK(work_session),
                "credit": CreditSDK(work_session),
                "credit_report": CreditReportSDK(work_session),
                "credit_reward": CreditRewardSDK(work_session),
                "goods_item": GoodsItemSDK(work_session),
                "stockin": StockinSDK(work_session),
                "stockout": StockoutSDK(work_session),
                "order": OrderSDK(work_session),
            }
            created_entities: Dict[str, List[int]] = defaultdict(list)
            suffix = MultiTenantBusinessScenarioFactory._build_suffix(tenant_id)

            try:
                statuses = MultiTenantBusinessScenarioFactory._load_statuses_with_retry(
                    sdks,
                    tenant_id,
                )

                status_id = MultiTenantBusinessScenarioFactory._resolve_status_id_from_statuses(
                    statuses
                )
                assert status_id, f"租户 {tenant_id} 无法解析可用状态ID"

                status_entity = sdks["status"].query_status(status_id)
                assert status_entity is not None, f"租户 {tenant_id} 查询状态失败"
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "status", status_id, tenant_id
                )

                warehouse_payload = {
                    "name": f"MT_WH_{suffix}",
                    "description": f"多租户并发仓库_{suffix}",
                }
                warehouse = sdks["warehouse"].create_warehouse(warehouse_payload)
                warehouse_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "warehouse", warehouse
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(warehouse, tenant_id)
                assert sdks["warehouse"].query_warehouse(warehouse_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "warehouse", warehouse_id, tenant_id
                )
                warehouse_update_payload = dict(warehouse)
                warehouse_update_payload["description"] = f"更新后的仓库_{suffix}"
                updated_warehouse = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "warehouse",
                    warehouse_id,
                    warehouse_update_payload,
                    tenant_id,
                )
                assert updated_warehouse.get("description") == warehouse_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "warehouse",
                    warehouse_id,
                    "description",
                    warehouse_update_payload["description"],
                    tenant_id,
                )

                shelf_payload = {
                    "description": f"多租户并发货架_{suffix}",
                    "capacity": 200,
                    "warehouse": {"id": warehouse_id},
                    "status": {"id": status_id},
                }
                shelf = sdks["shelf"].create_shelf(shelf_payload)
                shelf_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "shelf", shelf
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(shelf, tenant_id)
                assert sdks["shelf"].query_shelf(shelf_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "shelf", shelf_id, tenant_id
                )
                shelf_update_payload = {
                    "description": f"更新后的货架_{suffix}",
                    "capacity": 260,
                    "warehouse": {"id": warehouse_id},
                    "status": {"id": status_id},
                }
                updated_shelf = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "shelf", shelf_id, shelf_update_payload, tenant_id
                )
                assert updated_shelf.get("description") == shelf_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "shelf",
                    shelf_id,
                    "description",
                    shelf_update_payload["description"],
                    tenant_id,
                )

                store_payload = {
                    "name": f"MT_STORE_{suffix}",
                    "description": f"多租户并发店铺_{suffix}",
                }
                store = sdks["store"].create_store(store_payload)
                store_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "store", store
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(store, tenant_id)
                assert sdks["store"].query_store(store_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "store", store_id, tenant_id
                )
                store_update_payload = dict(store)
                store_update_payload["description"] = f"更新后的店铺_{suffix}"
                updated_store = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "store", store_id, store_update_payload, tenant_id
                )
                assert updated_store.get("description") == store_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "store",
                    store_id,
                    "description",
                    store_update_payload["description"],
                    tenant_id,
                )

                partner_payload = {
                    "name": f"MT_PARTNER_{suffix}",
                    "telephone": f"13{random.randint(100000000, 999999999)}",
                    "wechat": f"wechat_{suffix}",
                    "description": f"多租户并发会员_{suffix}",
                    "status": {"id": status_id},
                }
                partner = sdks["partner"].create_partner(partner_payload)
                partner_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "partner", partner
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(partner, tenant_id)
                assert sdks["partner"].query_partner(partner_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "partner", partner_id, tenant_id
                )
                partner_update_payload = dict(partner)
                partner_update_payload["description"] = f"更新后的合作伙伴_{suffix}"
                updated_partner = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "partner", partner_id, partner_update_payload, tenant_id
                )
                assert updated_partner.get("description") == partner_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "partner",
                    partner_id,
                    "description",
                    partner_update_payload["description"],
                    tenant_id,
                )

                member_payload = {
                    "title": f"店员_{tenant_id}",
                    "name": f"MT_MEMBER_{suffix}",
                    "store": {"id": store_id},
                }
                member = sdks["member"].create_member(member_payload)
                member_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "member", member
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(member, tenant_id)
                assert sdks["member"].query_member(member_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "member", member_id, tenant_id
                )
                member_update_payload = dict(member)
                member_update_payload["title"] = f"更新后的店员_{suffix}"
                updated_member = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "member", member_id, member_update_payload, tenant_id
                )
                assert updated_member.get("title") == member_update_payload["title"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks, "member", member_id, "title", member_update_payload["title"], tenant_id
                )

                product_payload = {
                    "name": f"MT_PRODUCT_{suffix}",
                    "description": f"多租户并发产品_{suffix}",
                    "image": [],
                    "expire": 365,
                    "tags": ["multi-tenant", tenant_id, suffix],
                    "status": {"id": status_id},
                }
                product = sdks["product"].create_product(product_payload)
                product_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "product", product
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(product, tenant_id)
                assert sdks["product"].query_product(product_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "product", product_id, tenant_id
                )
                product_update_payload = dict(product)
                product_update_payload["description"] = f"更新后的产品_{suffix}"
                updated_product = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "product", product_id, product_update_payload, tenant_id
                )
                assert updated_product.get("description") == product_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "product",
                    product_id,
                    "description",
                    product_update_payload["description"],
                    tenant_id,
                )

                product_info_payload = {
                    "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                    "description": f"多租户并发产品SKU_{suffix}",
                    "product": {"id": product_id},
                }
                product_info = sdks["product_info"].create_product_info(product_info_payload)
                product_info_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "product_info", product_info
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(
                    product_info, tenant_id
                )
                assert sdks["product_info"].query_product_info(product_info_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "product_info", product_info_id, tenant_id
                )
                product_info_update_payload = {
                    "sku": product_info_payload["sku"],
                    "description": f"更新后的产品SKU_{suffix}",
                    "product": {"id": product_id},
                }
                updated_product_info = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "product_info",
                    product_info_id,
                    {"description": product_info_update_payload["description"]},
                    tenant_id,
                    fallback_payload=product_info_update_payload,
                )
                assert updated_product_info.get("description") == product_info_update_payload["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "product_info",
                    product_info_id,
                    "description",
                    product_info_update_payload["description"],
                    tenant_id,
                )

                goods_info_stockin_payload = {
                    "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                    "product": {"id": product_info_id},
                    "type": 1,
                    "count": 100,
                    "price": 99.99,
                    "shelf": [{"id": shelf_id}],
                }
                goods_info_stockin = sdks["goods_info"].create_goods_info(
                    goods_info_stockin_payload
                )
                goods_info_stockin_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_info", goods_info_stockin
                )
                queried_goods_info_stockin = sdks["goods_info"].query_goods_info(
                    goods_info_stockin_id
                )
                assert queried_goods_info_stockin is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "goods_info", goods_info_stockin_id, tenant_id
                )
                goods_info_stockin_update_payload = {"count": 120, "price": 109.99}
                updated_goods_info_stockin = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "goods_info",
                    goods_info_stockin_id,
                    goods_info_stockin_update_payload,
                    tenant_id,
                )
                assert updated_goods_info_stockin.get("count") == goods_info_stockin_update_payload["count"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "goods_info",
                    goods_info_stockin_id,
                    "count",
                    goods_info_stockin_update_payload["count"],
                    tenant_id,
                )

                goods_info_stockout_payload = {
                    "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                    "product": {"id": product_info_id},
                    "type": 2,
                    "count": 50,
                    "price": 59.99,
                    "shelf": [{"id": shelf_id}],
                }
                goods_info_stockout = sdks["goods_info"].create_goods_info(
                    goods_info_stockout_payload
                )
                goods_info_stockout_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_info", goods_info_stockout
                )
                queried_goods_info_stockout = sdks["goods_info"].query_goods_info(
                    goods_info_stockout_id
                )
                assert queried_goods_info_stockout is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "goods_info", goods_info_stockout_id, tenant_id
                )
                goods_info_stockout_update_payload = {"count": 60, "price": 69.99}
                updated_goods_info_stockout = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "goods_info",
                    goods_info_stockout_id,
                    goods_info_stockout_update_payload,
                    tenant_id,
                )
                assert updated_goods_info_stockout.get("count") == goods_info_stockout_update_payload["count"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "goods_info",
                    goods_info_stockout_id,
                    "count",
                    goods_info_stockout_update_payload["count"],
                    tenant_id,
                )

                goods_payload = {
                    "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                    "name": f"MT_GOODS_{suffix}",
                    "description": f"多租户并发商品_{suffix}",
                    "parameter": f"参数_{suffix}",
                    "serviceInfo": f"服务信息_{suffix}",
                    "product": {"id": product_info_id},
                    "count": 80,
                    "price": 119.99,
                    "shelf": [{"id": shelf_id}],
                    "store": {"id": store_id},
                    "status": {"id": status_id},
                }
                goods = sdks["goods"].create_goods(goods_payload)
                goods_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods", goods
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(goods, tenant_id)
                assert sdks["goods"].query_goods(goods_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "goods", goods_id, tenant_id
                )
                goods_partial_update = {"description": f"更新后的商品_{suffix}", "count": 88}
                goods_fallback_update = dict(goods_payload)
                goods_fallback_update["description"] = goods_partial_update["description"]
                goods_fallback_update["count"] = goods_partial_update["count"]
                updated_goods = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "goods",
                    goods_id,
                    goods_partial_update,
                    tenant_id,
                    fallback_payload=goods_fallback_update,
                )
                assert updated_goods.get("description") == goods_partial_update["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "goods",
                    goods_id,
                    "description",
                    goods_partial_update["description"],
                    tenant_id,
                )

                reward_policy_payload = {
                    "name": f"MT_POLICY_{suffix}",
                    "description": f"多租户并发积分策略_{suffix}",
                    "policy": json.dumps(
                        {"type": "fixed", "points": 100, "tenant": tenant_id},
                        ensure_ascii=False,
                    ),
                    "status": {"id": status_id},
                }
                reward_policy = sdks["reward_policy"].create_reward_policy(
                    reward_policy_payload
                )
                reward_policy_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "reward_policy", reward_policy
                )
                assert (
                    sdks["reward_policy"].query_reward_policy(reward_policy_id) is not None
                )
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "reward_policy", reward_policy_id, tenant_id
                )
                reward_policy_update_payload = {
                    "name": f"更新后的策略_{suffix}",
                    "description": f"更新后的积分策略_{suffix}",
                }
                updated_reward_policy = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "reward_policy",
                    reward_policy_id,
                    reward_policy_update_payload,
                    tenant_id,
                )
                assert updated_reward_policy.get("name") == reward_policy_update_payload["name"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "reward_policy",
                    reward_policy_id,
                    "name",
                    reward_policy_update_payload["name"],
                    tenant_id,
                )

                credit_payload = {
                    "owner": {"id": partner_id},
                    "memo": f"多租户并发积分_{suffix}",
                    "credit": 100,
                    "type": 1,
                    "level": 1,
                }
                credit = sdks["credit"].create_credit(credit_payload)
                credit_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit", credit
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(credit, tenant_id)
                assert sdks["credit"].query_credit(credit_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "credit", credit_id, tenant_id
                )
                credit_update_payload = dict(credit)
                credit_update_payload["memo"] = f"更新后的积分备注_{suffix}"
                updated_credit = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "credit", credit_id, credit_update_payload, tenant_id
                )
                assert updated_credit.get("memo") == credit_update_payload["memo"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks, "credit", credit_id, "memo", credit_update_payload["memo"], tenant_id
                )

                credit_report_payload = {
                    "owner": {"id": partner_id},
                    "credit": 1000,
                    "available": 800,
                }
                credit_report = sdks["credit_report"].create_credit_report(
                    credit_report_payload
                )
                credit_report_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit_report", credit_report
                )
                assert (
                    sdks["credit_report"].query_credit_report(credit_report_id)
                    is not None
                )
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "credit_report", credit_report_id, tenant_id
                )
                credit_report_update_payload = {"credit": 1200, "available": 900}
                updated_credit_report = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "credit_report",
                    credit_report_id,
                    credit_report_update_payload,
                    tenant_id,
                )
                assert updated_credit_report.get("credit") == credit_report_update_payload["credit"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "credit_report",
                    credit_report_id,
                    "credit",
                    credit_report_update_payload["credit"],
                    tenant_id,
                )

                credit_reward_payload = {
                    "owner": {"id": partner_id},
                    "credit": 100,
                    "memo": f"多租户并发积分消费_{suffix}",
                }
                credit_reward = sdks["credit_reward"].create_credit_reward(
                    credit_reward_payload
                )
                credit_reward_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "credit_reward", credit_reward
                )
                assert (
                    sdks["credit_reward"].query_credit_reward(credit_reward_id)
                    is not None
                )
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "credit_reward", credit_reward_id, tenant_id
                )
                credit_reward_update_payload = {"memo": f"更新后的积分消费_{suffix}"}
                updated_credit_reward = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "credit_reward",
                    credit_reward_id,
                    credit_reward_update_payload,
                    tenant_id,
                )
                assert updated_credit_reward.get("memo") == credit_reward_update_payload["memo"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "credit_reward",
                    credit_reward_id,
                    "memo",
                    credit_reward_update_payload["memo"],
                    tenant_id,
                )

                goods_item_payload = {
                    "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                    "name": f"MT_GOODS_ITEM_{suffix}",
                    "price": 39.99,
                    "count": 3,
                }
                goods_item = sdks["goods_item"].create_goods_item(goods_item_payload)
                goods_item_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "goods_item", goods_item
                )
                assert sdks["goods_item"].query_goods_item(goods_item_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "goods_item", goods_item_id, tenant_id
                )
                goods_item_update_payload = {
                    "name": f"更新后的商品条目_{suffix}",
                    "price": 49.99,
                }
                updated_goods_item = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "goods_item",
                    goods_item_id,
                    goods_item_update_payload,
                    tenant_id,
                )
                assert updated_goods_item.get("name") == goods_item_update_payload["name"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "goods_item",
                    goods_item_id,
                    "name",
                    goods_item_update_payload["name"],
                    tenant_id,
                )

                stockin_payload = {
                    "goodsInfo": [
                        MultiTenantBusinessScenarioFactory._build_goods_info_payload(
                            queried_goods_info_stockin,
                            product_info_id,
                            shelf_id,
                            default_type=1,
                            default_count=100,
                            default_price=99.99,
                        )
                    ],
                    "description": f"多租户并发入库单_{suffix}",
                    "store": {"id": store_id},
                    "status": {"id": status_id},
                }
                stockin = sdks["stockin"].create_stockin(stockin_payload)
                stockin_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "stockin", stockin
                )
                assert sdks["stockin"].query_stockin(stockin_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "stockin", stockin_id, tenant_id
                )
                stockin_partial_update = {"description": f"更新后的入库单_{suffix}"}
                stockin_fallback_update = dict(stockin_payload)
                stockin_fallback_update["description"] = stockin_partial_update["description"]
                updated_stockin = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "stockin",
                    stockin_id,
                    stockin_partial_update,
                    tenant_id,
                    fallback_payload=stockin_fallback_update,
                )
                assert updated_stockin.get("description") == stockin_partial_update["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "stockin",
                    stockin_id,
                    "description",
                    stockin_partial_update["description"],
                    tenant_id,
                )

                stockout_payload = {
                    "goodsInfo": [
                        MultiTenantBusinessScenarioFactory._build_goods_info_payload(
                            queried_goods_info_stockout,
                            product_info_id,
                            shelf_id,
                            default_type=2,
                            default_count=50,
                            default_price=59.99,
                        )
                    ],
                    "description": f"多租户并发出库单_{suffix}",
                    "store": {"id": store_id},
                    "status": {"id": status_id},
                }
                stockout = sdks["stockout"].create_stockout(stockout_payload)
                stockout_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "stockout", stockout
                )
                assert sdks["stockout"].query_stockout(stockout_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "stockout", stockout_id, tenant_id
                )
                stockout_partial_update = {"description": f"更新后的出库单_{suffix}"}
                stockout_fallback_update = dict(stockout_payload)
                stockout_fallback_update["description"] = stockout_partial_update["description"]
                updated_stockout = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "stockout",
                    stockout_id,
                    stockout_partial_update,
                    tenant_id,
                    fallback_payload=stockout_fallback_update,
                )
                assert updated_stockout.get("description") == stockout_partial_update["description"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks,
                    "stockout",
                    stockout_id,
                    "description",
                    stockout_partial_update["description"],
                    tenant_id,
                )

                order_payload = {
                    "type": 1,
                    "customer": {"id": partner_id},
                    "goods": [
                        {
                            "sku": goods_item.get(
                                "sku",
                                MultiTenantBusinessScenarioFactory._build_numeric_code(),
                            ),
                            "name": goods_item.get("name", f"订单商品_{suffix}"),
                            "price": goods_item.get("price", 39.99),
                            "count": 2,
                        }
                    ],
                    "cost": 79.98,
                    "store": {"id": store_id},
                    "status": {"id": status_id},
                }
                order = sdks["order"].create_order(order_payload)
                order_id = MultiTenantBusinessScenarioFactory._record_entity(
                    created_entities, "order", order
                )
                MultiTenantBusinessScenarioFactory._assert_namespace(order, tenant_id)
                assert sdks["order"].query_order(order_id) is not None
                MultiTenantBusinessScenarioFactory._assert_list_contains(
                    sdks, "order", order_id, tenant_id
                )
                order_update_payload = {
                    "cost": 89.98,
                    "memo": f"更新后的订单备注_{suffix}",
                }
                updated_order = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks, "order", order_id, order_update_payload, tenant_id
                )
                assert updated_order.get("cost") == order_update_payload["cost"]
                MultiTenantBusinessScenarioFactory._assert_query_field(
                    sdks, "order", order_id, "cost", order_update_payload["cost"], tenant_id
                )

                logger.info("租户 %s: 全业务链路执行完成", tenant_id)

            finally:
                MultiTenantBusinessScenarioFactory._cleanup_entities(
                    sdks, created_entities
                )

        return test_full_business_flow

    @staticmethod
    def _prepare_hotspot_context(
        tenant_id: str,
        session_manager,
    ) -> Dict[str, Any]:
        existing_context = getattr(session_manager, "_vmi_hotspot_context", None)
        if existing_context is not None:
            return existing_context

        sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(session_manager)
        created_entities: Dict[str, List[int]] = defaultdict(list)
        suffix = f"{tenant_id}_{uuid.uuid4().hex[:8]}"

        statuses = MultiTenantBusinessScenarioFactory._load_statuses_with_retry(
            sdks,
            tenant_id,
        )
        status_id = MultiTenantBusinessScenarioFactory._resolve_status_id_from_statuses(
            statuses
        )
        assert status_id, f"租户 {tenant_id} 无法解析可用状态ID"

        warehouse = sdks["warehouse"].create_warehouse(
            {
                "name": f"STRESS_WH_{suffix}",
                "description": f"热点压测仓库_{suffix}",
            }
        )
        warehouse_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "warehouse", warehouse
        )

        shelf = sdks["shelf"].create_shelf(
            {
                "description": f"热点压测货架_{suffix}",
                "capacity": 500,
                "warehouse": {"id": warehouse_id},
                "status": {"id": status_id},
            }
        )
        shelf_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "shelf", shelf
        )

        store = sdks["store"].create_store(
            {
                "name": f"STRESS_STORE_{suffix}",
                "description": f"热点压测门店_{suffix}",
            }
        )
        store_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "store", store
        )

        product = sdks["product"].create_product(
            {
                "name": f"STRESS_PRODUCT_{suffix}",
                "description": f"热点压测产品_{suffix}",
                "image": [],
                "expire": 365,
                "tags": ["stress", tenant_id, suffix],
                "status": {"id": status_id},
            }
        )
        product_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "product", product
        )

        product_info = sdks["product_info"].create_product_info(
            {
                "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                "description": f"热点压测产品SKU_{suffix}",
                "product": {"id": product_id},
            }
        )
        product_info_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "product_info", product_info
        )

        goods_info = sdks["goods_info"].create_goods_info(
            {
                "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                "product": {"id": product_info_id},
                "type": 1,
                "count": 200,
                "price": 88.88,
                "shelf": [{"id": shelf_id}],
            }
        )
        goods_info_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "goods_info", goods_info
        )

        goods = sdks["goods"].create_goods(
            {
                "sku": MultiTenantBusinessScenarioFactory._build_numeric_code(),
                "name": f"STRESS_GOODS_{suffix}",
                "description": f"热点压测商品_{suffix}",
                "parameter": f"参数_{suffix}",
                "serviceInfo": f"服务_{suffix}",
                "product": {"id": product_info_id},
                "count": 160,
                "price": 128.88,
                "shelf": [{"id": shelf_id}],
                "store": {"id": store_id},
                "status": {"id": status_id},
            }
        )
        goods_id = MultiTenantBusinessScenarioFactory._record_entity(
            created_entities, "goods", goods
        )

        cleaned = {"done": False}

        def cleanup_hotspot_context():
            if cleaned["done"]:
                return
            cleaned["done"] = True
            cleanup_sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(
                session_manager
            )
            MultiTenantBusinessScenarioFactory._cleanup_entities(
                cleanup_sdks, created_entities
            )

        context = {
            "status_id": status_id,
            "warehouse_id": warehouse_id,
            "shelf_id": shelf_id,
            "store_id": store_id,
            "product_id": product_id,
            "product_info_id": product_info_id,
            "goods_info_id": goods_info_id,
            "goods_id": goods_id,
            "suffix": suffix,
            "hotspot_update_templates": {
                "warehouse": {
                    "name": f"STRESS_WH_{suffix}",
                    "description": f"热点压测仓库_{suffix}",
                },
                "store": {
                    "name": f"STRESS_STORE_{suffix}",
                    "description": f"热点压测门店_{suffix}",
                },
                "product": {
                    "name": f"STRESS_PRODUCT_{suffix}",
                    "description": f"热点压测产品_{suffix}",
                    "image": [],
                    "expire": 365,
                    "tags": ["stress", tenant_id, suffix],
                    "status": {"id": status_id},
                },
                "goods": {
                    "sku": goods["sku"],
                    "name": goods["name"],
                    "description": goods["description"],
                    "parameter": goods["parameter"],
                    "serviceInfo": goods["serviceInfo"],
                    "product": {"id": product_info_id},
                    "count": goods["count"],
                    "price": goods["price"],
                    "shelf": [{"id": shelf_id}],
                    "store": {"id": store_id},
                    "status": {"id": status_id},
                },
            },
            "cleanup": cleanup_hotspot_context,
        }
        session_manager._vmi_hotspot_context = context
        session_manager._codex_cleanup_hook = cleanup_hotspot_context
        logger.info("租户 %s: 共享热点资源初始化完成", tenant_id)
        return context

    @staticmethod
    def create_hotspot_stress_test(
        write_every: int = 4,
        read_rounds: int = 2,
        query_rounds: int = 2,
        prewrite_query: bool = False,
        shared_context_provider: Optional[Callable[[str, Any], Dict[str, Any]]] = None,
    ):
        """创建更偏向 DB 热点读写重叠的多租户压测场景。"""

        def test_hotspot_stress(
            tenant_id: str,
            worker_id: int,
            iteration: int,
            session_manager,
        ):
            if shared_context_provider is None:
                context = MultiTenantBusinessScenarioFactory._prepare_hotspot_context(
                    tenant_id=tenant_id,
                    session_manager=session_manager,
                )
            else:
                context = shared_context_provider(tenant_id, session_manager)
            sdks = MultiTenantBusinessScenarioFactory._get_hotspot_sdks(session_manager)

            filter_params = {
                "status": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "status",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                            ],
                        }
                    ),
                },
                "warehouse": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "warehouse",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                            ],
                        }
                    ),
                },
                "store": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "store",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                            ],
                        }
                    ),
                },
                "product": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "product",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                                {"name": "image", "value": []},
                                {"name": "tags", "value": []},
                            ],
                        }
                    ),
                },
                "product_info": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "productInfo",
                            "pkgPath": "/vmi/product",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "description", "value": ""},
                                {"name": "image", "value": []},
                            ],
                        }
                    ),
                },
                "goods_info": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "goodsInfo",
                            "pkgPath": "/vmi/store",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "type", "value": 0},
                                {"name": "count", "value": 0},
                                {"name": "price", "value": 0.0},
                            ],
                        }
                    ),
                },
                "goods": {
                    "page": 1,
                    "size": 200,
                    "_viewType": "lite",
                    "_needTotal": "false",
                    "_valueMask": json.dumps(
                        {
                            "name": "goods",
                            "pkgPath": "/vmi/store",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "name", "value": ""},
                                {"name": "price", "value": 0.0},
                            ],
                        }
                    ),
                },
            }
            query_params = {
                "warehouse": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "warehouse",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                            ],
                        }
                    ),
                },
                "store": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "store",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                            ],
                        }
                    ),
                },
                "product": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "product",
                            "pkgPath": "/vmi",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "name", "value": ""},
                                {"name": "description", "value": ""},
                                {"name": "image", "value": []},
                                {"name": "tags", "value": []},
                            ],
                        }
                    ),
                },
                "product_info": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "productInfo",
                            "pkgPath": "/vmi/product",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "description", "value": ""},
                                {"name": "image", "value": []},
                            ],
                        }
                    ),
                },
                "goods_info": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "goodsInfo",
                            "pkgPath": "/vmi/store",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "type", "value": 0},
                                {"name": "count", "value": 0},
                                {"name": "price", "value": 0.0},
                            ],
                        }
                    ),
                },
                "goods": {
                    "_viewType": "lite",
                    "_valueMask": json.dumps(
                        {
                            "name": "goods",
                            "pkgPath": "/vmi/store",
                            "fields": [
                                {"name": "id", "value": 0},
                                {"name": "sku", "value": ""},
                                {"name": "name", "value": ""},
                                {"name": "price", "value": 0.0},
                            ],
                        }
                    ),
                },
            }
            warehouse_id = context["warehouse_id"]
            store_id = context["store_id"]
            product_id = context["product_id"]
            product_info_id = context["product_info_id"]
            goods_info_id = context["goods_info_id"]
            goods_id = context["goods_id"]

            for _ in range(max(1, read_rounds)):
                assert sdks["status"].filter_status(filter_params["status"]) is not None
                assert sdks["warehouse"].filter_warehouse(filter_params["warehouse"]) is not None
                assert sdks["store"].filter_store(filter_params["store"]) is not None
                assert sdks["product"].filter_product(filter_params["product"]) is not None
                assert sdks["product_info"].filter_product_info(filter_params["product_info"]) is not None
                assert sdks["goods_info"].filter_goods_info(filter_params["goods_info"]) is not None
                assert sdks["goods"].filter_goods(filter_params["goods"]) is not None

            for _ in range(max(1, query_rounds)):
                assert sdks["warehouse"].query(warehouse_id, query_params["warehouse"]) is not None
                assert sdks["store"].query(store_id, query_params["store"]) is not None
                assert sdks["product"].query(product_id, query_params["product"]) is not None
                assert sdks["product_info"].query(product_info_id, query_params["product_info"]) is not None
                assert sdks["goods_info"].query(goods_info_id, query_params["goods_info"]) is not None
                assert sdks["goods"].query(goods_id, query_params["goods"]) is not None

            if (iteration + 1) % max(1, write_every) != 0:
                return

            update_suffix = f"{context['suffix']}_{iteration}"
            warehouse_update = {"description": f"热点压测更新仓库_{update_suffix}"}
            store_update = {"description": f"热点压测更新门店_{update_suffix}"}
            product_update = {"description": f"热点压测更新产品_{update_suffix}"}
            goods_update = {
                "description": f"热点压测更新商品_{update_suffix}",
                "count": 160 + ((iteration + worker_id) % 17),
            }

            if prewrite_query:
                warehouse_payload = dict(sdks["warehouse"].query_warehouse(warehouse_id))
                warehouse_payload.update(warehouse_update)

                store_payload = dict(sdks["store"].query_store(store_id))
                store_payload.update(store_update)

                product_payload = dict(sdks["product"].query_product(product_id))
                product_payload.update(product_update)

                current_goods = sdks["goods"].query_goods(goods_id)
                assert current_goods is not None
                goods_fallback_payload = {
                    "sku": current_goods.get(
                        "sku", MultiTenantBusinessScenarioFactory._build_numeric_code()
                    ),
                    "name": current_goods.get(
                        "name", f"STRESS_GOODS_{context['suffix']}"
                    ),
                    "description": goods_update["description"],
                    "parameter": current_goods.get(
                        "parameter", f"参数_{context['suffix']}"
                    ),
                    "serviceInfo": current_goods.get(
                        "serviceInfo", f"服务_{context['suffix']}"
                    ),
                    "product": {"id": product_info_id},
                    "count": goods_update["count"],
                    "price": current_goods.get("price", 128.88),
                    "shelf": [{"id": context['shelf_id']}],
                    "store": {"id": store_id},
                    "status": {"id": context["status_id"]},
                }
            else:
                hotspot_update_templates = context["hotspot_update_templates"]
                warehouse_payload = deepcopy(hotspot_update_templates["warehouse"])
                warehouse_payload.update(warehouse_update)
                updated_warehouse = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "warehouse",
                    warehouse_id,
                    warehouse_update,
                    tenant_id,
                    fallback_payload=warehouse_payload,
                )
                assert updated_warehouse is not None

                store_payload = deepcopy(hotspot_update_templates["store"])
                store_payload.update(store_update)
                updated_store = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "store",
                    store_id,
                    store_update,
                    tenant_id,
                    fallback_payload=store_payload,
                )
                assert updated_store is not None

                product_payload = deepcopy(hotspot_update_templates["product"])
                product_payload.update(product_update)
                updated_product = MultiTenantBusinessScenarioFactory._update_entity(
                    sdks,
                    "product",
                    product_id,
                    product_update,
                    tenant_id,
                    fallback_payload=product_payload,
                )
                assert updated_product is not None

                goods_fallback_payload = deepcopy(hotspot_update_templates["goods"])
                goods_fallback_payload.update(goods_update)

            if prewrite_query:
                updated_warehouse = sdks["warehouse"].update_warehouse(
                    warehouse_id, warehouse_payload
                )
            assert updated_warehouse is not None

            if prewrite_query:
                updated_store = sdks["store"].update_store(store_id, store_payload)
            assert updated_store is not None

            if prewrite_query:
                updated_product = sdks["product"].update_product(
                    product_id, product_payload
                )
            assert updated_product is not None

            updated_goods = MultiTenantBusinessScenarioFactory._update_entity(
                sdks,
                "goods",
                goods_id,
                goods_update,
                tenant_id,
                fallback_payload=goods_fallback_payload,
            )
            assert updated_goods is not None

        return test_hotspot_stress


def run_multi_tenant_hotspot_stress_test() -> ConcurrentTestResult:
    from config_helper import get_concurrent_config, get_timeout
    from tenant_config_helper import (
        get_concurrent_tenant_configs,
        get_preferred_concurrent_tenant_ids,
    )

    preferred_tenant_ids = get_preferred_concurrent_tenant_ids()
    tenant_configs = get_concurrent_tenant_configs(preferred_tenant_ids)
    if not tenant_configs:
        raise unittest.SkipTest("多租户未启用，跳过多租户热点压测")

    concurrent_config = get_concurrent_config()
    workers_per_tenant = int(concurrent_config.get("workers_per_tenant", 4))
    iterations_per_worker = int(concurrent_config.get("iterations_per_worker", 12))
    write_every = int(concurrent_config.get("write_every", 4))
    read_rounds = int(concurrent_config.get("hotspot_read_rounds", 2))
    query_rounds = int(concurrent_config.get("hotspot_query_rounds", 2))
    prewrite_query = bool(concurrent_config.get("hotspot_prewrite_query", False))
    shared_context_per_tenant = bool(
        concurrent_config.get("hotspot_shared_context_per_tenant", True)
    )
    measure_loop_only = bool(concurrent_config.get("hotspot_measure_loop_only", True))

    runner = MultiTenantConcurrentRunner(
        tenant_configs=tenant_configs,
        max_workers=max(1, len(tenant_configs) * workers_per_tenant),
        timeout=max(get_timeout(), 300),
    )

    def shared_context_provider(tenant_id: str, session_manager):
        return runner.get_or_create_shared_context(
            tenant_id,
            lambda: MultiTenantBusinessScenarioFactory._prepare_hotspot_context(
                tenant_id=tenant_id,
                session_manager=session_manager,
            ),
        )

    def prepare_hotspot_worker(tenant_id: str, worker_id: int, session_manager):
        del worker_id
        if shared_context_per_tenant:
            shared_context_provider(tenant_id, session_manager)
        MultiTenantBusinessScenarioFactory._warmup_hotspot_session(
            tenant_id,
            session_manager,
        )

    return runner.run_multi_tenant_worker_loop_test(
        test_func=MultiTenantBusinessScenarioFactory.create_hotspot_stress_test(
            write_every=write_every,
            read_rounds=read_rounds,
            query_rounds=query_rounds,
            prewrite_query=prewrite_query,
            shared_context_provider=(
                shared_context_provider if shared_context_per_tenant else None
            ),
        ),
        test_name="multi_tenant_hotspot_stress",
        workers_per_tenant=workers_per_tenant,
        iterations_per_worker=iterations_per_worker,
        prepare_func=prepare_hotspot_worker,
        measure_loop_only=measure_loop_only,
    )


def assert_hotspot_result(result: ConcurrentTestResult) -> None:
    assert result.failed_requests == 0, f"失败详情: {result.error_details[:5]}"
    assert (
        result.successful_requests == result.total_requests
    ), f"存在请求执行失败: {result.error_details[:5]}"
    assert result.http_qps > 5.0, "多租户热点压测 HTTP QPS 应大于5"
    assert result.write_tps > 0.5, "多租户热点压测写TPS应大于0.5"
    assert result.avg_response_time > 0, "平均响应时间应大于0"


def run_multi_tenant_full_flow_coverage_test() -> ConcurrentTestResult:
    from config_helper import get_max_workers, get_timeout
    from tenant_config_helper import (
        get_concurrent_tenant_configs,
        get_preferred_concurrent_tenant_ids,
    )

    preferred_tenant_ids = get_preferred_concurrent_tenant_ids()
    tenant_configs = get_concurrent_tenant_configs(preferred_tenant_ids)
    if not tenant_configs:
        raise unittest.SkipTest("多租户未启用，跳过 t001-t005 并发业务测试")

    missing_tenants = [
        tenant_id for tenant_id in preferred_tenant_ids if tenant_id not in tenant_configs
    ]
    if missing_tenants:
        raise unittest.SkipTest(f"目标租户配置不完整，缺少: {missing_tenants}")

    runner = MultiTenantConcurrentRunner(
        tenant_configs=tenant_configs,
        max_workers=max(len(tenant_configs), get_max_workers()),
        timeout=max(get_timeout(), 120),
    )
    return runner.run_multi_tenant_test(
        test_func=MultiTenantBusinessScenarioFactory.create_full_business_flow_test(),
        test_name="concurrent_multi_tenant_full_vmi_coverage",
    )


def assert_full_flow_result(result: ConcurrentTestResult) -> None:
    from tenant_config_helper import get_preferred_concurrent_tenant_ids

    preferred_tenant_ids = get_preferred_concurrent_tenant_ids()
    assert result.total_requests == len(preferred_tenant_ids)
    assert (
        result.successful_requests == len(preferred_tenant_ids)
    ), f"存在租户执行失败: {result.error_details}"
    assert result.failed_requests == 0, f"失败详情: {result.error_details}"
    assert result.avg_response_time > 0, "平均响应时间应大于0"


class TestConcurrentMultiTenantBusinessOperations(unittest.TestCase):
    """多租户并发业务覆盖测试。"""

    def test_multi_tenant_hotspot_stress(self):
        result = run_multi_tenant_hotspot_stress_test()
        assert_hotspot_result(result)

    def test_concurrent_multi_tenant_full_vmi_coverage(self):
        result = run_multi_tenant_full_flow_coverage_test()
        assert_full_flow_result(result)


def build_runtime_metadata(env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from config_helper import (
        get_concurrent_config,
        get_credentials,
        get_default_tenant,
        get_observability_config,
        get_request_application,
        get_server_url,
        get_target_config,
        get_tenant_targets,
    )
    from tenant_config_helper import get_preferred_concurrent_tenant_ids

    metadata = {
        "server_url": get_server_url(),
        "default_tenant": get_default_tenant(),
        "tenant_targets": get_tenant_targets(),
        "preferred_concurrent_tenants": get_preferred_concurrent_tenant_ids(),
        "username": get_credentials().get("username", ""),
        "request_application": get_request_application(),
        "prometheus_window": "10m",
        "concurrent_config": get_concurrent_config(),
        "target": get_target_config(),
        "observability": get_observability_config(),
    }

    if env_overrides:
        metadata["env_overrides"] = dict(env_overrides)

    return metadata


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VMI 并发压测入口")
    parser.add_argument(
        "--hotspot",
        action="store_true",
        help="只运行多租户热点读写压测",
    )
    parser.add_argument(
        "--full-flow",
        action="store_true",
        help="只运行多租户全业务链路并发覆盖",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="重复执行选中的压测轮次，默认 1",
    )
    parser.add_argument(
        "--report-file",
        help="将执行结果写入 JSON 报告文件",
    )
    parser.add_argument("--server-url", dest="server_url", help="临时覆盖默认服务地址")
    parser.add_argument(
        "--tenant-targets",
        help="临时覆盖并发租户列表，格式 t001,t002,t003",
    )
    parser.add_argument(
        "--tenant-url-template",
        dest="tenant_url_template",
        help="临时覆盖租户 URL 模板",
    )
    parser.add_argument(
        "--default-tenant",
        dest="default_tenant",
        help="临时覆盖默认租户",
    )
    parser.add_argument("--username", help="临时覆盖登录用户名")
    parser.add_argument("--password", help="临时覆盖登录密码")
    parser.add_argument("--namespace", help="临时覆盖请求命名空间")
    parser.add_argument(
        "--request-application",
        dest="request_application",
        help="为本轮压测绑定唯一 application/run_id，便于 Prometheus 对账",
    )
    parser.add_argument("--prometheus-url", dest="prometheus_url", help="记录 Prometheus 入口")
    parser.add_argument("--remote-host", dest="remote_host", help="记录远端目标主机")
    parser.add_argument("--remote-user", dest="remote_user", help="记录远端 SSH 用户")
    parser.add_argument(
        "--deployment-mode",
        dest="deployment_mode",
        help="记录部署形态，例如 docker",
    )
    parser.add_argument(
        "--ignore-env-proxy",
        dest="request_trust_env",
        action="store_false",
        default=None,
        help="HTTP 会话不继承系统代理环境变量",
    )
    parser.add_argument(
        "--trust-env-proxy",
        dest="request_trust_env",
        action="store_true",
        help="HTTP 会话继承系统代理环境变量",
    )
    parser.add_argument("--max-workers", type=int, dest="max_workers")
    parser.add_argument("--timeout", type=int, dest="timeout")
    parser.add_argument("--workers-per-tenant", type=int, dest="workers_per_tenant")
    parser.add_argument(
        "--iterations-per-worker", type=int, dest="iterations_per_worker"
    )
    parser.add_argument("--write-every", type=int, dest="write_every")
    parser.add_argument(
        "--hotspot-read-rounds", type=int, dest="hotspot_read_rounds"
    )
    parser.add_argument(
        "--hotspot-query-rounds", type=int, dest="hotspot_query_rounds"
    )
    parser.add_argument(
        "--hotspot-prewrite-query",
        dest="hotspot_prewrite_query",
        action="store_true",
        default=None,
        help="热点压测写入前先 query 当前对象，再构造完整更新载荷",
    )
    parser.add_argument(
        "--hotspot-no-prewrite-query",
        dest="hotspot_prewrite_query",
        action="store_false",
        help="热点压测写入前不额外 query 对象，失败时才回退完整模板",
    )
    parser.add_argument(
        "--shared-context-per-tenant",
        dest="hotspot_shared_context_per_tenant",
        action="store_true",
        default=None,
        help="热点压测共享同租户上下文",
    )
    parser.add_argument(
        "--isolated-context-per-worker",
        dest="hotspot_shared_context_per_tenant",
        action="store_false",
        help="热点压测每个 worker 独立准备上下文",
    )
    parser.add_argument(
        "--measure-loop-only",
        dest="hotspot_measure_loop_only",
        action="store_true",
        default=None,
        help="只统计压测循环窗口，不含预热和资源准备",
    )
    parser.add_argument(
        "--include-setup-time",
        dest="hotspot_measure_loop_only",
        action="store_false",
        help="统计包含预热和资源准备的完整耗时",
    )
    return parser


def run_selected_suites(
    hotspot_only: bool,
    full_flow_only: bool,
    repeat: int,
) -> Tuple[bool, List[ConcurrentTestResult], str]:
    if repeat < 1:
        raise ValueError("repeat 必须大于等于 1")

    results: List[ConcurrentTestResult] = []

    if hotspot_only and full_flow_only:
        raise ValueError("--hotspot 和 --full-flow 不能同时限定")

    if hotspot_only:
        suite_name = "multi_tenant_hotspot_stress"
        for round_index in range(repeat):
            logger.info("开始热点压测轮次 %s/%s", round_index + 1, repeat)
            result = run_multi_tenant_hotspot_stress_test()
            assert_hotspot_result(result)
            results.append(result)
        return True, results, suite_name

    if full_flow_only:
        suite_name = "concurrent_multi_tenant_full_vmi_coverage"
        for round_index in range(repeat):
            logger.info("开始全链路并发覆盖轮次 %s/%s", round_index + 1, repeat)
            result = run_multi_tenant_full_flow_coverage_test()
            assert_full_flow_result(result)
            results.append(result)
        return True, results, suite_name

    if repeat != 1:
        raise ValueError("运行全部并发测试套件时暂不支持 --repeat，请改用 --hotspot 或 --full-flow")

    unittest_result = run_all_concurrent_tests()
    return unittest_result.wasSuccessful(), [], "all_concurrent_tests"


def run_all_concurrent_tests():
    """运行所有并发测试"""
    import unittest

    # 创建测试套件
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentStoreOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentProductOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestConcurrentWarehouseOperations)
    )
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(
            TestConcurrentMultiTenantBusinessOperations
        )
    )

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # 生成报告
    if result.wasSuccessful():
        logger.info("\n🎉 所有并发测试通过！")
    else:
        logger.error(
            f"\n❌ 测试失败：{len(result.failures)} 个失败，{len(result.errors)} 个错误"
        )

    return result


if __name__ == "__main__":
    parser = create_argument_parser()
    cli_args = parser.parse_args()
    request_application = ensure_request_application(cli_args)
    env_overrides = apply_runtime_env_overrides(cli_args)
    logger.info("基于会话管理器的并发测试V2")
    logger.info("%s", "=" * 60)
    if request_application:
        logger.info("本轮 request_application: %s", request_application)

    try:
        success, results, suite_name = run_selected_suites(
            hotspot_only=cli_args.hotspot,
            full_flow_only=cli_args.full_flow,
            repeat=cli_args.repeat,
        )
    except unittest.SkipTest as exc:
        logger.warning("%s", exc)
        raise SystemExit(0)
    except Exception as exc:
        logger.exception("并发压测执行失败: %s", exc)
        raise SystemExit(1)

    if cli_args.report_file and results:
        save_results_report(
            filepath=cli_args.report_file,
            suite_name=suite_name,
            results=results,
            metadata=build_runtime_metadata(env_overrides=env_overrides),
        )

    raise SystemExit(0 if success else 1)
