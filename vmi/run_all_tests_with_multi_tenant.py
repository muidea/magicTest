#!/usr/bin/env python3
"""
支持多租户的统一测试运行脚本
扩展原有的测试运行器以支持多租户测试
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

def check_multi_tenant_config():
    """检查多租户配置状态"""
    print("\n🔍 检查多租户配置状态")
    
    cmd = """python3 -c "
import json
try:
    with open('test_config.json', 'r') as f:
        config = json.load(f)
    
    print('📋 配置文件内容:')
    print(json.dumps(config, indent=2, ensure_ascii=False))
    
    # 检查多租户配置
    if 'multi_tenant' in config:
        mt_config = config['multi_tenant']
        print(f'\\n✅ 找到多租户配置')
        print(f'   启用状态: {mt_config.get(\"enabled\", False)}')
        print(f'   默认租户: {mt_config.get(\"default_tenant\", \"autotest\")}')
        
        tenants = mt_config.get('tenants', [])
        print(f'   租户数量: {len(tenants)}')
        
        enabled_tenants = [t for t in tenants if t.get('enabled', True)]
        print(f'   启用租户: {len(enabled_tenants)}')
        
        for tenant in enabled_tenants:
            print(f'     - {tenant.get(\"id\", \"unknown\")}: {tenant.get(\"server_url\", \"N/A\")}')
    else:
        print('\\nℹ️  未找到多租户配置，使用单租户模式')
        
    # 测试配置助手
    try:
        from tenant_config_helper import get_multi_tenant_config, is_multi_tenant_enabled
        mt_config = get_multi_tenant_config()
        print(f'\\n✅ 多租户配置助手工作正常')
        print(f'   多租户启用: {is_multi_tenant_enabled()}')
        print(f'   默认租户: {mt_config.get("default_tenant", "autotest")}')
        print(f'   租户数量: {len(mt_config.get("tenants", {}))}')
    except ImportError as e:
        print(f'\\n⚠️  多租户配置助手导入失败: {e}')
        print('   请确保已安装多租户模块')
        
except FileNotFoundError:
    print('❌ 配置文件不存在')
    print('   请创建test_config.json或使用模板')
    print('   cp test_config_multi_tenant_template.json test_config.json')
except Exception as e:
    print(f'❌ 配置检查失败: {e}')
"
"""
    return run_command(cmd, "多租户配置检查")

def run_multi_tenant_validation():
    """运行多租户验证测试"""
    print("\n🧪 运行多租户验证测试")
    print("这将验证多租户框架的核心功能")
    
    cmd = "python3 test_final_validation.py"
    return run_command(cmd, "多租户框架验证测试")

def run_multi_tenant_example():
    """运行多租户示例测试"""
    print("\n📚 运行多租户示例测试")
    print("这将演示多租户测试的基本用法")
    
    cmd = "python3 test_multi_tenant_example.py"
    return run_command(cmd, "多租户示例测试")

def run_multi_tenant_config_validation():
    """运行多租户配置验证测试"""
    print("\n⚙️ 运行多租户配置验证测试")
    print("这将验证多租户配置系统的正确性")
    
    cmd = "python3 test_multi_tenant_config_validation.py"
    return run_command(cmd, "多租户配置验证测试")

def run_multi_tenant_basic():
    """运行多租户基础测试"""
    print("\n🏗️ 运行多租户基础测试")
    print("这将测试多租户环境下的基础功能")
    
    # 检查是否启用了多租户
    cmd = """python3 -c "
try:
    from tenant_config_helper import is_multi_tenant_enabled
    if is_multi_tenant_enabled():
        print('✅ 多租户已启用，运行多租户基础测试')
        print('   使用TestBaseMultiTenant作为测试基类')
        print('   支持租户切换和隔离验证')
    else:
        print('ℹ️  多租户未启用，运行标准基础测试')
        print('   使用TestBaseWithSessionManager作为测试基类')
except ImportError:
    print('⚠️  多租户模块未找到，运行标准基础测试')
"
"""
    success = run_command(cmd, "多租户状态检查")
    
    if success:
        # 运行基础测试（兼容多租户和单租户）
        cmd = "python3 -m unittest discover -s . -p '*test*.py' -k 'test_basic' -v"
        return run_command(cmd, "基础测试")
    return False

def run_multi_tenant_concurrent():
    """运行多租户并发测试"""
    print("\n⚡ 运行多租户并发测试")
    print("这将测试多租户环境下的并发访问")
    
    # 检查多租户状态
    cmd = """python3 -c "
