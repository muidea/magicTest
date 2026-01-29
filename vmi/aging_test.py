#!/usr/bin/env python3
"""
长期老化测试模块

用于持续处理partner, product, stockin, stockout, goods CRUD业务，
检验服务器运行稳定性，具备并发性和持续性。

主要功能：
1. 并发测试：多线程同时执行不同业务操作
2. 持续测试：长时间运行，模拟真实业务场景
3. 基础数据：在已有数据基础上进行测试
4. 监控报告：实时监控系统状态，生成测试报告
"""

import concurrent.futures
import threading
import time
import random
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum
import statistics

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestPhase(Enum):
    """测试阶段"""
    WARMUP = "warmup"  # 预热阶段
    STEADY = "steady"  # 稳定运行阶段
    PEAK = "peak"      # 峰值压力阶段
    COOLDOWN = "cooldown"  # 冷却阶段


class OperationType(Enum):
    """操作类型"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"


@dataclass
class OperationResult:
    """操作结果"""
    operation_type: OperationType
    entity_type: str
    success: bool
    duration: float
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgingTestConfig:
    """老化测试配置"""
    # 测试持续时间（小时）
    duration_hours: int = 24
    # 并发线程数
    concurrent_threads: int = 10
    # 操作间隔（秒）
    operation_interval: float = 1.0
    # 预热时间（分钟）
    warmup_minutes: int = 5
    # 峰值压力倍数
    peak_multiplier: float = 2.0
    # 基础数据量
    base_data_count: int = 100
    # 最大数据量（万条）
    max_data_count: int = 1000  # 1000万条 = 10,000,000条
    # 是否启用数据验证
    enable_validation: bool = True
    # 报告生成间隔（分钟）
    report_interval_minutes: int = 30
    # 性能劣化阈值（百分比）
    performance_degradation_threshold: float = 20.0  # 20%性能下降
    # 性能监控窗口大小（操作数）
    performance_window_size: int = 100


@dataclass
class EntityDataGenerator:
    """实体数据生成器"""
    
    @staticmethod
    def generate_partner_data(worker_id: int = 0) -> Dict[str, Any]:
        """生成合作伙伴数据"""
        return {
            'name': f'老化测试合作伙伴_{worker_id}_{int(time.time())}',
            'telephone': f'138{random.randint(10000000, 99999999)}',
            'wechat': f'wechat_{worker_id}',
            'description': f'老化测试合作伙伴描述_{worker_id}',
            'status': {'id': 3}
        }
    
    @staticmethod
    def generate_product_data(worker_id: int = 0) -> Dict[str, Any]:
        """生成产品数据"""
        return {
            'name': f'老化测试产品_{worker_id}_{int(time.time())}',
            'code': f'PROD_{worker_id:04d}',
            'price': round(random.uniform(10.0, 1000.0), 2),
            'description': f'老化测试产品描述_{worker_id}',
            'status': {'id': 1}
        }
    
    @staticmethod
    def generate_goods_data(worker_id: int = 0) -> Dict[str, Any]:
        """生成商品数据"""
        return {
            'name': f'老化测试商品_{worker_id}_{int(time.time())}',
            'code': f'GOODS_{worker_id:04d}',
            'price': round(random.uniform(5.0, 500.0), 2),
            'quantity': random.randint(1, 1000),
            'description': f'老化测试商品描述_{worker_id}'
        }
    
    @staticmethod
    def generate_stockin_data(worker_id: int = 0, goods_id: Optional[str] = None) -> Dict[str, Any]:
        """生成入库数据"""
        return {
            'warehouse_id': f'warehouse_{worker_id % 5}',
            'goods_id': goods_id or f'goods_{worker_id}',
            'quantity': random.randint(1, 100),
            'type': 'in',
            'remark': f'老化测试入库_{worker_id}',
            'operator': f'operator_{worker_id}'
        }
    
    @staticmethod
    def generate_stockout_data(worker_id: int = 0, goods_id: Optional[str] = None) -> Dict[str, Any]:
        """生成出库数据"""
        return {
            'warehouse_id': f'warehouse_{worker_id % 5}',
            'goods_id': goods_id or f'goods_{worker_id}',
            'quantity': random.randint(1, 50),
            'type': 'out',
            'remark': f'老化测试出库_{worker_id}',
            'operator': f'operator_{worker_id}'
        }


class AgingTestWorker:
    """老化测试工作线程"""
    
    def __init__(self, worker_id: int, config: AgingTestConfig):
        self.worker_id = worker_id
        self.config = config
        self.results: List[OperationResult] = []
        self.running = False
        self.entity_cache: Dict[str, List[str]] = {
            'partner': [],
            'product': [],
            'goods': [],
            'stockin': [],
            'stockout': []
        }
        # 性能监控窗口
        self.performance_window: List[float] = []
        self.baseline_performance: Optional[float] = None
        
    def run(self, stop_event: threading.Event):
        """运行测试工作线程"""
        self.running = True
        logger.info(f"工作线程 {self.worker_id} 启动")
        
        try:
            # 导入SDK
            from session_mock import MagicSession
            from cas_mock.cas import Cas
            from sdk import PartnerSDK, ProductSDK, GoodsSDK, StockinSDK, StockoutSDK
            
            # 导入配置助手
            from config_helper import get_server_url, get_credentials
            
            # 初始化会话
            server_url = get_server_url()
            credentials = get_credentials()
            
            work_session = session.MagicSession(server_url, '')
            cas_session = Cas(work_session)
            if not cas_session.login(credentials['username'], credentials['password']):
                logger.error(f"工作线程 {self.worker_id}: CAS登录失败")
                return
            
            work_session.bind_token(cas_session.get_session_token())
            
            # 初始化SDK
            self.partner_sdk = PartnerSDK(work_session)
            self.product_sdk = ProductSDK(work_session)
            self.goods_sdk = GoodsSDK(work_session)
            self.stockin_sdk = StockinSDK(work_session)
            self.stockout_sdk = StockoutSDK(work_session)
            
            # 运行测试循环
            while self.running and not stop_event.is_set():
                try:
                    # 随机选择操作类型
                    operation_type = random.choice(list(OperationType))
                    
                    # 随机选择实体类型
                    entity_type = random.choice(['partner', 'product', 'goods', 'stockin', 'stockout'])
                    
                    # 执行操作
                    result = self._execute_operation(operation_type, entity_type)
                    self.results.append(result)
                    
                    # 记录结果
                    if result.success:
                        logger.debug(f"工作线程 {self.worker_id}: {entity_type}.{operation_type.value} 成功")
                    else:
                        logger.warning(f"工作线程 {self.worker_id}: {entity_type}.{operation_type.value} 失败: {result.error}")
                    
                    # 操作间隔
                    time.sleep(self.config.operation_interval)
                    
                except Exception as e:
                    logger.error(f"工作线程 {self.worker_id} 执行操作异常: {e}")
                    time.sleep(1.0)
                    
        except Exception as e:
            logger.error(f"工作线程 {self.worker_id} 初始化失败: {e}")
        finally:
            self.running = False
            logger.info(f"工作线程 {self.worker_id} 停止")
    
    def _execute_operation(self, operation_type: OperationType, entity_type: str) -> OperationResult:
        """执行具体操作"""
        start_time = time.time()
        
        try:
            if operation_type == OperationType.CREATE:
                result = self._create_entity(entity_type)
            elif operation_type == OperationType.READ:
                result = self._read_entity(entity_type)
            elif operation_type == OperationType.UPDATE:
                result = self._update_entity(entity_type)
            elif operation_type == OperationType.DELETE:
                result = self._delete_entity(entity_type)
            elif operation_type == OperationType.LIST:
                result = self._list_entities(entity_type)
            else:
                raise ValueError(f"未知操作类型: {operation_type}")
            
            duration = time.time() - start_time
            
            # 更新性能监控窗口
            self._update_performance_window(duration)
            
            return OperationResult(
                operation_type=operation_type,
                entity_type=entity_type,
                success=True,
                duration=duration
            )
            
        except Exception as e:
            duration = time.time() - start_time
            return OperationResult(
                operation_type=operation_type,
                entity_type=entity_type,
                success=False,
                duration=duration,
                error=str(e)
            )
    
    def _update_performance_window(self, duration: float):
        """更新性能监控窗口"""
        self.performance_window.append(duration)
        
        # 保持窗口大小
        if len(self.performance_window) > self.config.performance_window_size:
            self.performance_window.pop(0)
        
        # 设置基线性能（前100个操作的平均值）
        if self.baseline_performance is None and len(self.performance_window) >= 100:
            self.baseline_performance = statistics.mean(self.performance_window)
            logger.info(f"工作线程 {self.worker_id} 基线性能: {self.baseline_performance:.3f}s")
    
    def check_performance_degradation(self) -> Optional[float]:
        """检查性能劣化
        
        Returns:
            性能劣化百分比，如果未劣化则返回None
        """
        if self.baseline_performance is None or len(self.performance_window) < 10:
            return None
        
        current_performance = statistics.mean(self.performance_window)
        
        # 计算性能变化百分比
        if self.baseline_performance > 0:
            degradation_percent = ((current_performance - self.baseline_performance) / 
                                  self.baseline_performance * 100)
            
            if degradation_percent > self.config.performance_degradation_threshold:
                return degradation_percent
        
        return None
    
    def _create_entity(self, entity_type: str) -> Any:
        """创建实体"""
        if entity_type == 'partner':
            data = EntityDataGenerator.generate_partner_data(self.worker_id)
            result = self.partner_sdk.create_partner(data)
        elif entity_type == 'product':
            data = EntityDataGenerator.generate_product_data(self.worker_id)
            result = self.product_sdk.create_product(data)
        elif entity_type == 'goods':
            data = EntityDataGenerator.generate_goods_data(self.worker_id)
            result = self.goods_sdk.create_goods(data)
        elif entity_type == 'stockin':
            # 需要先有商品
            goods_id = self._get_or_create_goods()
            data = EntityDataGenerator.generate_stockin_data(self.worker_id, goods_id)
            result = self.stockin_sdk.create_stockin(data)
        elif entity_type == 'stockout':
            # 需要先有商品
            goods_id = self._get_or_create_goods()
            data = EntityDataGenerator.generate_stockout_data(self.worker_id, goods_id)
            result = self.stockout_sdk.create_stockout(data)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")
        
        if result and 'id' in result:
            self.entity_cache[entity_type].append(result['id'])
        
        return result
    
    def _read_entity(self, entity_type: str) -> Any:
        """读取实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            # 如果没有缓存，先创建一个
            return self._create_entity(entity_type)
        
        entity_id = random.choice(entity_ids)
        
        if entity_type == 'partner':
            return self.partner_sdk.query_partner(entity_id)
        elif entity_type == 'product':
            return self.product_sdk.query_product(entity_id)
        elif entity_type == 'goods':
            return self.goods_sdk.query_goods(entity_id)
        elif entity_type == 'stockin':
            return self.stockin_sdk.query_stockin(entity_id)
        elif entity_type == 'stockout':
            return self.stockout_sdk.query_stockout(entity_id)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")
    
    def _update_entity(self, entity_type: str) -> Any:
        """更新实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            # 如果没有缓存，先创建一个
            entity = self._create_entity(entity_type)
            if not entity or 'id' not in entity:
                return None
            entity_id = entity['id']
        else:
            entity_id = random.choice(entity_ids)
        
        # 获取当前实体
        current_entity = self._read_entity(entity_type)
        if not current_entity:
            return None
        
        # 更新描述字段
        current_entity['description'] = f'老化测试更新_{self.worker_id}_{int(time.time())}'
        
        if entity_type == 'partner':
            return self.partner_sdk.update_partner(entity_id, current_entity)
        elif entity_type == 'product':
            return self.product_sdk.update_product(entity_id, current_entity)
        elif entity_type == 'goods':
            return self.goods_sdk.update_goods(entity_id, current_entity)
        elif entity_type == 'stockin':
            return self.stockin_sdk.update_stockin(entity_id, current_entity)
        elif entity_type == 'stockout':
            return self.stockout_sdk.update_stockout(entity_id, current_entity)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")
    
    def _delete_entity(self, entity_type: str) -> Any:
        """删除实体"""
        entity_ids = self.entity_cache[entity_type]
        if not entity_ids:
            return None
        
        entity_id = random.choice(entity_ids)
        
        if entity_type == 'partner':
            result = self.partner_sdk.delete_partner(entity_id)
        elif entity_type == 'product':
            result = self.product_sdk.delete_product(entity_id)
        elif entity_type == 'goods':
            result = self.goods_sdk.delete_goods(entity_id)
        elif entity_type == 'stockin':
            result = self.stockin_sdk.delete_stockin(entity_id)
        elif entity_type == 'stockout':
            result = self.stockout_sdk.delete_stockout(entity_id)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")
        
        if result:
            self.entity_cache[entity_type].remove(entity_id)
        
        return result
    
    def _list_entities(self, entity_type: str) -> Any:
        """列出实体"""
        filters = {'page': 1, 'size': 10}
        
        if entity_type == 'partner':
            return self.partner_sdk.filter_partner(filters)
        elif entity_type == 'product':
            return self.product_sdk.filter_product(filters)
        elif entity_type == 'goods':
            return self.goods_sdk.filter_goods(filters)
        elif entity_type == 'stockin':
            return self.stockin_sdk.filter_stockin(filters)
        elif entity_type == 'stockout':
            return self.stockout_sdk.filter_stockout(filters)
        else:
            raise ValueError(f"未知实体类型: {entity_type}")
    
    def _get_or_create_goods(self) -> str:
        """获取或创建商品ID"""
        goods_ids = self.entity_cache['goods']
        if goods_ids:
            return random.choice(goods_ids)
        
        # 创建新商品
        goods_data = EntityDataGenerator.generate_goods_data(self.worker_id)
        goods = self.goods_sdk.create_goods(goods_data)
        if goods and 'id' in goods:
            self.entity_cache['goods'].append(goods['id'])
            return goods['id']
        
        # 如果创建失败，返回一个默认ID
        return f'goods_{self.worker_id}'
    
    def get_results(self) -> List[OperationResult]:
        """获取测试结果"""
        return self.results
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        if not self.results:
            return {}
        
        successful_results = [r for r in self.results if r.success]
        failed_results = [r for r in self.results if not r.success]
        
        durations = [r.duration for r in self.results if r.duration > 0]
        
        # 计算性能劣化
        degradation_percent = self.check_performance_degradation()
        
        # 计算总数据量（缓存中的实体数）
        total_entities = sum(len(ids) for ids in self.entity_cache.values())
        
        return {
            'total_operations': len(self.results),
            'successful_operations': len(successful_results),
            'failed_operations': len(failed_results),
            'success_rate': len(successful_results) / len(self.results) * 100 if self.results else 0,
            'avg_duration': statistics.mean(durations) if durations else 0,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0,
            'entity_counts': {entity_type: len(ids) for entity_type, ids in self.entity_cache.items()},
            'total_entities': total_entities,
            'performance_degradation_percent': degradation_percent,
            'baseline_performance': self.baseline_performance,
            'current_performance': statistics.mean(self.performance_window) if self.performance_window else 0
        }


class AgingTestMonitor:
    """老化测试监控器"""
    
    def __init__(self, config: AgingTestConfig):
        self.config = config
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.phase_history: List[Dict[str, Any]] = []
        self.current_phase = TestPhase.WARMUP
        self.metrics_history: List[Dict[str, Any]] = []
        self.data_limit_exceeded = False
        self.performance_degradation_detected = False
        self.stop_reason: Optional[str] = None
        
    def start(self):
        """开始监控"""
        self.start_time = datetime.now()
        logger.info(f"老化测试监控开始: {self.start_time}")
        
    def update_phase(self, phase: TestPhase):
        """更新测试阶段"""
        self.current_phase = phase
        phase_info = {
            'phase': phase.value,
            'timestamp': datetime.now().isoformat(),
            'elapsed_minutes': self.get_elapsed_minutes()
        }
        self.phase_history.append(phase_info)
        logger.info(f"测试阶段更新: {phase.value}")
        
    def record_metrics(self, workers: List[AgingTestWorker]):
        """记录指标"""
        total_stats = {
            'total_operations': 0,
            'successful_operations': 0,
            'failed_operations': 0,
            'avg_duration': 0,
            'total_entities': 0,
            'worker_count': len(workers),
            'performance_degradation_detected': False,
            'data_limit_exceeded': False
        }
        
        worker_durations = []
        performance_degradations = []
        
        for worker in workers:
            stats = worker.get_statistics()
            if stats:
                total_stats['total_operations'] += stats['total_operations']
                total_stats['successful_operations'] += stats['successful_operations']
                total_stats['failed_operations'] += stats['failed_operations']
                total_stats['total_entities'] += stats.get('total_entities', 0)
                
                if stats['avg_duration'] > 0:
                    worker_durations.append(stats['avg_duration'])
                
                # 检查性能劣化
                degradation_percent = stats.get('performance_degradation_percent')
                if degradation_percent is not None:
                    performance_degradations.append(degradation_percent)
                    logger.warning(
                        f"工作线程 {worker.worker_id} 检测到性能劣化: {degradation_percent:.1f}% "
                        f"(基线: {stats.get('baseline_performance', 0):.3f}s, "
                        f"当前: {stats.get('current_performance', 0):.3f}s)"
                    )
        
        if worker_durations:
            total_stats['avg_duration'] = statistics.mean(worker_durations)
        
        if total_stats['total_operations'] > 0:
            total_stats['success_rate'] = (
                total_stats['successful_operations'] / total_stats['total_operations'] * 100
            )
        
        # 检查数据量限制
        max_data_count = self.config.max_data_count * 10000  # 转换为实际条数
        if total_stats['total_entities'] > max_data_count:
            total_stats['data_limit_exceeded'] = True
            self.data_limit_exceeded = True
            self.stop_reason = f"数据量超过限制: {total_stats['total_entities']} > {max_data_count}"
            logger.error(f"数据量超过限制: {total_stats['total_entities']} > {max_data_count}")
        
        # 检查性能劣化
        if performance_degradations:
            avg_degradation = statistics.mean(performance_degradations)
            total_stats['performance_degradation_detected'] = True
            total_stats['avg_degradation_percent'] = avg_degradation
            self.performance_degradation_detected = True
            self.stop_reason = f"检测到性能劣化: 平均{avg_degradation:.1f}%"
            logger.error(f"检测到性能劣化: 平均{avg_degradation:.1f}%")
        
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'elapsed_minutes': self.get_elapsed_minutes(),
            'current_phase': self.current_phase.value,
            'metrics': total_stats
        }
        
        self.metrics_history.append(metrics)
        return metrics
    
    def get_elapsed_minutes(self) -> float:
        """获取已过时间（分钟）"""
        if not self.start_time:
            return 0
        elapsed = datetime.now() - self.start_time
        return elapsed.total_seconds() / 60
    
    def should_continue(self) -> bool:
        """判断是否应该继续测试"""
        if not self.start_time:
            return True
        
        # 检查停止条件
        if self.data_limit_exceeded:
            logger.error(f"测试停止: {self.stop_reason}")
            return False
        
        if self.performance_degradation_detected:
            logger.error(f"测试停止: {self.stop_reason}")
            return False
        
        # 检查时间限制
        elapsed_minutes = self.get_elapsed_minutes()
        total_minutes = self.config.duration_hours * 60
        
        return elapsed_minutes < total_minutes
    
    def stop(self):
        """停止监控"""
        self.end_time = datetime.now()
        logger.info(f"老化测试监控结束: {self.end_time}")
        
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        if not self.start_time:
            return {}
        
        end_time = self.end_time or datetime.now()
        total_duration = (end_time - self.start_time).total_seconds()
        
        # 汇总所有阶段的指标
        total_operations = sum(m['metrics'].get('total_operations', 0) for m in self.metrics_history)
        successful_operations = sum(m['metrics'].get('successful_operations', 0) for m in self.metrics_history)
        total_entities = self.metrics_history[-1]['metrics'].get('total_entities', 0) if self.metrics_history else 0
        
        report = {
            'test_info': {
                'start_time': self.start_time.isoformat(),
                'end_time': end_time.isoformat(),
                'total_duration_seconds': total_duration,
                'total_duration_hours': total_duration / 3600,
                'config': {
                    'duration_hours': self.config.duration_hours,
                    'concurrent_threads': self.config.concurrent_threads,
                    'operation_interval': self.config.operation_interval,
                    'base_data_count': self.config.base_data_count,
                    'max_data_count': self.config.max_data_count,
                    'performance_degradation_threshold': self.config.performance_degradation_threshold
                }
            },
            'summary': {
                'total_operations': total_operations,
                'successful_operations': successful_operations,
                'failed_operations': total_operations - successful_operations,
                'success_rate': (successful_operations / total_operations * 100) if total_operations > 0 else 0,
                'total_entities': total_entities,
                'data_limit_exceeded': self.data_limit_exceeded,
                'performance_degradation_detected': self.performance_degradation_detected,
                'stop_reason': self.stop_reason,
                'phase_history': self.phase_history
            },
            'metrics_history': self.metrics_history,
            'analysis': self._analyze_metrics()
        }
        
        return report
    
    def _analyze_metrics(self) -> Dict[str, Any]:
        """分析指标"""
        if not self.metrics_history:
            return {}
        
        # 按阶段分析
        phase_metrics = {}
        for phase in TestPhase:
            phase_data = [m for m in self.metrics_history if m.get('current_phase') == phase.value]
            if phase_data:
                phase_metrics[phase.value] = {
                    'duration_minutes': len(phase_data) * (self.config.report_interval_minutes or 30),
                    'avg_success_rate': statistics.mean(
                        [m['metrics'].get('success_rate', 0) for m in phase_data]
                    ) if phase_data else 0,
                    'avg_duration': statistics.mean(
                        [m['metrics'].get('avg_duration', 0) for m in phase_data]
                    ) if phase_data else 0,
                    'total_entities': phase_data[-1]['metrics'].get('total_entities', 0) if phase_data else 0
                }
        
        # 趋势分析
        success_rates = [m['metrics'].get('success_rate', 0) for m in self.metrics_history]
        durations = [m['metrics'].get('avg_duration', 0) for m in self.metrics_history]
        entity_counts = [m['metrics'].get('total_entities', 0) for m in self.metrics_history]
        
        # 性能劣化分析
        performance_degradation_data = []
        for metrics in self.metrics_history:
            if metrics['metrics'].get('performance_degradation_detected'):
                performance_degradation_data.append({
                    'timestamp': metrics['timestamp'],
                    'degradation_percent': metrics['metrics'].get('avg_degradation_percent', 0),
                    'elapsed_minutes': metrics['elapsed_minutes']
                })
        
        analysis = {
            'phase_analysis': phase_metrics,
            'trend_analysis': {
                'success_rate_trend': 'stable' if len(success_rates) < 2 else (
                    'improving' if success_rates[-1] > success_rates[0] else 'declining'
                ),
                'duration_trend': 'stable' if len(durations) < 2 else (
                    'improving' if durations[-1] < durations[0] else 'worsening'
                ),
                'entity_growth_trend': 'stable' if len(entity_counts) < 2 else (
                    'growing' if entity_counts[-1] > entity_counts[0] else 'shrinking'
                ),
                'final_success_rate': success_rates[-1] if success_rates else 0,
                'final_avg_duration': durations[-1] if durations else 0,
                'final_entity_count': entity_counts[-1] if entity_counts else 0,
                'entity_growth_rate': ((entity_counts[-1] - entity_counts[0]) / entity_counts[0] * 100) 
                    if entity_counts and entity_counts[0] > 0 else 0
            },
            'performance_analysis': {
                'degradation_detected': self.performance_degradation_detected,
                'degradation_events': performance_degradation_data,
                'degradation_threshold': self.config.performance_degradation_threshold,
                'data_limit_exceeded': self.data_limit_exceeded,
                'max_data_limit': self.config.max_data_count * 10000,
                'final_data_usage_percent': (entity_counts[-1] / (self.config.max_data_count * 10000) * 100) 
                    if entity_counts and self.config.max_data_count > 0 else 0
            },
            'recommendations': self._generate_recommendations()
        }
        
        return analysis
    
    def _generate_recommendations(self) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if not self.metrics_history:
            return recommendations
        
        final_metrics = self.metrics_history[-1]['metrics']
        success_rate = final_metrics.get('success_rate', 0)
        avg_duration = final_metrics.get('avg_duration', 0)
        total_entities = final_metrics.get('total_entities', 0)
        
        if self.data_limit_exceeded:
            recommendations.append(f"数据量已超过限制({self.config.max_data_count}万条)，建议优化数据清理策略或扩容数据库")
        
        if self.performance_degradation_detected:
            recommendations.append("检测到性能劣化，建议检查数据库索引、查询优化和服务器资源")
        
        if success_rate < 95:
            recommendations.append("系统稳定性需要提升，建议检查服务器资源和数据库性能")
        
        if avg_duration > 1.0:
            recommendations.append("响应时间较长，建议优化接口性能和数据库查询")
        
        if final_metrics.get('failed_operations', 0) > 0:
            recommendations.append("存在失败操作，建议检查错误日志并修复问题")
        
        # 数据量相关建议
        max_entities = self.config.max_data_count * 10000
        if total_entities > max_entities * 0.8:
            recommendations.append(f"数据量接近限制({total_entities}/{max_entities})，建议提前规划数据清理或扩容")
        
        return recommendations


class AgingTestRunner:
    """老化测试运行器"""
    
    def __init__(self, config: Optional[AgingTestConfig] = None):
        self.config = config or AgingTestConfig()
        self.monitor = AgingTestMonitor(self.config)
        self.workers: List[AgingTestWorker] = []
        self.stop_event = threading.Event()
        self.report_thread: Optional[threading.Thread] = None
        
    def run(self):
        """运行老化测试"""
        logger.info("开始长期老化测试")
        logger.info(f"测试配置: {self.config}")
        
        try:
            # 启动监控
            self.monitor.start()
            
            # 预热阶段
            self._run_phase(TestPhase.WARMUP, self.config.warmup_minutes)
            
            # 稳定运行阶段
            steady_hours = self.config.duration_hours - (
                self.config.warmup_minutes / 60 + 1  # 预留1小时给峰值阶段
            )
            if steady_hours > 0:
                self._run_phase(TestPhase.STEADY, steady_hours * 60)
            
            # 峰值压力阶段
            self._run_phase(TestPhase.PEAK, 60, multiplier=self.config.peak_multiplier)
            
            # 冷却阶段
            self._run_phase(TestPhase.COOLDOWN, 15)
            
        except KeyboardInterrupt:
            logger.info("测试被用户中断")
        except Exception as e:
            logger.error(f"测试运行异常: {e}")
        finally:
            # 停止测试
            self.stop()
            
            # 生成最终报告
            report = self.monitor.generate_report()
            self._save_report(report)
            
            logger.info("长期老化测试完成")
    
    def _run_phase(self, phase: TestPhase, duration_minutes: float, multiplier: float = 1.0):
        """运行特定阶段"""
        logger.info(f"开始 {phase.value} 阶段，持续时间: {duration_minutes} 分钟")
        
        # 更新监控阶段
        self.monitor.update_phase(phase)
        
        # 调整并发线程数
        thread_count = int(self.config.concurrent_threads * multiplier)
        
        # 启动工作线程
        self._start_workers(thread_count)
        
        # 启动报告线程
        self._start_report_thread()
        
        # 运行指定时间
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        while datetime.now() < end_time and not self.stop_event.is_set():
            time.sleep(1.0)
        
        # 停止工作线程
        self._stop_workers()
        
        logger.info(f"{phase.value} 阶段完成")
    
    def _start_workers(self, thread_count: int):
        """启动工作线程"""
        # 停止现有工作线程
        self._stop_workers()
        
        # 创建新的工作线程
        self.workers = []
        for i in range(thread_count):
            worker = AgingTestWorker(i, self.config)
            self.workers.append(worker)
        
        # 启动工作线程
        for worker in self.workers:
            thread = threading.Thread(
                target=worker.run,
                args=(self.stop_event,),
                daemon=True
            )
            thread.start()
        
        logger.info(f"启动 {thread_count} 个工作线程")
    
    def _stop_workers(self):
        """停止工作线程"""
        self.stop_event.set()
        time.sleep(2.0)  # 给线程时间停止
        self.stop_event.clear()
        
        # 清空工作线程列表
        self.workers = []
        logger.info("工作线程已停止")
    
    def _start_report_thread(self):
        """启动报告线程"""
        if self.report_thread and self.report_thread.is_alive():
            return
        
        def report_generator():
            while not self.stop_event.is_set():
                try:
                    # 记录指标
                    metrics = self.monitor.record_metrics(self.workers)
                    
                    # 打印状态
                    self._print_status(metrics)
                    
                    # 保存中间报告
                    if self.config.report_interval_minutes > 0:
                        time.sleep(self.config.report_interval_minutes * 60)
                    else:
                        time.sleep(300)  # 默认5分钟
                        
                except Exception as e:
                    logger.error(f"报告线程异常: {e}")
                    time.sleep(60)
        
        self.report_thread = threading.Thread(target=report_generator, daemon=True)
        self.report_thread.start()
        logger.info("报告线程已启动")
    
    def _print_status(self, metrics: Dict[str, Any]):
        """打印状态"""
        if not metrics:
            return
        
        m = metrics['metrics']
        elapsed = metrics['elapsed_minutes']
        phase = metrics['current_phase']
        
        status = (
            f"[老化测试] 阶段: {phase}, 已运行: {elapsed:.1f}分钟, "
            f"操作数: {m.get('total_operations', 0)}, "
            f"成功率: {m.get('success_rate', 0):.1f}%, "
            f"平均耗时: {m.get('avg_duration', 0):.3f}s"
        )
        
        logger.info(status)
    
    def _save_report(self, report: Dict[str, Any]):
        """保存测试报告"""
        if not report:
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"aging_test_report_{timestamp}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"测试报告已保存到: {report_file}")
        
        # 同时生成简化的文本报告
        self._generate_text_report(report, f"aging_test_summary_{timestamp}.txt")
    
    def _generate_text_report(self, report: Dict[str, Any], filename: str):
        """生成文本报告"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("长期老化测试报告\n")
            f.write("=" * 60 + "\n\n")
            
            # 测试信息
            test_info = report.get('test_info', {})
            f.write("测试信息:\n")
            f.write(f"  开始时间: {test_info.get('start_time', 'N/A')}\n")
            f.write(f"  结束时间: {test_info.get('end_time', 'N/A')}\n")
            f.write(f"  总时长: {test_info.get('total_duration_hours', 0):.2f} 小时\n")
            f.write(f"  并发线程数: {test_info.get('config', {}).get('concurrent_threads', 0)}\n\n")
            
            # 测试摘要
            summary = report.get('summary', {})
            f.write("测试摘要:\n")
            f.write(f"  总操作数: {summary.get('total_operations', 0)}\n")
            f.write(f"  成功操作: {summary.get('successful_operations', 0)}\n")
            f.write(f"  失败操作: {summary.get('failed_operations', 0)}\n")
            f.write(f"  成功率: {summary.get('success_rate', 0):.2f}%\n\n")
            
            # 阶段历史
            f.write("测试阶段:\n")
            for phase in summary.get('phase_history', []):
                f.write(f"  - {phase.get('phase', 'N/A')}: "
                       f"{phase.get('elapsed_minutes', 0):.1f}分钟\n")
            f.write("\n")
            
            # 分析结果
            analysis = report.get('analysis', {})
            trend = analysis.get('trend_analysis', {})
            f.write("趋势分析:\n")
            f.write(f"  成功率趋势: {trend.get('success_rate_trend', 'N/A')}\n")
            f.write(f"  响应时间趋势: {trend.get('duration_trend', 'N/A')}\n")
            f.write(f"  最终成功率: {trend.get('final_success_rate', 0):.2f}%\n")
            f.write(f"  最终平均耗时: {trend.get('final_avg_duration', 0):.3f}秒\n\n")
            
            # 建议
            recommendations = analysis.get('recommendations', [])
            if recommendations:
                f.write("改进建议:\n")
                for i, rec in enumerate(recommendations, 1):
                    f.write(f"  {i}. {rec}\n")
            else:
                f.write("系统表现良好，无需特别改进。\n")
            
            f.write("\n" + "=" * 60 + "\n")
        
        logger.info(f"文本报告已保存到: {filename}")
    
    def stop(self):
        """停止测试"""
        logger.info("停止老化测试")
        self.stop_event.set()
        self.monitor.stop()
        
        if self.report_thread and self.report_thread.is_alive():
            self.report_thread.join(timeout=5.0)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='长期老化测试')
    parser.add_argument('--duration', type=int, default=24,
                       help='测试持续时间（小时），默认24小时')
    parser.add_argument('--threads', type=int, default=10,
                       help='并发线程数，默认10')
    parser.add_argument('--interval', type=float, default=1.0,
                       help='操作间隔（秒），默认1.0')
    parser.add_argument('--warmup', type=int, default=5,
                       help='预热时间（分钟），默认5')
    parser.add_argument('--peak-multiplier', type=float, default=2.0,
                       help='峰值压力倍数，默认2.0')
    parser.add_argument('--data-count', type=int, default=100,
                       help='基础数据量，默认100')
    parser.add_argument('--report-interval', type=int, default=30,
                       help='报告生成间隔（分钟），默认30')
    
    args = parser.parse_args()
    
    config = AgingTestConfig(
        duration_hours=args.duration,
        concurrent_threads=args.threads,
        operation_interval=args.interval,
        warmup_minutes=args.warmup,
        peak_multiplier=args.peak_multiplier,
        base_data_count=args.data_count,
        report_interval_minutes=args.report_interval
    )
    
    runner = AgingTestRunner(config)
    runner.run()


if __name__ == '__main__':
    main()