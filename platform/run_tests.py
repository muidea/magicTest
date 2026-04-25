#!/usr/bin/env python3
"""magicTest/platform 统一测试运行器

用法:
    python3 run_tests.py                    # 运行所有平台测试
    python3 run_tests.py --list             # 列出所有可用的测试模块
    python3 run_tests.py --module access_log  # 仅运行指定模块
    python3 run_tests.py --skip-totalizator   # 跳过指定模块
    python3 run_tests.py --verbose           # 详细输出
    python3 run_tests.py --coverage          # 运行后打印覆盖率摘要

环境变量:
    MAGICTEST_PLATFORM_BASE_URL   目标服务地址（默认 https://autotest.local.vpc/api/v1）
    MAGICTEST_PLATFORM_NAMESPACE  命名空间（默认空）
"""

import argparse
import importlib
import logging
import os
import sys
import time
import unittest


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# 平台测试模块注册表
# (模块路径, 显示名, 测试类)
PLATFORM_TEST_MODULES = [
    ("application.application_test", "Application", "ApplicationTestCase"),
    ("block.block_test", "Block", "BlockTestCase"),
    ("entity.entity_test", "Entity", "EntityTestCase"),
    ("value.value_test", "Value", "ValueTestCase"),
    ("access_log.access_log_test", "AccessLog", "AccessLogTestCase"),
    ("operation_log.operation_log_test", "OperationLog", "OperationLogTestCase"),
    ("totalizator.totalizator_test", "Totalizator", "TotalizatorTestCase"),
]


def _add_platform_path():
    """将 platform 父目录和自身加入 sys.path"""
    platform_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(platform_dir)
    for p in (platform_dir, parent_dir):
        if p not in sys.path:
            sys.path.insert(0, p)


def list_modules():
    """列出所有可用的平台测试模块"""
    print("=" * 60)
    print("magicTest/platform 可用测试模块")
    print("=" * 60)
    for mod_path, display_name, class_name in PLATFORM_TEST_MODULES:
        print(f"  {display_name:15s}  {mod_path}")
    print("=" * 60)
    print(f"  共 {len(PLATFORM_TEST_MODULES)} 个测试模块")


def run_single_module(module_name: str, verbose: bool = False) -> bool:
    """运行单个测试模块

    Args:
        module_name: 模块名（支持路径名如 access_log 或 access_log.access_log_test）
        verbose: 是否详细输出

    Returns:
        测试是否全部通过
    """
    # 查找匹配的模块
    matched = []
    for mod_path, display_name, class_name in PLATFORM_TEST_MODULES:
        if module_name in (display_name.lower(), mod_path, class_name.lower()):
            matched.append((mod_path, display_name, class_name))

    if not matched:
        logger.error("未找到匹配模块: %s", module_name)
        logger.info("可用模块: %s",
                     ", ".join(m[0] for m in PLATFORM_TEST_MODULES))
        return False

    all_ok = True
    for mod_path, display_name, class_name in matched:
        _add_platform_path()
        logger.info("=" * 50)
        logger.info("运行模块: %s (%s)", display_name, mod_path)
        logger.info("=" * 50)

        try:
            suite = unittest.TestLoader().loadTestsFromName(
                f"{mod_path}.{class_name}"
            )
            runner = unittest.TextTestRunner(
                verbosity=2 if verbose else 1,
                stream=sys.stdout,
            )
            result = runner.run(suite)
            if not result.wasSuccessful():
                all_ok = False
                logger.error("模块 %s 测试失败", display_name)
        except Exception as e:
            all_ok = False
            logger.error("运行模块 %s 异常: %s", display_name, e)

    return all_ok


def run_all_modules(
    skip_modules: list = None,
    verbose: bool = False,
) -> bool:
    """运行所有平台测试模块

    Args:
        skip_modules: 要跳过的模块名列表
        verbose: 是否详细输出

    Returns:
        所有测试是否全部通过
    """
    skip_modules = skip_modules or []
    all_ok = True
    total_tests = 0
    total_failures = 0
    total_errors = 0
    start_time = time.time()

    _add_platform_path()

    for mod_path, display_name, class_name in PLATFORM_TEST_MODULES:
        if display_name.lower() in skip_modules or mod_path in skip_modules:
            logger.info("跳过模块: %s", display_name)
            continue

        logger.info("正在运行 %s ...", display_name)
        try:
            suite = unittest.TestLoader().loadTestsFromName(
                f"{mod_path}.{class_name}"
            )
            runner = unittest.TextTestRunner(
                verbosity=2 if verbose else 1,
                stream=sys.stdout,
            )
            result = runner.run(suite)
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
            if not result.wasSuccessful():
                all_ok = False
        except Exception as e:
            all_ok = False
            total_errors += 1
            logger.error("加载模块 %s 异常: %s", display_name, e)

    elapsed = time.time() - start_time
    logger.info("=" * 50)
    logger.info("平台测试汇总")
    logger.info("=" * 50)
    logger.info("  总耗时: %.2f 秒", elapsed)
    logger.info("  总用例: %d", total_tests)
    logger.info("  失败数: %d", total_failures)
    logger.info("  错误数: %d", total_errors)
    logger.info("  最终结果: %s", "通过" if all_ok else "失败")
    logger.info("=" * 50)

    return all_ok


def main():
    parser = argparse.ArgumentParser(
        description="magicTest/platform 统一测试运行器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run_tests.py                    # 运行所有平台测试
  python3 run_tests.py --list             # 列出可用模块
  python3 run_tests.py --module access_log  # 仅运行访问日志模块
  python3 run_tests.py --skip totalizator   # 跳过总计器模块
  python3 run_tests.py --verbose           # 详细输出

环境变量:
  MAGICTEST_PLATFORM_BASE_URL   目标服务地址（默认 https://autotest.local.vpc/api/v1）
  MAGICTEST_PLATFORM_NAMESPACE  命名空间（默认空）
        """,
    )
    parser.add_argument(
        "--list", action="store_true", help="列出所有可用的测试模块"
    )
    parser.add_argument(
        "--module", type=str, default=None,
        help="仅运行指定模块（支持模块名、显示名、类名）"
    )
    parser.add_argument(
        "--skip", type=str, default=None,
        help="要跳过的模块，逗号分隔"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="详细输出"
    )
    args = parser.parse_args()

    if args.list:
        list_modules()
        return True

    skip_list = []
    if args.skip:
        skip_list = [s.strip() for s in args.skip.split(",")]

    if args.module:
        return run_single_module(args.module, verbose=args.verbose)
    else:
        return run_all_modules(skip_modules=skip_list, verbose=args.verbose)


if __name__ == "__main__":
    # 关闭 httplib/requests 的调试日志
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    success = main()
    sys.exit(0 if success else 1)
