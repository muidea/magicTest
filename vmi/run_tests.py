#!/usr/bin/env python3
"""
VMI 统一测试入口
整合所有测试运行模式，支持 unittest 和 pytest

使用方法：
    python3 run_tests.py --all           # 运行所有测试
    python3 run_tests.py --quick         # 快速验证
    python3 run_tests.py --concurrent    # 并发测试
    python3 run_tests.py --hotspot       # 多租户热点压测
    python3 run_tests.py --hotspot --workers-per-tenant 12 --iterations-per-worker 20 --report-file hotspot-report.json
    python3 run_tests.py --scenario      # 场景测试
    python3 run_tests.py --aging 60      # 老化测试（60分钟）
    python3 run_tests.py --multi-tenant  # 多租户测试
    python3 run_tests.py --validation    # 框架验证测试
    python3 run_tests.py --module        # 模块测试
    python3 run_tests.py --pytest --all  # 使用 pytest 运行
"""

import argparse
import json
import logging
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "test_config.json")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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


def python_cmd() -> str:
    return shlex.quote(sys.executable)


def pytest_cmd() -> str:
    return f"{python_cmd()} -m pytest"


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("配置文件不存在: %s", CONFIG_FILE)
        return {}


def _shell_quote_args(args: List[str]) -> str:
    return " ".join(shlex.quote(str(arg)) for arg in args)


def _stringify_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_runtime_env(args: argparse.Namespace) -> Dict[str, str]:
    env = os.environ.copy()
    for arg_name, env_name in RUNTIME_ENV_ARG_MAP.items():
        value = getattr(args, arg_name, None)
        if value is not None:
            env[env_name] = _stringify_env_value(value)
    return env


def summarize_runtime_overrides(args: argparse.Namespace) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    for arg_name in RUNTIME_ENV_ARG_MAP:
        value = getattr(args, arg_name, None)
        if value is not None:
            summary[arg_name] = value
    return summary


def build_concurrent_cli_args(
    args: argparse.Namespace,
    hotspot_only: bool = False,
    full_flow_only: bool = False,
) -> List[str]:
    cmd = [python_cmd(), "concurrent_test_v2.py"]
    if hotspot_only:
        cmd.append("--hotspot")
    if full_flow_only:
        cmd.append("--full-flow")
    repeat = getattr(args, "repeat", None)
    if repeat is not None and repeat != 1:
        cmd.extend(["--repeat", str(repeat)])
    report_file = getattr(args, "report_file", None)
    if report_file:
        cmd.extend(["--report-file", report_file])
    return cmd


def run_command(
    cmd: str, description: str = "", env: Optional[Dict[str, str]] = None
) -> Tuple[bool, float]:
    logger.info("\n%s", "=" * 60)
    logger.info("执行: %s", description)
    logger.info("命令: %s", cmd)
    logger.info("%s", "=" * 60)

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            env=env,
        )
        elapsed = time.time() - start_time

        if result.stdout:
            logger.info("%s", result.stdout.rstrip())

        if result.stderr and result.returncode != 0:
            logger.error("错误: %s", result.stderr.rstrip())

        logger.info("执行时间: %.2f秒", elapsed)

        return result.returncode == 0, elapsed
    except Exception as e:
        logger.exception("执行命令时出错: %s", e)
        return False, 0


def run_pytest_command(
    pytest_args: List[str],
    description: str = "",
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, float]:
    cmd = pytest_cmd() + " " + " ".join(pytest_args)
    return run_command(cmd, description, env=env)


def run_validation_tests(
    pytest_mode: bool = False, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, float]:
    """运行框架验证测试（包含基础功能和会话管理验证）"""
    logger.info("运行框架验证测试")

    if pytest_mode:
        return run_pytest_command(
            ["test_complete_validation.py", "-v", "--tb=short"],
            "框架验证测试 (pytest)",
            env=env,
        )

    cmd = f"{python_cmd()} test_complete_validation.py"
    return run_command(cmd, "框架验证测试", env=env)


def run_multi_tenant_tests(
    pytest_mode: bool = False, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, float]:
    """运行多租户测试"""
    logger.info("运行多租户测试")

    if pytest_mode:
        return run_pytest_command(
            [
                "test_multi_tenant.py",
                "test_multi_tenant_example.py",
                "-v",
                "--tb=short",
            ],
            "多租户测试 (pytest)",
            env=env,
        )

    cmd = f"{python_cmd()} test_multi_tenant.py"
    return run_command(cmd, "多租户测试", env=env)


