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
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "test_config.json")


def load_config() -> Dict[str, Any]:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️ 配置文件不存在: {CONFIG_FILE}")
        return {}


def run_command(cmd: str, description: str = "") -> Tuple[bool, float]:
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*60}")

    start_time = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        elapsed = time.time() - start_time

        if result.stdout:
            print(result.stdout)

        if result.stderr and result.returncode != 0:
            print(f"错误: {result.stderr}")

        print(f"\n执行时间: {elapsed:.2f}秒")

        return result.returncode == 0, elapsed
    except Exception as e:
        print(f"执行命令时出错: {e}")
        return False, 0


def run_pytest_command(
    pytest_args: List[str], description: str = ""
) -> Tuple[bool, float]:
    cmd = "pytest " + " ".join(pytest_args)
    return run_command(cmd, description)


def run_validation_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行框架验证测试（包含基础功能和会话管理验证）"""
    print("\n✅ 运行框架验证测试")

    if pytest_mode:
        return run_pytest_command(
            ["test_complete_validation.py", "-v", "--tb=short"], "框架验证测试 (pytest)"
        )

    cmd = "python3 test_complete_validation.py"
    return run_command(cmd, "框架验证测试")


def run_multi_tenant_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行多租户测试"""
    print("\n🏢 运行多租户测试")

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
    print("\n⚡ 运行并发测试")

    if pytest_mode:
        return run_pytest_command(
            ["concurrent_test_v2.py", "-v", "--tb=short"], "并发测试 (pytest)"
        )

    cmd = "python3 concurrent_test_v2.py"
    return run_command(cmd, "并发测试")


def run_scenario_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行场景测试"""
    print("\n🎭 运行场景测试")

    if pytest_mode:
        return run_pytest_command(
            ["scenario_test.py", "-v", "--tb=short"], "场景测试 (pytest)"
        )

    cmd = "python3 scenario_test.py"
    return run_command(cmd, "场景测试")


def run_aging_tests(
    duration: int = 60, pytest_mode: bool = False
) -> Tuple[bool, float]:
    """运行老化测试"""
    print(f"\n⏳ 运行老化测试（{duration}分钟）")

    if pytest_mode:
        os.environ["AGING_TEST_DURATION"] = str(duration / 60.0)
        os.environ["AGING_TEST_THREADS"] = "2"
        success, elapsed = run_pytest_command(
            ["aging_test_simple.py", "-v", "--tb=short"],
            f"老化测试 ({duration}分钟) - pytest",
        )
        os.environ.pop("AGING_TEST_DURATION", None)
        os.environ.pop("AGING_TEST_THREADS", None)
        return success, elapsed

    cmd = f"python3 aging_test_simple.py --duration {duration}"
    return run_command(cmd, f"老化测试 ({duration}分钟)")


def run_module_tests(pytest_mode: bool = False) -> Tuple[bool, float]:
    """运行模块测试"""
    print("\n📦 运行模块测试")

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


def run_all_tests(pytest_mode: bool = False) -> List[Tuple[str, bool, float]]:
    """运行所有测试"""
    print("\n🔍 运行所有测试")

    results = []

    results.append(("框架验证测试", *run_validation_tests(pytest_mode)))
    results.append(("多租户测试", *run_multi_tenant_tests(pytest_mode)))
    results.append(("并发测试", *run_concurrent_tests(pytest_mode)))
    results.append(("场景测试", *run_scenario_tests(pytest_mode)))
    results.append(("模块测试", *run_module_tests(pytest_mode)))

    return results


def run_quick_tests(pytest_mode: bool = False) -> List[Tuple[str, bool, float]]:
    """运行快速测试（仅框架验证）"""
    print("\n⚡ 运行快速测试")

    results = []
    results.append(("框架验证测试", *run_validation_tests(pytest_mode)))

    return results


def generate_report(results: List[Tuple[str, bool, float]]) -> None:
    print("\n" + "=" * 60)
    print("📊 测试执行报告")
    print("=" * 60)

    total_tests = len(results)
    passed_tests = sum(1 for _, success, _ in results if success)
    failed_tests = total_tests - passed_tests
    total_time = sum(elapsed for _, _, elapsed in results)

    print(f"总测试套件: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    print(f"总耗时: {total_time:.2f}秒")

    if total_tests > 0:
        print(f"通过率: {passed_tests/total_tests*100:.1f}%")

    print("\n详细结果:")
    for test_name, success, elapsed in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status} ({elapsed:.2f}秒)")

    if failed_tests > 0:
        print(f"\n⚠️ 失败的测试:")
        for test_name, success, _ in results:
            if not success:
                print(f"  - {test_name}")

    print(f"\n报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def check_config_status() -> None:
    """检查配置状态"""
    print("\n🔍 检查配置状态")

    print(f"配置文件: {CONFIG_FILE}")
    if os.path.exists(CONFIG_FILE):
        config = load_config()
        print(f"服务器: {config.get('server', {}).get('url', 'N/A')}")
        print(f"命名空间: {config.get('server', {}).get('namespace', 'N/A')}")
        print(f"环境: {config.get('server', {}).get('environment', 'N/A')}")
    else:
        print("⚠️ 配置文件不存在")


def main():
    parser = argparse.ArgumentParser(
        description="VMI 统一测试入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    python3 run_tests.py --all           # 运行所有测试
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
    parser.add_argument("--aging", type=int, metavar="MINUTES", help="运行老化测试")
    parser.add_argument("--multi-tenant", action="store_true", help="运行多租户测试")
    parser.add_argument("--module", action="store_true", help="运行模块测试")
    parser.add_argument("--pytest", action="store_true", help="使用 pytest 运行测试")
    parser.add_argument("--check-config", action="store_true", help="检查配置状态")

    args = parser.parse_args()

    if not any(vars(args).values()):
        parser.print_help()
        return

    print("🚀 VMI 测试系统")
    print("=" * 60)
    print(f"运行模式: {'pytest' if args.pytest else 'unittest'}")
    print(f"配置文件: {CONFIG_FILE}")
    print("=" * 60)

    results = []

    if args.check_config:
        check_config_status()
        return

    if args.all:
        results = run_all_tests(args.pytest)
    elif args.quick:
        results = run_quick_tests(args.pytest)
    else:
        if args.validation:
            results.append(("框架验证测试", *run_validation_tests(args.pytest)))
        if args.concurrent:
            results.append(("并发测试", *run_concurrent_tests(args.pytest)))
        if args.scenario:
            results.append(("场景测试", *run_scenario_tests(args.pytest)))
        if args.aging:
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
            print(f"\n❌ 以下测试失败: {', '.join(failed_tests)}")
            sys.exit(1)
        else:
            print("\n🎉 所有测试通过!")
            sys.exit(0)
    else:
        print("没有执行任何测试")


if __name__ == "__main__":
    main()
