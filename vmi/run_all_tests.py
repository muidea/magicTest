#!/usr/bin/env python3
"""
统一的测试运行脚本
提供多种测试执行选项，简化测试管理
"""

import os
import sys
import argparse
import subprocess
import time
import json
from datetime import datetime

def run_command(cmd, description=""):
    """运行命令并显示输出"""
    print(f"\n{'='*60}")
    print(f"执行: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*60}")
    
    start_time = time.time()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        elapsed = time.time() - start_time
        
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

def run_basic_tests():
    """运行基础测试套件"""
    print("\n📋 运行基础测试套件")
    print("这将运行所有基础测试，验证系统基本功能")
    
    # 激活虚拟环境
    venv_activate = "source ~/codespace/venv/bin/activate"
    
    # 运行无错误日志的测试
    cmd = f"{venv_activate} && python3 run_tests_without_errors.py"
    return run_command(cmd, "基础测试套件")

def run_aging_test(duration=60):
    """运行老化测试"""
    print(f"\n⏳ 运行老化测试 (持续时间: {duration}分钟)")
    print("这将测试系统在长时间运行下的稳定性")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 aging_test_simple.py --duration {duration}"
    return run_command(cmd, f"老化测试 ({duration}分钟)")

def run_session_manager_test():
    """运行会话管理器测试"""
    print("\n🔐 运行会话管理器测试")
    print("这将验证会话管理器的自动刷新功能")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 test_session_manager.py"
    return run_command(cmd, "会话管理器测试")

def run_long_running_test():
    """运行长时间运行测试"""
    print("\n⏱️ 运行长时间运行测试")
    print("这将测试会话在长时间操作中的保持能力")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 test_long_running_with_session.py"
    return run_command(cmd, "长时间运行测试")

def run_product_delete_test():
    """运行product.delete操作测试"""
    print("\n🗑️ 运行product.delete操作测试")
    print("这将验证product.delete操作的正常行为")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 test_product_delete_final.py"
    return run_command(cmd, "product.delete操作测试")

def run_concurrent_test():
    """运行并发测试"""
    print("\n⚡ 运行并发测试")
    print("这将测试系统在并发访问下的表现")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 concurrent_test.py"
    return run_command(cmd, "并发测试")

def run_scenario_test():
    """运行场景测试"""
    print("\n🎭 运行场景测试")
    print("这将测试完整的业务场景")
    
    venv_activate = "source ~/codespace/venv/bin/activate"
    cmd = f"{venv_activate} && python3 scenario_test.py"
    return run_command(cmd, "场景测试")

def generate_report(results, performance_file=None):
    """生成测试报告"""
    print("\n" + "="*60)
    print("📊 测试执行报告")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    failed_tests = total_tests - passed_tests
    
    print(f"总测试数: {total_tests}")
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
            
            # 显示建议
            recommendations = perf_data.get('recommendations', {})
            if any(recommendations.values()):
                print(f"\n💡 性能建议:")
                
                if recommendations.get('slow_tests'):
                    print(f"  ⚠️  较慢测试: {', '.join(recommendations['slow_tests'])}")
                
                if recommendations.get('high_memory_tests'):
                    print(f"  ⚠️  高内存测试: {', '.join(recommendations['high_memory_tests'])}")
                
                if recommendations.get('low_success_tests'):
                    print(f"  ⚠️  低成功率测试: {', '.join(recommendations['low_success_tests'])}")
        
        except Exception as e:
            print(f"\n⚠️  读取性能报告时出错: {e}")
    
    print(f"\n报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 保存报告到文件
    report_file = f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
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
        print(f"⚠️  保存报告文件时出错: {e}")

def main():
    parser = argparse.ArgumentParser(description="统一的测试运行脚本")
    parser.add_argument("--all", action="store_true", help="运行所有测试")
    parser.add_argument("--basic", action="store_true", help="运行基础测试")
    parser.add_argument("--aging", type=int, metavar="MINUTES", help="运行老化测试，指定持续时间（分钟）")
    parser.add_argument("--session", action="store_true", help="运行会话管理器测试")
    parser.add_argument("--long", action="store_true", help="运行长时间运行测试")
    parser.add_argument("--product", action="store_true", help="运行product.delete测试")
    parser.add_argument("--concurrent", action="store_true", help="运行并发测试")
    parser.add_argument("--scenario", action="store_true", help="运行场景测试")
    parser.add_argument("--quick", action="store_true", help="快速测试（基础+会话）")
    parser.add_argument("--performance", action="store_true", help="启用性能监控")
    parser.add_argument("--report", type=str, metavar="FILE", help="保存性能报告到指定文件")
    
    args = parser.parse_args()
    
    # 如果没有指定任何选项，显示帮助
    if not any(vars(args).values()):
        parser.print_help()
        return
    
    print("🚀 VMI测试系统 - 统一测试运行器")
    print("="*60)
    
    results = []
    
    # 运行所有测试
    if args.all:
        print("🔍 运行所有测试...")
        results.append(("基础测试", run_basic_tests()))
        results.append(("会话管理器测试", run_session_manager_test()))
        results.append(("长时间运行测试", run_long_running_test()))
        results.append(("product.delete测试", run_product_delete_test()))
        results.append(("并发测试", run_concurrent_test()))
        results.append(("场景测试", run_scenario_test()))
        if args.aging:
            results.append((f"老化测试 ({args.aging}分钟)", run_aging_test(args.aging)))
    
    # 运行快速测试
    elif args.quick:
        print("⚡ 运行快速测试...")
        results.append(("基础测试", run_basic_tests()))
        results.append(("会话管理器测试", run_session_manager_test()))
    
    # 运行单个测试
    else:
        if args.basic:
            results.append(("基础测试", run_basic_tests()))
        if args.session:
            results.append(("会话管理器测试", run_session_manager_test()))
        if args.long:
            results.append(("长时间运行测试", run_long_running_test()))
        if args.product:
            results.append(("product.delete测试", run_product_delete_test()))
        if args.concurrent:
            results.append(("并发测试", run_concurrent_test()))
        if args.scenario:
            results.append(("场景测试", run_scenario_test()))
        if args.aging:
            results.append((f"老化测试 ({args.aging}分钟)", run_aging_test(args.aging)))
    
    # 生成报告
    if results:
        performance_file = args.report if args.report else ("performance_report.json" if args.performance else None)
        generate_report(results, performance_file)
        
        # 检查是否有失败
        failed_tests = [name for name, success in results if not success]
        if failed_tests:
            print(f"\n⚠️  注意: 以下测试失败: {', '.join(failed_tests)}")
            sys.exit(1)
        else:
            print("\n🎉 所有测试通过!")
            sys.exit(0)
    else:
        print("没有执行任何测试")

if __name__ == "__main__":
    main()