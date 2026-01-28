import json
import time
from datetime import datetime
from typing import Dict, List, Any
import statistics


class PerformanceReport:
    def __init__(self):
        self.start_time = time.time()
        self.test_results = []
        self.metrics = {}
        
    def record_test(self, test_name: str, test_type: str, duration: float, 
                   success: bool, details: Dict[str, Any] = None):
        result = {
            'test_name': test_name,
            'test_type': test_type,
            'duration': duration,
            'success': success,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        self.test_results.append(result)
        
    def record_metric(self, name: str, value: float, unit: str = "seconds"):
        if name not in self.metrics:
            self.metrics[name] = []
        self.metrics[name].append({
            'value': value,
            'unit': unit,
            'timestamp': datetime.now().isoformat()
        })
        
    def generate_summary(self) -> Dict[str, Any]:
        total_tests = len(self.test_results)
        successful_tests = sum(1 for r in self.test_results if r['success'])
        failed_tests = total_tests - successful_tests
        
        durations = [r['duration'] for r in self.test_results]
        
        summary = {
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'failed_tests': failed_tests,
            'success_rate': (successful_tests / total_tests * 100) if total_tests > 0 else 0,
            'total_duration': sum(durations),
            'avg_duration': statistics.mean(durations) if durations else 0,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0,
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'end_time': datetime.now().isoformat()
        }
        
        test_types = {}
        for result in self.test_results:
            test_type = result['test_type']
            if test_type not in test_types:
                test_types[test_type] = {
                    'count': 0,
                    'successful': 0,
                    'durations': []
                }
            test_types[test_type]['count'] += 1
            if result['success']:
                test_types[test_type]['successful'] += 1
            test_types[test_type]['durations'].append(result['duration'])
        
        for test_type, stats in test_types.items():
            stats['success_rate'] = (stats['successful'] / stats['count'] * 100) if stats['count'] > 0 else 0
            stats['avg_duration'] = statistics.mean(stats['durations']) if stats['durations'] else 0
            del stats['durations']
            
        summary['test_types'] = test_types
        
        metrics_summary = {}
        for metric_name, metric_list in self.metrics.items():
            values = [m['value'] for m in metric_list]
            metrics_summary[metric_name] = {
                'count': len(values),
                'total': sum(values),
                'average': statistics.mean(values) if values else 0,
                'min': min(values) if values else 0,
                'max': max(values) if values else 0,
                'unit': metric_list[0]['unit'] if metric_list else 'unknown'
            }
            
        summary['metrics'] = metrics_summary
        
        return summary
        
    def save_report(self, filename: str = "performance_report.json"):
        report = {
            'summary': self.generate_summary(),
            'test_results': self.test_results,
            'metrics': self.metrics,
            'generated_at': datetime.now().isoformat()
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            
        return report
        
    def print_summary(self):
        summary = self.generate_summary()
        
        print("\n" + "="*60)
        print("性能测试报告摘要")
        print("="*60)
        
        print(f"执行时间: {summary['start_time']} - {summary['end_time']}")
        print(f"总耗时: {summary['total_duration']:.2f}秒")
        print(f"总测试数: {summary['total_tests']}")
        print(f"成功: {summary['successful_tests']}")
        print(f"失败: {summary['failed_tests']}")
        print(f"成功率: {summary['success_rate']:.1f}%")
        
        print(f"\n平均测试时间: {summary['avg_duration']:.2f}秒")
        print(f"最短测试时间: {summary['min_duration']:.2f}秒")
        print(f"最长测试时间: {summary['max_duration']:.2f}秒")
        
        print("\n测试类型统计:")
        for test_type, stats in summary['test_types'].items():
            print(f"  {test_type}: {stats['count']}个测试, {stats['success_rate']:.1f}%成功率, "
                  f"平均{stats['avg_duration']:.2f}秒")
                  
        if summary['metrics']:
            print("\n性能指标:")
            for metric_name, stats in summary['metrics'].items():
                print(f"  {metric_name}: {stats['average']:.2f}{stats['unit']} "
                      f"(范围: {stats['min']:.2f}-{stats['max']:.2f}, "
                      f"样本: {stats['count']})")
                      
        print("="*60)


class TestMonitor:
    def __init__(self, report: PerformanceReport):
        self.report = report
        self.test_start_times = {}
        
    def start_test(self, test_name: str, test_type: str = "functional"):
        self.test_start_times[test_name] = time.time()
        return test_name
        
    def end_test(self, test_name: str, success: bool = True, details: Dict[str, Any] = None):
        if test_name in self.test_start_times:
            duration = time.time() - self.test_start_times[test_name]
            test_type = "functional"  # 默认类型，可以根据需要扩展
            
            self.report.record_test(test_name, test_type, duration, success, details)
            del self.test_start_times[test_name]
            
            return duration
        return 0


def create_test_report():
    report = PerformanceReport()
    
    monitor = TestMonitor(report)
    
    test1 = monitor.start_test("test_store_creation", "store")
    time.sleep(0.1)
    monitor.end_test(test1, True, {"stores_created": 5})
    
    test2 = monitor.start_test("test_goods_operations", "goods")
    time.sleep(0.2)
    monitor.end_test(test2, True, {"goods_processed": 10})
    
    test3 = monitor.start_test("test_concurrent_operations", "concurrent")
    time.sleep(0.3)
    monitor.end_test(test3, False, {"error": "timeout"})
    
    report.record_metric("response_time", 0.15, "seconds")
    report.record_metric("throughput", 100, "requests/second")
    report.record_metric("memory_usage", 256, "MB")
    
    report.print_summary()
    report.save_report()
    
    return report


if __name__ == "__main__":
    create_test_report()