#!/usr/bin/env python3
"""
pytest测试运行器

提供与原有测试运行器兼容的pytest接口，支持：
1. 原有命令行参数
2. pytest高级特性
3. 测试报告生成
4. 性能监控集成
"""

import os
import sys
import argparse
import subprocess
import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

def run_pytest_command(pytest_args: List[str], description: str = "") -> bool:
    """运行pytest命令
    
    Args:
        pytest_args: pytest命令行参数
        description: 命令描述
        
    Returns:
        命令是否成功
    """
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: pytest {' '.join(pytest_args)}")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    try:
        # 构建完整命令
        cmd = ["pytest"] + pytest_args
        
        # 运行命令
        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.time() - start_time
        
        # 输出结果
        if result.stdout:
            print("输出:")
            print(result.stdout)
        
        if result.stderr:
            print("错误:")
            print(result.stderr)
        
        print(f"\n执行时间: {elapsed:.2f}秒")
        print(f"返回码: {result.returncode}")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"执行命令时出错: {e}")
        return False


def run_basic_tests_pytest() -> bool:
    """运行基础测试 - pytest版本"""
    print("\n📋 运行基础测试套件 (pytest)")
    print("这将运行所有基础测试，验证系统基本功能")
    
    pytest_args = [
        "-m", "basic",           # 只运行标记为basic的测试
        "-v",                    # 详细输出
        "--tb=short",            # 简短回溯
        "--durations=5",         # 显示最慢的5个测试
    ]
    
    return run_pytest_command(pytest_args, "基础测试套件")


def run_session_manager_test_pytest() -> bool:
    """运行会话管理器测试 - pytest版本"""
    print("\n🔐 运行会话管理器测试 (pytest)")
    print("这将验证会话管理器的自动刷新功能")
    
    pytest_args = [
        "-m", "session",         # 只运行标记为session的测试
        "-v",
        "--tb=short",
    ]
    
    return run_pytest_command(pytest_args, "会话管理器测试")


def run_concurrent_test_pytest() -> bool:
    """运行并发测试 - pytest版本"""
    print("\n⚡ 运行并发测试 (pytest)")
    print("这将测试系统在并发访问下的表现")
    
    pytest_args = [
        "-m", "concurrent",      # 只运行标记为concurrent的测试
        "-v",
        "--tb=short",
        "--html=concurrent_test_report.html",  # 生成HTML报告
        "--self-contained-html",
    ]
    
    return run_pytest_command(pytest_args, "并发测试")


def run_scenario_test_pytest() -> bool:
    """运行场景测试 - pytest版本"""
    print("\n🎭 运行场景测试 (pytest)")
    print("这将测试完整的业务场景")
    
    pytest_args = [
        "-m", "scenario",        # 只运行标记为scenario的测试
        "-v",
        "--tb=short",
        "--html=scenario_test_report.html",
        "--self-contained-html",
    ]
    
    return run_pytest_command(pytest_args, "场景测试")


def run_aging_test_pytest(duration: int = 60) -> bool:
    """运行老化测试 - pytest版本
    
    Args:
        duration: 测试持续时间（分钟）
    """
    print(f"\n⏳ 运行老化测试 (pytest) - 持续时间: {duration}分钟")
    print("这将测试系统在长时间运行下的稳定性")
    
    # 支持最短1分钟测试
    if duration < 1:
        duration = 1
    
    # 将分钟转换为小时（支持小数）
    duration_hours = duration / 60.0
    
    # 设置环境变量传递给测试
    os.environ['AGING_TEST_DURATION'] = str(duration_hours)
    os.environ['AGING_TEST_THREADS'] = '2'
    
    pytest_args = [
        "-m", "aging",           # 只运行标记为aging的测试
        "-v",
        "--tb=short",
        f"--html=aging_test_{duration}min_report.html",
        "--self-contained-html",
    ]
    
    success = run_pytest_command(pytest_args, f"老化测试 ({duration}分钟)")
    
    # 清理环境变量
    os.environ.pop('AGING_TEST_DURATION', None)
    os.environ.pop('AGING_TEST_THREADS', None)
    
    return success


def run_product_delete_test_pytest() -> bool:
    """运行product.delete测试 - pytest版本"""
    print("\n🗑️ 运行product.delete操作测试 (pytest)")
    print("这将验证product.delete操作的正常行为")
    
    # 这里可以添加特定的product.delete测试
    # 目前先运行所有产品相关测试
    pytest_args = [
        "-k", "product",         # 运行名称包含product的测试
        "-v",
        "--tb=short",
    ]
    
    return run_pytest_command(pytest_args, "product.delete操作测试")


def run_long_running_test_pytest() -> bool:
    """运行长时间运行测试 - pytest版本"""
    print("\n⏱️ 运行长时间运行测试 (pytest)")
    print("这将测试会话在长时间操作中的保持能力")
    
    # 使用老化测试代替长时间运行测试
    return run_aging_test_pytest(5)  # 5分钟测试


def run_all_tests_pytest() -> bool:
    """运行所有测试 - pytest版本"""
    print("\n🔍 运行所有测试 (pytest)")
    print("这将运行所有标记的测试")
    
    pytest_args = [
        "-v",
        "--tb=short",
        "--html=all_tests_report.html",
        "--self-contained-html",
        "--cov=.",               # 代码覆盖率
        "--cov-report=html",
        "--cov-report=term",
    ]
    
    return run_pytest_command(pytest_args, "所有测试")