def run_concurrent_tests(
    pytest_mode: bool = False,
    env: Optional[Dict[str, str]] = None,
    cli_args: Optional[argparse.Namespace] = None,
) -> Tuple[bool, float]:
    """运行并发测试"""
    logger.info("运行并发测试")

    if pytest_mode:
        return run_pytest_command(
            ["concurrent_test_v2.py", "-v", "--tb=short"],
            "并发测试 (pytest)",
            env=env,
        )

    cmd = (
        _shell_quote_args(build_concurrent_cli_args(cli_args or argparse.Namespace()))
        if cli_args is not None
        else f"{python_cmd()} concurrent_test_v2.py"
    )
    return run_command(cmd, "并发测试", env=env)


def run_hotspot_tests(
    pytest_mode: bool = False,
    env: Optional[Dict[str, str]] = None,
    cli_args: Optional[argparse.Namespace] = None,
) -> Tuple[bool, float]:
    """运行多租户热点压测"""
    logger.info("运行多租户热点压测")

    if pytest_mode:
        return run_pytest_command(
            [
                "concurrent_test_v2.py",
                "-k",
                "test_multi_tenant_hotspot_stress",
                "-v",
                "--tb=short",
            ],
            "多租户热点压测 (pytest)",
            env=env,
        )

    if cli_args is not None:
        cmd = _shell_quote_args(build_concurrent_cli_args(cli_args, hotspot_only=True))
    else:
        cmd = (
            f"{python_cmd()} -m unittest "
            "concurrent_test_v2.TestConcurrentMultiTenantBusinessOperations."
            "test_multi_tenant_hotspot_stress -v"
        )
    return run_command(cmd, "多租户热点压测", env=env)


def run_scenario_tests(
    pytest_mode: bool = False, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, float]:
    """运行场景测试"""
    logger.info("运行场景测试")

    if pytest_mode:
        return run_pytest_command(
            ["scenario_test.py", "-v", "--tb=short"],
            "场景测试 (pytest)",
            env=env,
        )

    cmd = f"{python_cmd()} scenario_test.py"
    return run_command(cmd, "场景测试", env=env)


