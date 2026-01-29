#!/usr/bin/env python3
"""
配置变更查看工具
用于查看配置变更历史
"""

import sys
import os
import time
import argparse
from datetime import datetime

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from test_config import config

def format_timestamp(timestamp):
    """格式化时间戳"""
    if timestamp:
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    return 'N/A'

def show_recent_changes(hours=24):
    """显示最近变更"""
    print("=" * 80)
    print(f"最近 {hours} 小时内的配置变更")
    print("=" * 80)
    
    changes = config.get_recent_changes(hours)
    if not changes:
        print("没有找到最近的配置变更")
        return True
    
    print(f"变更数量: {len(changes)}")
    print("-" * 80)
    
    for i, change in enumerate(changes, 1):
        print(f"{i}. {change['key']}")
        print(f"   时间: {format_timestamp(change['timestamp'])}")
        print(f"   来源: {change.get('source', 'unknown')}")
        print(f"   旧值: {change['old_value']}")
        print(f"   新值: {change['new_value']}")
        print()
    
    return True

def show_all_changes(limit=50):
    """显示所有变更"""
    print("=" * 80)
    print("所有配置变更历史")
    print("=" * 80)
    
    changes = config.get_change_log(limit)
    if not changes:
        print("没有找到配置变更记录")
        return True
    
    print(f"变更数量: {len(changes)} (显示最近 {limit} 条)")
    print("-" * 80)
    
    for i, change in enumerate(changes, 1):
        print(f"{i}. {change['key']}")
        print(f"   时间: {format_timestamp(change['timestamp'])}")
        print(f"   来源: {change.get('source', 'unknown')}")
        print(f"   旧值: {change['old_value']}")
        print(f"   新值: {change['new_value']}")
        print()
    
    return True

def save_changes_to_file():
    """保存变更到文件"""
    print("=" * 80)
    print("保存配置变更记录")
    print("=" * 80)
    
    log_file = config.save_change_log()
    if log_file:
        print(f"✅ 变更记录已保存到: {log_file}")
        
        # 显示保存的变更数量
        changes = config.get_change_log()
        print(f"保存的变更数量: {len(changes)}")
        
        return True
    else:
        print("❌ 保存变更记录失败")
        return False

def show_change_summary():
    """显示变更摘要"""
    print("=" * 80)
    print("配置变更摘要")
    print("=" * 80)
    
    changes = config.get_change_log()
    if not changes:
        print("没有找到配置变更记录")
        return True
    
    # 按来源统计
    source_stats = {}
    key_stats = {}
    
    for change in changes:
        source = change.get('source', 'unknown')
        key = change['key']
        
        source_stats[source] = source_stats.get(source, 0) + 1
        key_stats[key] = key_stats.get(key, 0) + 1
    
    print(f"总变更次数: {len(changes)}")
    print(f"记录时间范围: {format_timestamp(changes[0]['timestamp'])} 到 {format_timestamp(changes[-1]['timestamp'])}")
    
    print("\n按来源统计:")
    print("-" * 40)
    for source, count in sorted(source_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {source}: {count} 次")
    
    print("\n按配置项统计:")
    print("-" * 40)
    for key, count in sorted(key_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {key}: {count} 次")
    
    # 显示最近的重要变更
    print("\n最近的重要变更:")
    print("-" * 40)
    important_keys = ['server_url', 'username', 'test_mode', 'environment']
    recent_changes = config.get_recent_changes(24)
    
    for change in recent_changes:
        if change['key'] in important_keys:
            print(f"  {change['key']}: {change['old_value']} → {change['new_value']}")
            print(f"    时间: {format_timestamp(change['timestamp'])}")
            print(f"    来源: {change.get('source', 'unknown')}")
    
    return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='配置变更查看工具')
    parser.add_argument('--recent', type=int, default=24, help='显示最近N小时内的变更（默认: 24）')
    parser.add_argument('--all', '-a', action='store_true', help='显示所有变更历史')
    parser.add_argument('--save', '-s', action='store_true', help='保存变更记录到文件')
    parser.add_argument('--summary', action='store_true', help='显示变更摘要')
    parser.add_argument('--limit', type=int, default=50, help='显示变更数量限制（默认: 50）')
    
    args = parser.parse_args()
    
    if args.all:
        show_all_changes(args.limit)
    elif args.save:
        save_changes_to_file()
    elif args.summary:
        show_change_summary()
    else:
        show_recent_changes(args.recent)

if __name__ == "__main__":
    main()