#!/usr/bin/env python3
"""
pytest配置文件 - 定义核心fixtures

这个文件包含所有测试共享的fixtures，包括：
1. 会话管理fixtures
2. SDK客户端fixtures
3. 测试数据工厂
4. 配置和工具fixtures
"""

import pytest
import logging
import time
import random
import uuid
from typing import Dict, Any, Generator, Optional
from datetime import datetime

# 配置日志
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_config() -> Dict[str, Any]:
    """测试配置fixture - 从统一配置文件读取"""
    import json
    import os
    
    config_path = os.path.join(os.path.dirname(__file__), 'test_config.json')
    
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    
    config = {
        'server_url': cfg['server']['url'],
        'namespace': cfg['server']['namespace'],
        'credentials': cfg['credentials'],
        'refresh_interval': cfg['session']['refresh_interval'],
        'session_timeout': cfg['session']['timeout'],
        'pytest': cfg.get('pytest', {}),
        'concurrent': cfg.get('concurrent', {}),
        'aging': cfg.get('aging', {}),
    }
    
    logger.info(f"测试配置加载完成 - 服务器: {config['server_url']}")
    return config


@pytest.fixture(scope="session")
def session_manager(test_config) -> Generator:
    """全局会话管理器fixture - 会话级别
    
    提供自动会话刷新功能，9分钟刷新一次
    """
    from session_manager import SessionManager
    
    logger.info("初始化全局会话管理器")
    
    mgr = SessionManager(
        server_url=test_config['server_url'],
        namespace=test_config['namespace'],
        username=test_config['credentials']['username'],
        password=test_config['credentials']['password'],
        refresh_interval=test_config['refresh_interval'],
        session_timeout=test_config['session_timeout']
    )
    
    # 创建会话
    if not mgr.create_session():
        pytest.fail("创建会话失败")
    
    # 启动自动刷新
    mgr.start_auto_refresh()
    
    logger.info("会话管理器初始化完成，自动刷新已启动")
    
    yield mgr
    
    # 清理
    logger.info("清理会话管理器")
    mgr.stop_auto_refresh()
    mgr.close_session()


@pytest.fixture(scope="session")
def work_session(session_manager) -> Any:
    """工作会话fixture - 会话级别"""
    session = session_manager.get_session()
    if not session:
        pytest.fail("获取工作会话失败")
    return session


@pytest.fixture(scope="session")
def cas_session(session_manager) -> Any:
    """CAS会话fixture - 会话级别"""
    session = session_manager.get_cas_session()
    if not session:
        pytest.fail("获取CAS会话失败")
    return session


@pytest.fixture(scope="session")
def sdk_clients(work_session) -> Dict[str, Any]:
    """SDK客户端fixture - 会话级别
    
    返回所有SDK客户端的字典
    """
    try:
        from sdk import (
            WarehouseSDK, ShelfSDK, StoreSDK, ProductSDK,
            PartnerSDK, GoodsSDK, StockinSDK, StockoutSDK
        )
        
        clients = {
            'warehouse': WarehouseSDK(work_session),
            'shelf': ShelfSDK(work_session),
            'store': StoreSDK(work_session),
            'product': ProductSDK(work_session),
            'partner': PartnerSDK(work_session),
            'goods': GoodsSDK(work_session),
            'stockin': StockinSDK(work_session),
            'stockout': StockoutSDK(work_session),
        }
        
        logger.debug("SDK客户端初始化完成")
        return clients
        
    except ImportError as e:
        pytest.fail(f"导入SDK失败: {e}")
    except Exception as e:
        pytest.fail(f"初始化SDK客户端失败: {e}")


@pytest.fixture
def ensure_session_valid(session_manager) -> bool:
    """确保会话有效的fixture - 函数级别
    
    在每个测试前检查会话状态，如果无效则尝试恢复
    """
    from session_manager import ensure_session_valid as esv
    
    if not esv(session_manager):
        logger.warning("会话无效，尝试重新连接")
        if session_manager.reconnect():
            logger.info("会话重新连接成功")
            return True
        else:
            pytest.fail("会话重新连接失败")
    
    # 更新活动时间
    session_manager.update_activity()
    return True


@pytest.fixture
def execute_with_session_check(session_manager, ensure_session_valid):
    """带会话检查的执行fixture - 函数级别
    
    包装操作函数，自动处理会话检查和重试
    """
    def _execute(operation_func, *args, **kwargs):
        # 确保会话有效
        if not ensure_session_valid:
            pytest.fail("会话无效且无法恢复，操作中止")
        
        try:
            # 执行操作
            result = operation_func(*args, **kwargs)
            
            # 更新活动时间
            session_manager.update_activity()
            
            return result
            
        except Exception as e:
            # 检查是否是会话超时错误
            error_msg = str(e).lower()
            session_errors = ['session', 'token', 'auth', 'login', 'unauthorized', 'timeout']
            
            if any(error in error_msg for error in session_errors):
                logger.warning(f"操作可能因会话问题失败: {e}")
                
                # 尝试重新连接并重试
                logger.info("尝试重新连接并重试操作")
                if session_manager.reconnect():
                    # 重试操作
                    try:
                        result = operation_func(*args, **kwargs)
                        session_manager.update_activity()
                        logger.info("重试操作成功")
                        return result
                    except Exception as retry_error:
                        logger.error(f"重试操作失败: {retry_error}")
                        raise retry_error
                else:
                    logger.error("重新连接失败")
                    raise e
            else:
                # 其他错误，直接抛出
                raise e
    
    return _execute


