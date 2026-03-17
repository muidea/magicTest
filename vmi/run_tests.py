#!/usr/bin/env python3
"""
VMI 统一测试入口
整合所有测试运行模式，支持 unittest 和 pytest

使用方法：
    python3 run_tests.py --all           # 运行所有测试
    python3 run_tests.py --quick         # 快速验证
    python3 run_tests.py --concurrent    # 并发测试
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
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "test_config.json")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("配置文件不存在: %s", CONFIG_FILE)
        return {}


def run_command(cmd: str, description: str = "") -> Tuple[bool, float]:
    logger.info("\n%s", "=" * 60)
    logger.info("执行: %s", description)
    logger.info("命令: %s", cmd)
    logger.info("%s", "=" * 60)

    start_time = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
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
    pytest_args: List[str], description: str = ""
) -> Tuple[bool, float]:
    cmd = "pytest " + " ".join(pytest_args)
    return run_command(cmd, description)


def run_validation_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行框架验证测试（包含基础功能和会话管理验证）"""
    logger.info("运行框架验证测试")

    if pytest_mode:
        return run_pytest_command(
            ["test_complete_validation.py", "-v", "--tb=short"], "框架验证测试 (pytest)"
        )

    cmd = "python3 test_complete_validation.py"
    return run_command(cmd, "框架验证测试")


def run_multi_tenant_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
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
        )

    cmd = "python3 test_multi_tenant.py"
    return run_command(cmd, "多租户测试")


def run_concurrent_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行并发测试"""
    logger.info("运行并发测试")

    if pytest_mode:
        return run_pytest_command(
            ["concurrent_test_v2.py", "-v", "--tb=short"], "并发测试 (pytest)"
        )

    cmd = "python3 concurrent_test_v2.py"
    return run_command(cmd, "并发测试")


def run_scenario_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行场景测试"""
    logger.info("运行场景测试")

    if pytest_mode:
        return run_pytest_command(
            ["scenario_test.py", "-v", "--tb=short"], "场景测试 (pytest)"
        )

    cmd = "python3 scenario_test.py"
    return run_command(cmd, "场景测试")


def run_aging_tests(
    duration: Optional[int] = None, pytest_mode: bool = False
) -> Tuple[bool, float]:
    """运行老化测试"""
    if duration is None:
        logger.info("运行老化测试（使用配置文件时长）")
        if pytest_mode:
            cmd = "python3 aging_test_simple.py --threads 2"
            return run_command(cmd, "老化测试 (配置文件) - 轻量模式")

        cmd = "python3 aging_test_simple.py"
        return run_command(cmd, "老化测试 (配置文件)")

    logger.info("运行老化测试（%s分钟）", duration)
    duration_hours = duration / 60.0

    if pytest_mode:
        cmd = (
            "python3 aging_test_simple.py "
            f"--duration {duration_hours} --threads 2"
        )
        return run_command(cmd, f"老化测试 ({duration}分钟) - 轻量模式")

    cmd = f"python3 aging_test_simple.py --duration {duration_hours}"
    return run_command(cmd, f"老化测试 ({duration}分钟)")


def run_module_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
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
        )

    cmd = "python3 -m unittest discover -s . -p '*_test.py' -v"
    return run_command(cmd, "模块测试")


def run_all_tests(
    pytest_mode: bool = False,
    include_aging: bool = False,
    aging_duration: Optional[int] = None,
) -> List[Tuple[str, bool, float]]:
    """运行所有测试"""
    logger.info("运行所有测试")

    results = []

    results.append(("框架验证测试", *run_validation_tests(pytest_mode)))
    results.append(("多租户测试", *run_multi_tenant_tests(pytest_mode)))
    results.append(("并发测试", *run_concurrent_tests(pytest_mode)))
    results.append(("场景测试", *run_scenario_tests(pytest_mode)))
    results.append(("模块测试", *run_module_tests(pytest_mode)))
    if include_aging:
        aging_label = (
            f"老化测试 ({aging_duration}分钟)"
            if aging_duration is not None
            else "老化测试 (配置文件)"
        )
        results.append((aging_label, *run_aging_tests(aging_duration, pytest_mode)))

    return results


def run_quick_tests(pytest_mode: bool = False) -> List[Tuple[str, bool, float]]:
    """运行快速测试（仅框架验证）"""
    logger.info("运行快速测试")

    results = []
    results.append(("框架验证测试", *run_validation_tests(pytest_mode)))

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
        logger.info("服务器: %s", config.get("server", {}).get("url", "N/A"))
        logger.info(
            "命名空间: %s", config.get("server", {}).get("namespace", "N/A")
        )
        logger.info("环境: %s", config.get("server", {}).get("environment", "N/A"))
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

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    logger.info("VMI 测试系统")
    logger.info("%s", "=" * 60)
    logger.info("运行模式: %s", "pytest" if args.pytest else "unittest")
    logger.info("配置文件: %s", CONFIG_FILE)
    logger.info("%s", "=" * 60)

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
        )
    elif args.quick:
        results = run_quick_tests(args.pytest)
    else:
        if args.validation:
            results.append(("框架验证测试", *run_validation_tests(args.pytest)))
        if args.concurrent:
            results.append(("并发测试", *run_concurrent_tests(args.pytest)))
        if args.scenario:
            results.append(("场景测试", *run_scenario_tests(args.pytest)))
        if args.aging is not None:
            results.append(
                (
                    f"老化测试 ({args.aging}分钟)",
                    *run_aging_tests(args.aging, args.pytest),
                )
            )
        if args.multi_tenant:
            results.append(("多租户测试", *run_multi_tenant_tests(args.pytest)))
        if args.module:
            results.append(("模块测试", *run_module_tests(args.pytest)))

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
