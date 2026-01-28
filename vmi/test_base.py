"""
测试基类和工具函数

提供统一的测试基类，包含：
1. 配置管理
2. 会话管理
3. 数据清理
4. 性能监控
5. 工具函数
"""

import unittest
import logging
import time
import threading
import sys
import os
from typing import Dict, Any, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from test_config import get_config, TestMode

# 添加真实模块路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')

# 导入真实模块
import session
import cas.cas


class TestBase(unittest.TestCase):
    """测试基类
    
    所有测试类应该继承此类，以获取统一的配置和工具支持。
    """
    
    # 类级别配置
    _config = None
    _work_session = None
    _cas_session = None
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        # 获取配置
        cls._config = get_config()
        
        # 初始化会话
        server_config = cls._config.get_server_config()
        cls._work_session = session.MagicSession(
            server_config["server_url"],
            server_config["namespace"]
        )
        cls._cas_session = cas.Cas(cls._work_session)
        
        # 登录
        if not cls._cas_session.login(
            server_config["username"],
            server_config["password"]
        ):
            raise Exception("CAS登录失败")
        
        cls._work_session.bind_token(cls._cas_session.get_session_token())
        
        # 初始化日志
        cls._init_logging()
        
        logger = logging.getLogger(cls.__name__)
        logger.info(f"测试类初始化完成，模式: {cls._config['test_mode']}")
    
    @classmethod
    def _init_logging(cls):
        """初始化日志配置"""
        log_level = cls._config.get("monitoring", {}).get("log_level", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理"""
        if cls._work_session and cls._cas_session:
            # 可以在这里添加全局清理逻辑
            pass
    
    def setUp(self):
        """测试用例初始化"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.test_start_time = time.time()
        
        # 记录测试开始
        self.logger.info(f"开始测试: {self._testMethodName}")
    
    def tearDown(self):
        """测试用例清理"""
        test_duration = time.time() - self.test_start_time
        self.logger.info(f"测试完成: {self._testMethodName}, 耗时: {test_duration:.2f}秒")
    
    @property
    def config(self) -> Dict:
        """获取配置"""
        return self._config.config if self._config else {}
    
    @property
    def work_session(self):
        """获取工作会话"""
        return self._work_session
    
    @property
    def cas_session(self):
        """获取CAS会话"""
        return self._cas_session
    
    def refresh_session(self):
        """刷新会话token"""
        if self._cas_session and self._work_session:
            new_token = self._cas_session.refresh(self._cas_session.get_session_token())
            self._work_session.bind_token(new_token)
    
    def get_mode_param(self, key: str, default: Any = None) -> Any:
        """获取当前模式的参数
        
        Args:
            key: 参数键
            default: 默认值
            
        Returns:
            参数值
        """
        mode_params = self._config.get_mode_params() if self._config else {}
        return mode_params.get(key, default)
    
    def get_concurrent_param(self, key: str, default: Any = None) -> Any:
        """获取并发测试参数
        
        Args:
            key: 参数键
            default: 默认值
            
        Returns:
            参数值
        """
        concurrent_params = self._config.get_concurrent_params() if self._config else {}
        return concurrent_params.get(key, default)


class ConcurrentTestMixin:
    """并发测试混入类
    
    提供并发测试相关的工具方法。
    """
    
    def run_concurrent_tasks(self, tasks: List[Callable], max_workers: Optional[int] = None):
        """并发执行任务
        
        Args:
            tasks: 任务函数列表
            max_workers: 最大工作线程数
            
        Returns:
            任务结果列表
        """
        if max_workers is None:
            max_workers = self.get_concurrent_param("max_workers", 10)
        
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务
            future_to_task = {executor.submit(task): task for task in tasks}
            
            # 收集结果
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    result = future.result()
                    results.append((task, result, None))
                except Exception as e:
                    results.append((task, None, e))
        
        return results
    
    def create_concurrent_data_partition(self, total_count: int, thread_count: int) -> List[tuple]:
        """创建并发数据分区
        
        Args:
            total_count: 总数据量
            thread_count: 线程数
            
        Returns:
            每个线程的数据范围列表 [(start_idx, end_idx), ...]
        """
        partition_size = total_count // thread_count
        partitions = []
        
        for i in range(thread_count):
            start_idx = i * partition_size
            end_idx = start_idx + partition_size if i < thread_count - 1 else total_count
            partitions.append((start_idx, end_idx))
        
        return partitions
    
    def generate_unique_name(self, prefix: str, thread_id: int, item_id: int) -> str:
        """生成唯一名称
        
        Args:
            prefix: 名称前缀
            thread_id: 线程ID
            item_id: 项目ID
            
        Returns:
            唯一名称
        """
        return f"{prefix}_THREAD{thread_id}_ITEM{item_id}"
    
    def wait_for_condition(self, condition_func: Callable[[], bool], 
                          timeout: int = 30, interval: float = 0.5) -> bool:
        """等待条件满足
        
        Args:
            condition_func: 条件函数
            timeout: 超时时间（秒）
            interval: 检查间隔（秒）
            
        Returns:
            是否满足条件
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition_func():
                return True
            time.sleep(interval)
        return False


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, test_name: str):
        self.test_name = test_name
        self.metrics = {
            "start_time": time.time(),
            "operations": [],
            "errors": [],
            "threads": {}
        }
    
    def record_operation(self, operation_name: str, duration: float, 
                        success: bool = True, error: Optional[str] = None):
        """记录操作
        
        Args:
            operation_name: 操作名称
            duration: 耗时（秒）
            success: 是否成功
            error: 错误信息
        """
        operation = {
            "name": operation_name,
            "duration": duration,
            "success": success,
            "timestamp": time.time(),
            "error": error
        }
        self.metrics["operations"].append(operation)
        
        if not success and error:
            self.metrics["errors"].append({
                "operation": operation_name,
                "error": error,
                "timestamp": time.time()
            })
    
    def record_thread_metric(self, thread_id: int, metric_name: str, value: Any):
        """记录线程指标
        
        Args:
            thread_id: 线程ID
            metric_name: 指标名称
            value: 指标值
        """
        if thread_id not in self.metrics["threads"]:
            self.metrics["threads"][thread_id] = {}
        
        self.metrics["threads"][thread_id][metric_name] = value
    
    def get_summary(self) -> Dict:
        """获取性能摘要
        
        Returns:
            性能摘要字典
        """
        total_duration = time.time() - self.metrics["start_time"]
        operations = self.metrics["operations"]
        
        if not operations:
            return {
                "test_name": self.test_name,
                "total_duration": total_duration,
                "operation_count": 0,
                "success_rate": 0,
                "avg_duration": 0,
                "error_count": len(self.metrics["errors"])
            }
        
        success_count = sum(1 for op in operations if op["success"])
        total_duration_sum = sum(op["duration"] for op in operations)
        
        return {
            "test_name": self.test_name,
            "total_duration": total_duration,
            "operation_count": len(operations),
            "success_rate": success_count / len(operations) if operations else 0,
            "avg_duration": total_duration_sum / len(operations) if operations else 0,
            "min_duration": min(op["duration"] for op in operations) if operations else 0,
            "max_duration": max(op["duration"] for op in operations) if operations else 0,
            "error_count": len(self.metrics["errors"]),
            "thread_count": len(self.metrics["threads"])
        }
    
    def save_report(self, file_path: str):
        """保存报告到文件
        
        Args:
            file_path: 文件路径
        """
        import json
        report = {
            "summary": self.get_summary(),
            "metrics": self.metrics,
            "timestamp": time.time()
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)


# 工具函数
def create_test_data_batch(sdk, mock_func, count: int, batch_size: int = 50) -> List:
    """批量创建测试数据
    
    Args:
        sdk: SDK实例
        mock_func: mock数据生成函数
        count: 总数量
        batch_size: 批次大小
        
    Returns:
        创建的数据列表
    """
    data_list = []
    for i in range(0, count, batch_size):
        batch_count = min(batch_size, count - i)
        batch_data = []
        
        for j in range(batch_count):
            data = mock_func(i + j)
            batch_data.append(data)
        
        # 这里假设SDK支持批量创建
        # 如果不支持，需要逐个创建
        for data in batch_data:
            created = sdk.create(data)
            if created:
                data_list.append(created)
        
        # 短暂等待，避免请求过快
        time.sleep(0.1)
    
    return data_list


def cleanup_test_data(sdk, data_list: List, batch_size: int = 50):
    """清理测试数据
    
    Args:
        sdk: SDK实例
        data_list: 数据列表
        batch_size: 批次大小
    """
    logger = logging.getLogger(__name__)
    logger.info(f"开始清理 {len(data_list)} 个测试数据")
    
    for i in range(0, len(data_list), batch_size):
        batch = data_list[i:i + batch_size]
        
        for data in batch:
            try:
                if 'id' in data:
                    sdk.delete(data['id'])
            except Exception as e:
                logger.warning(f"清理数据失败: {e}")
        
        # 短暂等待
        time.sleep(0.05)
    
    logger.info("测试数据清理完成")


def validate_response_structure(response: Dict, required_fields: List[str]) -> bool:
    """验证响应结构
    
    Args:
        response: 响应数据
        required_fields: 必需字段列表
        
    Returns:
        是否验证通过
    """
    if not response:
        return False
    
    for field in required_fields:
        if field not in response:
            return False
    
    return True


def calculate_throughput(operation_count: int, total_duration: float) -> float:
    """计算吞吐量
    
    Args:
        operation_count: 操作数量
        total_duration: 总耗时（秒）
        
    Returns:
        吞吐量（操作/秒）
    """
    if total_duration <= 0:
        return 0
    return operation_count / total_duration


def calculate_error_rate(error_count: int, total_count: int) -> float:
    """计算错误率
    
    Args:
        error_count: 错误数量
        total_count: 总数量
        
    Returns:
        错误率
    """
    if total_count <= 0:
        return 0
    return error_count / total_count