def run_aging_tests(
    duration: Optional[int] = None,
    pytest_mode: bool = False,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[bool, float]:
    """运行老化测试"""
    if duration is None:
        logger.info("运行老化测试（使用配置文件时长）")
        if pytest_mode:
            cmd = f"{python_cmd()} aging_test_simple.py --threads 2"
            return run_command(cmd, "老化测试 (配置文件) - 轻量模式", env=env)

        cmd = f"{python_cmd()} aging_test_simple.py"
        return run_command(cmd, "老化测试 (配置文件)", env=env)

    logger.info("运行老化测试（%s分钟）", duration)
    duration_hours = duration / 60.0

    if pytest_mode:
        cmd = (
            f"{python_cmd()} aging_test_simple.py "
            f"--duration {duration_hours} --threads 2"
        )
        return run_command(cmd, f"老化测试 ({duration}分钟) - 轻量模式", env=env)

    cmd = f"{python_cmd()} aging_test_simple.py --duration {duration_hours}"
    return run_command(cmd, f"老化测试 ({duration}分钟)", env=env)


def run_module_tests(
    pytest_mode: bool = False, env: Optional[Dict[str, str]] = None
) -> Tuple[bool, float]:
    """运行模块测试"""
    logger.info("运行模块测试")

    if pytest_mode:
        return run_pytest_command(
            [
                "./store",
                "./credit",
                "./order",
                "./product",
                "./warehouse",
                "./partner",
                "./status",
                "-v",
                "--tb=short",
            ],
            "模块测试 (pytest)",
            env=env,
        )

    cmd = f"{python_cmd()} -m unittest discover -s . -p '*_test.py' -v"
    return run_command(cmd, "模块测试", env=env)


def run_all_tests(
    pytest_mode: bool = False,
    include_aging: bool = False,
    aging_duration: Optional[int] = None,
    env: Optional[Dict[str, str]] = None,
) -> List[Tuple[str, bool, float]]:
    """运行所有测试"""
    logger.info("运行所有测试")

    results = []

    results.append(("框架验证测试", *run_validation_tests(pytest_mode, env=env)))
    results.append(("多租户测试", *run_multi_tenant_tests(pytest_mode, env=env)))
    results.append(("并发测试", *run_concurrent_tests(pytest_mode, env=env)))
    results.append(("场景测试", *run_scenario_tests(pytest_mode, env=env)))
    results.append(("模块测试", *run_module_tests(pytest_mode, env=env)))
    if include_aging:
        aging_label = (
            f"老化测试 ({aging_duration}分钟)"
            if aging_duration is not None
            else "老化测试 (配置文件)"
        )
        results.append(
            (aging_label, *run_aging_tests(aging_duration, pytest_mode, env=env))
        )

    return results


def run_quick_tests(
    pytest_mode: bool = False, env: Optional[Dict[str, str]] = None
) -> List[Tuple[str, bool, float]]:
    """运行快速测试（仅框架验证）"""
    logger.info("运行快速测试")

    results = []
    results.append(("框架验证测试", *run_validation_tests(pytest_mode, env=env)))

    return results


def generate_report(results: List[Tuple[str, bool, float]]) -> None:
    logger.info("\n%s", "=" * 60)
    logger.info("测试执行报告")
    logger.info("%s", "=" * 60)

    total_tests = len(results)
    passed_tests = sum(1 for _, success, _ in results if success)
    failed_tests = total_tests - passed_tests
    total_time = sum(elapsed for _, _, elapsed in results)

    logger.info("总测试套件: %s", total_tests)
    logger.info("通过: %s", passed_tests)
    logger.info("失败: %s", failed_tests)
    logger.info("总耗时: %.2f秒", total_time)

    if total_tests > 0:
        logger.info("通过率: %.1f%%", passed_tests / total_tests * 100)

    logger.info("详细结果:")
    for test_name, success, elapsed in results:
        status = "通过" if success else "失败"
        logger.info("  %s: %s (%.2f秒)", test_name, status, elapsed)

    if failed_tests > 0:
        logger.warning("失败的测试:")
        for test_name, success, _ in results:
            if not success:
                logger.warning("  - %s", test_name)

    logger.info("报告生成时间: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def check_config_status() -> None:
    """检查配置状态"""
    logger.info("检查配置状态")

    logger.info("配置文件: %s", CONFIG_FILE)
    if os.path.exists(CONFIG_FILE):
        config = load_config()
        logger.info("运行模式: %s", config.get("mode", "N/A"))
        logger.info("环境: %s", config.get("environment", "N/A"))
        logger.info("默认租户: %s", config.get("default_tenant", "N/A"))
        logger.info("服务器: %s", config.get("default_server_url", "N/A"))
        logger.info(
            "目标租户: %s",
            ", ".join(config.get("tenant_targets", [])) or "未启用多租户",
        )
        target = config.get("target", {})
        observability = config.get("observability", {})
        if target:
            logger.info("远端主机: %s@%s", target.get("remote_user", ""), target.get("remote_host", ""))
            logger.info("部署形态: %s", target.get("deployment_mode", "N/A"))
        if observability:
            logger.info("Prometheus: %s", observability.get("prometheus_url", "N/A"))
    else:
        logger.warning("配置文件不存在")


def main():
    parser = argparse.ArgumentParser(
        description="VMI 统一测试入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python3 run_tests.py --all           # 运行所有测试（不含老化）
    python3 run_tests.py --all --include-aging      # 全量+配置文件老化测试
    python3 run_tests.py --all --aging 30           # 全量+30分钟老化测试
    python3 run_tests.py --quick         # 快速验证
    python3 run_tests.py --validation    # 框架验证测试
    python3 run_tests.py --module        # 模块测试
    python3 run_tests.py --concurrent    # 并发测试
    python3 run_tests.py --hotspot       # 多租户热点压测
    python3 run_tests.py --hotspot --workers-per-tenant 12 --iterations-per-worker 20 --report-file hotspot-report.json
    python3 run_tests.py --scenario      # 场景测试
    python3 run_tests.py --aging 30      # 30分钟老化测试
    python3 run_tests.py --multi-tenant  # 多租户测试
    python3 run_tests.py --pytest --all  # 使用 pytest 运行所有测试
        """,
    )

    parser.add_argument("--all", action="store_true", help="运行所有测试")
    parser.add_argument("--quick", action="store_true", help="运行快速测试（框架验证）")
    parser.add_argument("--validation", action="store_true", help="运行框架验证测试")
    parser.add_argument("--concurrent", action="store_true", help="运行并发测试")
    parser.add_argument("--hotspot", action="store_true", help="运行多租户热点压测")
    parser.add_argument("--scenario", action="store_true", help="运行场景测试")
    parser.add_argument(
        "--aging",
        type=int,
        metavar="MINUTES",
        help="运行老化测试；若与 --all 联用，则将老化测试加入全量回归",
    )
    parser.add_argument(
        "--include-aging",
        action="store_true",
        help="与 --all 联用，在全量回归中包含老化测试（默认使用配置文件时长）",
    )
    parser.add_argument("--multi-tenant", action="store_true", help="运行多租户测试")
    parser.add_argument("--module", action="store_true", help="运行模块测试")
    parser.add_argument("--pytest", action="store_true", help="使用 pytest 运行测试")
    parser.add_argument("--check-config", action="store_true", help="检查配置状态")
    parser.add_argument("--report-file", help="将并发压测结果写入 JSON 报告文件")
    parser.add_argument("--repeat", type=int, default=1, help="重复执行热点压测轮次")
    parser.add_argument("--server-url", dest="server_url", help="临时覆盖服务地址")
    parser.add_argument("--tenant-targets", help="临时覆盖租户列表，格式 t001,t002")
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
        help="热点压测每个 worker 独立上下文",
    )
    parser.add_argument(
        "--measure-loop-only",
        dest="hotspot_measure_loop_only",
        action="store_true",
        default=None,
        help="热点压测只统计循环窗口",
    )
    parser.add_argument(
        "--include-setup-time",
        dest="hotspot_measure_loop_only",
        action="store_false",
        help="热点压测耗时包含准备和预热阶段",
    )
    parser.add_argument(
        "--prometheus-url",
        dest="prometheus_url",
        help="记录压测对应的 Prometheus 入口",
    )
    parser.add_argument(
        "--remote-host",
        dest="remote_host",
        help="记录压测目标远端主机",
    )
    parser.add_argument(
        "--remote-user",
        dest="remote_user",
        help="记录压测目标 SSH 用户",
    )
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

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    logger.info("VMI 测试系统")
    logger.info("%s", "=" * 60)
    logger.info("运行模式: %s", "pytest" if args.pytest else "unittest")
    logger.info("配置文件: %s", CONFIG_FILE)
    logger.info("%s", "=" * 60)
    runtime_overrides = summarize_runtime_overrides(args)
    runtime_env = build_runtime_env(args)
    if runtime_overrides:
        logger.info("运行时覆盖: %s", runtime_overrides)

    results = []

    if args.check_config:
        check_config_status()
        return

    if args.all:
        include_aging = args.include_aging or args.aging is not None
        results = run_all_tests(
            args.pytest,
            include_aging=include_aging,
            aging_duration=args.aging,
            env=runtime_env,
        )
    elif args.quick:
        results = run_quick_tests(args.pytest, env=runtime_env)
    else:
        if args.validation:
            results.append(
                ("框架验证测试", *run_validation_tests(args.pytest, env=runtime_env))
            )
        if args.concurrent:
            results.append(
                (
                    "并发测试",
                    *run_concurrent_tests(args.pytest, env=runtime_env, cli_args=args),
                )
            )
        if args.hotspot:
            results.append(
                (
                    "多租户热点压测",
                    *run_hotspot_tests(args.pytest, env=runtime_env, cli_args=args),
                )
            )
        if args.scenario:
            results.append(("场景测试", *run_scenario_tests(args.pytest, env=runtime_env)))
        if args.aging is not None:
            results.append(
                (
                    f"老化测试 ({args.aging}分钟)",
                    *run_aging_tests(args.aging, args.pytest, env=runtime_env),
                )
            )
        if args.multi_tenant:
            results.append(
                ("多租户测试", *run_multi_tenant_tests(args.pytest, env=runtime_env))
            )
        if args.module:
            results.append(("模块测试", *run_module_tests(args.pytest, env=runtime_env)))

    if results:
        generate_report(results)

        failed_tests = [name for name, success, _ in results if not success]
        if failed_tests:
            logger.error("以下测试失败: %s", ", ".join(failed_tests))
            sys.exit(1)
        else:
            logger.info("所有测试通过")
            sys.exit(0)
    else:
        logger.warning("没有执行任何测试")


if __name__ == "__main__":
    main()
