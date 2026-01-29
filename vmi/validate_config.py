#!/usr/bin/env python3
"""
配置验证脚本
用于验证测试配置的有效性
"""

import sys
import os

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from test_config import config

def main():
    """主函数"""
    print("=" * 60)
    print("VMI测试框架 - 配置验证工具")
    print("=" * 60)
    
    # 获取验证报告
    report = config.get_validation_report()
    print(report)
    
    # 检查配置是否有效
    validation = config.validate()
    if not validation['is_valid']:
        print("\n❌ 配置验证失败，请修复以上错误后再运行测试")
        sys.exit(1)
    else:
        print("\n✅ 配置验证通过，可以开始测试")
        
        # 显示版本信息
        version_info = config.get_version_info()
        print("\n版本信息:")
        print("-" * 40)
        print(f"当前系统版本: {version_info['current_version']}")
        print(f"配置版本: {version_info['config_version']}")
        print(f"版本兼容性: {'✓ 兼容' if version_info['is_compatible'] else '✗ 不兼容'}")
        
        # 显示完整配置
        print("\n完整配置信息:")
        print("-" * 40)
        print(config)
        
        # 显示配置来源
        print("\n配置来源:")
        print("-" * 40)
        print("1. 默认配置")
        print("2. 环境变量覆盖")
        print("3. 配置文件: test_config.json (如果存在)")
        
        # 建议的环境变量设置
        print("\n建议的环境变量设置:")
        print("-" * 40)
        print("export TEST_SERVER_URL=https://your-server.com")
        print("export TEST_USERNAME=your_username")
        print("export TEST_PASSWORD=your_password")
        print("export TEST_MODE=functional")
        print("export TEST_ENVIRONMENT=test")
        print("export AGING_DURATION_HOURS=24")
        print("export AGING_CONCURRENT_THREADS=10")
        
        # 版本历史
        print("\n版本历史:")
        print("-" * 40)
        for version, description in version_info['version_history'].items():
            print(f"{version}: {description}")

if __name__ == "__main__":
    main()