def run_quick_test_pytest() -> bool:
    """运行快速测试 - pytest版本"""
    print("\n⚡ 运行快速测试 (pytest)")
    print("这将运行基础测试和会话管理器测试")
    
    pytest_args = [
        "-m", "basic or session",  # 运行basic或session标记的测试
        "-v",
        "--tb=short",
        "--html=quick_test_report.html",
        "--self-contained-html",
    ]
    
    return run_pytest_command(pytest_args, "快速测试")


def generate_pytest_report(results: List[tuple], performance_file: Optional[str] = None):
    """生成pytest测试报告
    
    Args:
        results: 测试结果列表 [(test_name, success), ...]
        performance_file: 性能报告文件路径
    """
    print("\n" + "="*60)
    print("📊 pytest测试执行报告")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    failed_tests = total_tests - passed_tests
    
    print(f"总测试套件: {total_tests}")
    print(f"通过: {passed_tests}")
    print(f"失败: {failed_tests}")
    print(f"通过率: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "通过率: N/A")
    
    print("\n详细结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    # 如果有性能报告文件，显示性能摘要
    if performance_file and os.path.exists(performance_file):
        try:
            with open(performance_file, 'r') as f:
                perf_data = json.load(f)
            
            print(f"\n{'='*60}")
            print("📈 性能摘要")
            print(f"{'='*60}")
            
            summary = perf_data.get('summary', {})
            print(f"总执行时间: {summary.get('total_duration', 0):.2f}秒")
            print(f"平均测试时间: {summary.get('average_duration', 0):.2f}秒")
            print(f"总API调用: {summary.get('total_api_calls', 0)}")
            print(f"总体成功率: {summary.get('overall_success_rate', 0):.1f}%")
            
        except Exception as e:
            print(f"\n⚠️ 读取性能报告时出错: {e}")
    
    print(f"\n报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 保存报告到文件
    report_file = f"pytest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "pass_rate": passed_tests/total_tests*100 if total_tests > 0 else 0
        },
        "results": [
            {"test_name": name, "status": "passed" if success else "failed"}
            for name, success in results
        ]
    }
    
    try:
        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f"📄 详细报告已保存到: {report_file}")
    except Exception as e:
        print(f"⚠️ 保存报告文件时出错: {e}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="pytest测试运行器 - 兼容原有接口")
    parser.add_argument("--all", action="store_true", help="运行所有测试")
    parser.add_argument("--basic", action="store_true", help="运行基础测试")
    parser.add_argument("--aging", type=int, metavar="MINUTES", help="运行老化测试，指定持续时间（分钟），支持最短1分钟")
    parser.add_argument("--session", action="store_true", help="运行会话管理器测试")
    parser.add_argument("--long", action="store_true", help="运行长时间运行测试")
    parser.add_argument("--product", action="store_true", help="运行product.delete测试")
    parser.add_argument("--concurrent", action="store_true", help="运行并发测试")
    parser.add_argument("--scenario", action="store_true", help="运行场景测试")
    parser.add_argument("--quick", action="store_true", help="快速测试（基础+会话）")
    parser.add_argument("--performance", action="store_true", help="启用性能监控")
    parser.add_argument("--report", type=str, metavar="FILE", help="保存性能报告到指定文件")
    parser.add_argument("--pytest-only", action="store_true", help="只运行pytest测试，不运行原有测试")
    
    args = parser.parse_args()
    
    # 如果没有指定任何选项，显示帮助
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    print("🚀 VMI测试系统 - pytest测试运行器")
    print("="*60)
    print("基于pytest的现代化测试架构")
    print("支持原有命令行参数，提供更好的测试体验")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    if args.all:
        print("🔍 运行所有测试...")
        results.append(("基础测试", run_basic_tests_pytest()))
        results.append(("会话管理器测试", run_session_manager_test_pytest()))
        results.append(("长时间运行测试", run_long_running_test_pytest()))
        results.append(("product.delete测试", run_product_delete_test_pytest()))
        results.append(("并发测试", run_concurrent_test_pytest()))
        results.append(("场景测试", run_scenario_test_pytest()))
        if args.aging:
            results.append((f"老化测试 ({args.aging}分钟)", run_aging_test_pytest(args.aging)))
    
    # 运行快速测试
    elif args.quick:
        print("⚡ 运行快速测试...")
        results.append(("基础测试", run_basic_tests_pytest()))
        results.append(("会话管理器测试", run_session_manager_test_pytest()))
    
    # 运行单个测试
    else:
        if args.basic:
            results.append(("基础测试", run_basic_tests_pytest()))
        if args.session:
            results.append(("会话管理器测试", run_session_manager_test_pytest()))
        if args.long:
            results.append(("长时间运行测试", run_long_running_test_pytest()))
        if args.product:
            results.append(("product.delete测试", run_product_delete_test_pytest()))
        if args.concurrent:
            results.append(("并发测试", run_concurrent_test_pytest()))
        if args.scenario:
            results.append(("场景测试", run_scenario_test_pytest()))
        if args.aging:
            results.append((f"老化测试 ({args.aging}分钟)", run_aging_test_pytest(args.aging)))
    
    # 生成报告
    if results:
        performance_file = args.report if args.report else ("performance_report.json" if args.performance else None)
        generate_pytest_report(results, performance_file)
        
        # 检查是否有失败
        failed_tests = [name for name, success in results if not success]
        if failed_tests:
            print(f"\n⚠️ 注意: 以下测试失败: {', '.join(failed_tests)}")
            sys.exit(1)
        else:
            print("\n🎉 所有测试通过!")
            sys.exit(0)
    else:
        print("没有执行任何测试")


if __name__ == "__main__":
    main()