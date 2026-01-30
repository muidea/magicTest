#!/usr/bin/env python3
"""
性能监控和报告工具
监控测试执行性能，生成详细报告
"""

import time
import psutil
import threading
import json
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import statistics

@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: str
    test_name: str
    duration: float  # 秒
    cpu_percent: float
    memory_mb: float
    api_calls: int = 0
    success_count: int = 0
    failure_count: int = 0
    error_messages: List[str] = None
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.metrics: List[PerformanceMetrics] = []
        self.current_test = None
        self.start_time = None
        self.api_call_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.error_messages = []
        self.monitoring_thread = None
        self.stop_monitoring = False
        
    def start_test(self, test_name: str):
        """开始测试监控"""
        self.current_test = test_name
        self.start_time = time.time()
        self.api_call_count = 0
        self.success_count = 0
        self.failure_count = 0
        self.error_messages = []
        
        # 启动后台监控线程
        self.stop_monitoring = False
        self.monitoring_thread = threading.Thread(target=self._monitor_resources)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        print(f"📊 开始监控测试: {test_name}")
    
    def end_test(self):
        """结束测试监控"""
        if not self.current_test or not self.start_time:
            return
        
        duration = time.time() - self.start_time
        
        # 停止监控线程
        self.stop_monitoring = True
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=1)
        
        # 获取最终资源使用情况
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.Process().memory_info()
        memory_mb = memory_info.rss / 1024 / 1024  # 转换为MB
        
        # 创建性能指标
        metrics = PerformanceMetrics(
            timestamp=datetime.now().isoformat(),
            test_name=self.current_test,
            duration=duration,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            api_calls=self.api_call_count,
            success_count=self.success_count,
            failure_count=self.failure_count,
            error_messages=self.error_messages.copy()
        )
        
        self.metrics.append(metrics)
        
        # 打印测试摘要
        self._print_test_summary(metrics)
        
        # 重置状态
        self.current_test = None
        self.start_time = None
    
    def record_api_call(self, success: bool = True):
        """记录API调用"""
        self.api_call_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
    
    def record_error(self, error_message: str):
        """记录错误信息"""
        self.error_messages.append(error_message)
    
    def _monitor_resources(self):
        """后台资源监控线程"""
        while not self.stop_monitoring:
            # 这里可以记录更详细的资源使用历史
            time.sleep(5)  # 每5秒检查一次
    
    def _print_test_summary(self, metrics: PerformanceMetrics):
        """打印测试摘要"""
        print(f"\n{'='*60}")
        print(f"📋 测试摘要: {metrics.test_name}")
        print(f"{'='*60}")
        print(f"执行时间: {metrics.duration:.2f}秒")
        print(f"CPU使用率: {metrics.cpu_percent:.1f}%")
        print(f"内存使用: {metrics.memory_mb:.1f}MB")
        print(f"API调用次数: {metrics.api_calls}")
        print(f"成功: {metrics.success_count} | 失败: {metrics.failure_count}")
        
        if metrics.failure_count > 0:
            success_rate = metrics.success_count / metrics.api_calls * 100 if metrics.api_calls > 0 else 0
            print(f"成功率: {success_rate:.1f}%")
        
        if metrics.error_messages:
            print(f"\n错误信息 ({len(metrics.error_messages)}个):")
            for i, error in enumerate(metrics.error_messages[:5], 1):  # 只显示前5个错误
                print(f"  {i}. {error}")
            if len(metrics.error_messages) > 5:
                print(f"  ... 还有 {len(metrics.error_messages) - 5} 个错误")
    
    def generate_report(self, output_file: str = None):
        """生成性能报告"""
        if not self.metrics:
            print("⚠️  没有性能数据可报告")
            return
        
        print(f"\n{'='*60}")
        print("📊 性能分析报告")
        print(f"{'='*60}")
        
        # 总体统计
        total_duration = sum(m.duration for m in self.metrics)
        avg_duration = statistics.mean([m.duration for m in self.metrics])
        total_api_calls = sum(m.api_calls for m in self.metrics)
        total_success = sum(m.success_count for m in self.metrics)
        total_failure = sum(m.failure_count for m in self.metrics)
        
        print(f"总测试数: {len(self.metrics)}")
        print(f"总执行时间: {total_duration:.2f}秒")
        print(f"平均测试时间: {avg_duration:.2f}秒")
        print(f"总API调用: {total_api_calls}")
        print(f"总成功: {total_success} | 总失败: {total_failure}")
        
        if total_api_calls > 0:
            overall_success_rate = total_success / total_api_calls * 100
            print(f"总体成功率: {overall_success_rate:.1f}%")
        
        # 按测试详细统计
        print(f"\n{'='*60}")
        print("📈 详细测试性能")
        print(f"{'='*60}")
        
        for metrics in self.metrics:
            print(f"\n测试: {metrics.test_name}")
            print(f"  时间: {metrics.duration:.2f}秒")
            print(f"  CPU: {metrics.cpu_percent:.1f}%")
            print(f"  内存: {metrics.memory_mb:.1f}MB")
            print(f"  API调用: {metrics.api_calls}")
            
            if metrics.api_calls > 0:
                test_success_rate = metrics.success_count / metrics.api_calls * 100
                print(f"  成功率: {test_success_rate:.1f}%")
        
        # 性能建议
        print(f"\n{'='*60}")
        print("💡 性能建议")
        print(f"{'='*60}")
        
        # 找出最慢的测试
        slowest_test = max(self.metrics, key=lambda m: m.duration)
        fastest_test = min(self.metrics, key=lambda m: m.duration)
        
        if slowest_test.duration > 30:  # 超过30秒的测试
            print(f"⚠️  '{slowest_test.test_name}' 测试较慢 ({slowest_test.duration:.2f}秒)")
            print("   建议: 检查是否有不必要的等待或优化API调用")
        
        # 检查高内存使用
        high_memory_tests = [m for m in self.metrics if m.memory_mb > 100]  # 超过100MB
        if high_memory_tests:
            print(f"⚠️  以下测试内存使用较高:")
            for test in high_memory_tests:
                print(f"    - {test.test_name}: {test.memory_mb:.1f}MB")
            print("   建议: 检查内存泄漏或优化数据加载")
        
        # 检查低成功率
        low_success_tests = []
        for m in self.metrics:
            if m.api_calls > 0:
                success_rate = m.success_count / m.api_calls * 100
                if success_rate < 90:  # 成功率低于90%
                    low_success_tests.append((m.test_name, success_rate))
        
        if low_success_tests:
            print(f"⚠️  以下测试成功率较低:")
            for test_name, rate in low_success_tests:
                print(f"    - {test_name}: {rate:.1f}%")
            print("   建议: 检查API稳定性或网络连接")
        
        # 保存报告到文件
        if output_file:
            report_data = {
                "generated_at": datetime.now().isoformat(),
                "summary": {
                    "total_tests": len(self.metrics),
                    "total_duration": total_duration,
                    "average_duration": avg_duration,
                    "total_api_calls": total_api_calls,
                    "total_success": total_success,
                    "total_failure": total_failure,
                    "overall_success_rate": overall_success_rate if total_api_calls > 0 else 0
                },
                "tests": [asdict(m) for m in self.metrics],
                "recommendations": {
                    "slow_tests": [slowest_test.test_name] if slowest_test.duration > 30 else [],
                    "high_memory_tests": [m.test_name for m in high_memory_tests],
                    "low_success_tests": [name for name, _ in low_success_tests]
                }
            }
            
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n📄 报告已保存到: {output_file}")
    
    def clear(self):
        """清除所有监控数据"""
        self.metrics.clear()
        self.current_test = None
        self.start_time = None

# 全局监控器实例
global_monitor = PerformanceMonitor()

def monitor_test(test_name):
    """装饰器：监控测试函数性能"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            global_monitor.start_test(test_name)
            try:
                result = func(*args, **kwargs)
                global_monitor.record_api_call(success=True)
                return result
            except Exception as e:
                global_monitor.record_api_call(success=False)
                global_monitor.record_error(str(e))
                raise
            finally:
                global_monitor.end_test()
        return wrapper
    return decorator

def record_api_call(success=True):
    """记录API调用"""
    global_monitor.record_api_call(success)

def record_error(error_message):
    """记录错误"""
    global_monitor.record_error(error_message)

if __name__ == "__main__":
    # 示例用法
    monitor = PerformanceMonitor()
    
    # 模拟测试1
    monitor.start_test("基础功能测试")
    time.sleep(1)
    monitor.record_api_call(success=True)
    monitor.record_api_call(success=True)
    monitor.record_api_call(success=False)
    monitor.record_error("API调用超时")
    monitor.end_test()
    
    # 模拟测试2
    monitor.start_test("并发测试")
    time.sleep(2)
    for i in range(5):
        monitor.record_api_call(success=True)
    monitor.end_test()
    
    # 生成报告
    monitor.generate_report("performance_report.json")