try:
    from tenant_config_helper import is_multi_tenant_enabled
    if is_multi_tenant_enabled():
        print('✅ 多租户已启用，运行多租户并发测试')
        print('   支持跨租户的并发操作')
    else:
        print('ℹ️  多租户未启用，运行标准并发测试')
except ImportError:
    print('⚠️  多租户模块未找到，运行标准并发测试')
"
"""
    success = run_command(cmd, "多租户并发状态检查")
    
    if success:
        # 运行并发测试
        cmd = "python3 concurrent_test_simple.py"
        return run_command(cmd, "并发测试")
    return False

def enable_multi_tenant():
    """启用多租户功能"""
    print("\n🔧 启用多租户功能")
    
    # 检查配置文件是否存在
    if not os.path.exists("test_config.json"):
        print("❌ 配置文件不存在")
        print("   请先创建配置文件:")
        print("   cp test_config_multi_tenant_template.json test_config.json")
        return False
    
    # 读取当前配置
    try:
        with open("test_config.json", "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False
    
    # 启用多租户
    if "multi_tenant" not in config:
        config["multi_tenant"] = {
            "enabled": True,
            "default_tenant": "autotest",
            "tenants": [
                {
                    "id": "autotest",
                    "server_url": config.get("server_url", "https://autotest.local.vpc"),
                    "username": config.get("username", "administrator"),
                    "password": config.get("password", "administrator"),
                    "namespace": config.get("namespace", "autotest"),
                    "enabled": True
                }
            ]
        }
    else:
        config["multi_tenant"]["enabled"] = True
    
    # 保存配置
    try:
        with open("test_config.json", "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("✅ 多租户功能已启用")
        print("   配置文件已更新")
        print("   请根据需要添加更多租户配置")
        return True
    except Exception as e:
        print(f"❌ 保存配置文件失败: {e}")
        return False

def disable_multi_tenant():
    """禁用多租户功能"""
    print("\n🔧 禁用多租户功能")
    
    # 检查配置文件是否存在
    if not os.path.exists("test_config.json"):
        print("❌ 配置文件不存在")
        return False
    
    # 读取当前配置
    try:
        with open("test_config.json", "r") as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return False
    
    # 禁用多租户
    if "multi_tenant" in config:
        config["multi_tenant"]["enabled"] = False
        print("✅ 多租户功能已禁用")
    else:
        print("ℹ️  配置文件中未找到多租户配置")
        return True
    
    # 保存配置
    try:
        with open("test_config.json", "w") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print("   配置文件已更新")
        return True
    except Exception as e:
        print(f"❌ 保存配置文件失败: {e}")
        return False

def generate_multi_tenant_report(results, performance_file=None):
    """生成多租户测试报告"""
    print("\n" + "="*60)
    print("📊 多租户测试执行报告")
    print("="*60)
    
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)
    failed_tests = total_tests - passed_tests
    
    print(f"总测试数: {total_tests}")
    print(f"通过数: {passed_tests}")
    print(f"失败数: {failed_tests}")
    print(f"成功率: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "成功率: N/A")
    
    # 显示详细结果
    print("\n📋 详细结果:")
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {status}: {test_name}")
    
    # 检查多租户状态
    try:
        from tenant_config_helper import is_multi_tenant_enabled
        mt_enabled = is_multi_tenant_enabled()
        print(f"\n🔍 多租户状态: {'✅ 已启用' if mt_enabled else 'ℹ️  未启用'}")
    except ImportError:
        print("\n⚠️  无法检测多租户状态: 模块未找到")
    
    # 保存性能报告
    if performance_file:
        try:
            report_data = {
                "timestamp": datetime.now().isoformat(),
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": passed_tests/total_tests*100 if total_tests > 0 else 0,
                "results": [
                    {"test": name, "success": success}
                    for name, success in results
                ]
            }
            
            with open(performance_file, "w") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n📁 性能报告已保存到: {performance_file}")
        except Exception as e:
            print(f"\n⚠️  保存性能报告失败: {e}")
    
    return failed_tests == 0

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="支持多租户的统一测试运行脚本")
    
    # 多租户特定选项
    parser.add_argument("--multi-tenant", action="store_true", help="运行多租户测试")
    parser.add_argument("--mt-check", action="store_true", help="检查多租户配置")
    parser.add_argument("--mt-validate", action="store_true", help="运行多租户验证测试")
    parser.add_argument("--mt-example", action="store_true", help="运行多租户示例测试")
    parser.add_argument("--mt-enable", action="store_true", help="启用多租户功能")
    parser.add_argument("--mt-disable", action="store_true", help="禁用多租户功能")
    
    # 原有选项
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
    parser.add_argument("--report", metavar="FILE", help="保存性能报告到指定文件")
    
    args = parser.parse_args()
    
    print("="*60)
    print("🚀 支持多租户的测试运行器")
    print("="*60)
    
    # 记录开始时间
    start_time = time.time()
    results = []
    
    # 多租户特定操作
    if args.mt_enable:
        results.append(("启用多租户", enable_multi_tenant()))
    elif args.mt_disable:
        results.append(("禁用多租户", disable_multi_tenant()))
    
    # 多租户测试
    if args.mt_check:
        results.append(("多租户配置检查", check_multi_tenant_config()))
    
    if args.mt_validate:
        results.append(("多租户验证测试", run_multi_tenant_validation()))
    
    if args.mt_example:
        results.append(("多租户示例测试", run_multi_tenant_example()))
    
    # 多租户模式下的标准测试
    if args.multi_tenant:
        print("\n🏢 运行多租户测试套件")
        print("="*60)
        
        # 检查多租户配置
        results.append(("多租户配置检查", check_multi_tenant_config()))
        
        # 运行验证测试
        results.append(("多租户框架验证", run_multi_tenant_validation()))
        
        # 运行配置验证
        results.append(("多租户配置验证", run_multi_tenant_config_validation()))
        
        # 运行基础测试
        results.append(("多租户基础测试", run_multi_tenant_basic()))
        
        # 运行并发测试
        results.append(("多租户并发测试", run_multi_tenant_concurrent()))
        
        # 运行示例测试
        results.append(("多租户示例测试", run_multi_tenant_example()))
    
    # 原有测试逻辑（向后兼容）
    elif args.all:
        print("\n📋 运行所有测试")
        print("="*60)
        
        # 检查多租户状态
        results.append(("多租户状态检查", check_multi_tenant_config()))
        
        # 运行基础测试（兼容多租户）
        results.append(("基础测试", run_multi_tenant_basic()))
        
        # 运行会话测试
        from run_all_tests import run_session_manager_test
        results.append(("会话管理器测试", run_session_manager_test()))
        
        # 运行并发测试（兼容多租户）
        results.append(("并发测试", run_multi_tenant_concurrent()))
        
        # 运行场景测试
        from run_all_tests import run_scenario_test
        results.append(("场景测试", run_scenario_test()))
        
        # 运行老化测试
        if args.aging:
            from run_all_tests import run_aging_test
            results.append((f"老化测试 ({args.aging}分钟)", run_aging_test(args.aging)))
    
    elif args.basic:
        results.append(("基础测试", run_multi_tenant_basic()))
    
    elif args.aging:
        from run_all_tests import run_aging_test
        results.append((f"老化测试 ({args.aging}分钟)", run_aging_test(args.aging)))
    
    elif args.session:
        from run_all_tests import run_session_manager_test
        results.append(("会话管理器测试", run_session_manager_test()))
    
    elif args.long:
        from run_all_tests import run_long_running_test
        results.append(("长时间运行测试", run_long_running_test()))
    
    elif args.product:
        from run_all_tests import run_product_delete_test
        results.append(("product.delete测试", run_product_delete_test()))
    
    elif args.concurrent:
        results.append(("并发测试", run_multi_tenant_concurrent()))
    
    elif args.scenario:
        from run_all_tests import run_scenario_test
        results.append(("场景测试", run_scenario_test()))
    
    elif args.quick:
        results.append(("基础测试", run_multi_tenant_basic()))
        from run_all_tests import run_session_manager_test
        results.append(("会话管理器测试", run_session_manager_test()))
    
    else:
        # 默认运行帮助
        parser.print_help()
        return
    
    # 计算总时间
    total_time = time.time() - start_time
    
    # 生成报告
    print("\n" + "="*60)
    print("📈 测试执行摘要")
    print("="*60)
    
    success = generate_multi_tenant_report(results, args.report)
    
    print(f"\n⏱️  总执行时间: {total_time:.2f}秒")
    print("="*60)
    
    if success:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1

if __name__ == "__main__":
    sys.exit(main())