# 测试数据工厂fixtures
@pytest.fixture
def random_partner_data() -> Dict[str, Any]:
    """随机合作伙伴数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    
    return {
        'name': f'测试合作伙伴_{timestamp}_{random_id}',
        'telephone': f'138{random.randint(10000000, 99999999)}',
        'wechat': f'wechat_{random_id}',
        'description': f'测试合作伙伴描述_{timestamp}',
        'status': {'id': 3}
    }


@pytest.fixture
def random_product_data() -> Dict[str, Any]:
    """随机产品数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    
    return {
        'name': f'测试产品_{timestamp}_{random_id}',
        'code': f'PROD_{random_id:04d}',
        'price': round(random.uniform(10.0, 1000.0), 2),
        'description': f'测试产品描述_{timestamp}',
        'status': {'id': 1}
    }


@pytest.fixture
def random_goods_data(random_product_data) -> Dict[str, Any]:
    """随机商品数据工厂"""
    timestamp = int(time.time())
    random_id = random.randint(1000, 9999)
    
    return {
        'name': f'测试商品_{timestamp}_{random_id}',
        'code': f'GOODS_{random_id:04d}',
        'sku': f'SKU_{random_id:04d}_{timestamp}',
        'price': round(random.uniform(5.0, 500.0), 2),
        'count': random.randint(1, 1000),
        'description': f'测试商品描述_{timestamp}',
        'status': {'id': 1},
        'product': {'id': 1},           # 默认产品ID
        'shelf': [{'id': 1}],           # shelf应该是数组
        'store': {'id': 1}              # 需要store字段
    }


@pytest.fixture
def random_stockin_data(random_goods_data) -> Dict[str, Any]:
    """随机入库数据工厂"""
    timestamp = int(time.time())
    
    return {
        'warehouse': {'id': 1},
        'goodsInfo': [{
            'id': 1,
            'sku': f'SKU_{random.randint(1000, 9999):04d}_{timestamp}',
            'product': {'id': 1},
            'type': 1,
            'count': random.randint(1, 100),
            'price': round(random.uniform(5.0, 500.0), 2),
            'shelf': [{'id': 1}]
        }],
        'quantity': random.randint(1, 100),
        'type': 'in',
        'remark': f'测试入库_{timestamp}',
        'operator': f'operator_{random.randint(1, 100)}',
        'status': {'id': 1},
        'store': {'id': 1}
    }


@pytest.fixture
def random_stockout_data(random_goods_data) -> Dict[str, Any]:
    """随机出库数据工厂"""
    timestamp = int(time.time())
    
    return {
        'warehouse': {'id': 1},
        'goodsInfo': [{
            'id': 1,
            'sku': f'SKU_{random.randint(1000, 9999):04d}_{timestamp}',
            'product': {'id': 1},
            'type': 2,
            'count': random.randint(1, 50),
            'price': round(random.uniform(5.0, 500.0), 2),
            'shelf': [{'id': 1}]
        }],
        'quantity': random.randint(1, 50),
        'type': 'out',
        'remark': f'测试出库_{timestamp}',
        'operator': f'operator_{random.randint(1, 100)}',
        'status': {'id': 1},
        'store': {'id': 1}
    }


@pytest.fixture
def entity_cleanup(sdk_clients) -> Generator:
    """实体清理fixture - 函数级别
    
    自动清理测试创建的实体
    """
    created_entities = {
        'partner': [],
        'product': [],
        'goods': [],
        'stockin': [],
        'stockout': []
    }
    
    yield created_entities
    
    # 测试结束后清理实体
    logger.info("清理测试创建的实体")
    
    for entity_type, entity_ids in created_entities.items():
        if not entity_ids:
            continue
            
        sdk_client = sdk_clients.get(entity_type)
        if not sdk_client:
            continue
            
        for entity_id in entity_ids:
            try:
                if entity_type == 'partner':
                    sdk_client.delete_partner(int(entity_id))
                elif entity_type == 'product':
                    sdk_client.delete_product(int(entity_id))
                elif entity_type == 'goods':
                    sdk_client.delete_goods(int(entity_id))
                elif entity_type == 'stockin':
                    sdk_client.delete_stockin(int(entity_id))
                elif entity_type == 'stockout':
                    sdk_client.delete_stockout(int(entity_id))
                
                logger.debug(f"清理 {entity_type} ID: {entity_id}")
            except Exception as e:
                logger.warning(f"清理 {entity_type} ID: {entity_id} 失败: {e}")


@pytest.fixture
def performance_monitor():
    """性能监控fixture - 函数级别"""
    from performance_monitor import PerformanceMonitor
    
    monitor = PerformanceMonitor()
    monitor.start()
    
    yield monitor
    
    monitor.stop()
    
    # 生成性能报告
    report = monitor.generate_report()
    if report:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = f"performance_report_{timestamp}.json"
        
        import json
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"性能报告已保存到: {report_file}")


# 自定义pytest钩子
def pytest_sessionstart(session):
    """测试会话开始时调用"""
    logger.info("=" * 60)
    logger.info("VMI测试会话开始")
    logger.info("=" * 60)


def pytest_sessionfinish(session, exitstatus):
    """测试会话结束时调用"""
    logger.info("=" * 60)
    logger.info(f"VMI测试会话结束 - 退出状态: {exitstatus}")
    logger.info("=" * 60)


def pytest_runtest_logstart(nodeid, location):
    """测试开始运行时调用"""
    test_name = nodeid.split("::")[-1]
    logger.info(f"开始测试: {test_name}")


def pytest_runtest_logfinish(nodeid, location):
    """测试结束运行时调用"""
    test_name = nodeid.split("::")[-1]
    logger.info(f"结束测试: {test_name}")