#!/usr/bin/env python3
"""
测试基类
提供通用的测试功能，包括并发测试支持
"""

import unittest
import time
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class TestResult:
    """测试结果数据类"""
    test_name: str
    passed: bool
    duration: float
    error_message: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class ConcurrentTestMixin:
    """并发测试混入类"""
    
    def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建实体（需要在子类中实现）"""
        raise NotImplementedError("子类必须实现 create_entity 方法")
    
    def read_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """读取实体（需要在子类中实现）"""
        raise NotImplementedError("子类必须实现 read_entity 方法")
    
    def update_entity(self, entity_type: str, entity_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新实体（需要在子类中实现）"""
        raise NotImplementedError("子类必须实现 update_entity 方法")
    
    def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        """删除实体（需要在子类中实现）"""
        raise NotImplementedError("子类必须实现 delete_entity 方法")
    
    def list_entities(self, entity_type: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出实体（需要在子类中实现）"""
        raise NotImplementedError("子类必须实现 list_entities 方法")
    
    def setUp(self):
        """测试用例初始化"""
        pass
    
    def tearDown(self):
        """测试用例清理"""
        pass


class TestBase(unittest.TestCase, ConcurrentTestMixin):
    """测试基类"""
    
    def create_entity(self, entity_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建实体 - 基础实现"""
        # 这是一个基础实现，子类应该重写这个方法
        entity_id = f"{entity_type}_{int(time.time() * 1000)}"
        return {"id": entity_id, **data}
    
    def read_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """读取实体 - 基础实现"""
        # 这是一个基础实现，子类应该重写这个方法
        return {"id": entity_id, "type": entity_type, "status": "active"}
    
    def update_entity(self, entity_type: str, entity_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新实体 - 基础实现"""
        # 这是一个基础实现，子类应该重写这个方法
        entity = self.read_entity(entity_type, entity_id)
        entity.update(update_data)
        return entity
    
    def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        """删除实体 - 基础实现"""
        # 这是一个基础实现，子类应该重写这个方法
        return True
    
    def list_entities(self, entity_type: str, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """列出实体 - 基础实现"""
        # 这是一个基础实现，子类应该重写这个方法
        return []


class PerformanceMonitor:
    """性能监控器 - 简化版本"""
    
    def __init__(self, name: str = "default"):
        self.name = name
        self.metrics = []
        self.start_time = None
        self.end_time = None
    
    def start(self):
        """开始监控"""
        self.start_time = time.time()
    
    def stop(self):
        """停止监控"""
        self.end_time = time.time()
    
    def record_metric(self, metric_name: str, value: float):
        """记录指标"""
        self.metrics.append({
            "name": metric_name,
            "value": value,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取所有指标"""
        duration = self.end_time - self.start_time if self.start_time and self.end_time else 0
        
        return {
            "monitor_name": self.name,
            "duration": duration,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "metrics": self.metrics
        }


if __name__ == "__main__":
    # 测试基类功能
    class TestExample(TestBase):
        def test_example(self):
            entity = self.create_entity("test", {"name": "example"})
            self.assertIn("id", entity)
            self.assertEqual(entity["name"], "example")
    
    suite = unittest.TestLoader().loadTestsFromTestCase(TestExample)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print(f"\n测试结果: {result.testsRun} 个测试运行")
    print(f"失败: {len(result.failures)}, 错误: {len(result.errors)}")