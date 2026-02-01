#!/usr/bin/env python3
"""
多租户会话管理器 - 包装现有的SessionManager以支持多租户测试

特性：
1. 复用现有SessionManager：为每个租户创建独立的SessionManager实例
2. 租户隔离：确保不同租户的会话完全隔离
3. 统一管理：提供统一的接口管理所有租户的会话
4. 向后兼容：默认使用autotest租户，保持现有行为不变
"""

import logging
import threading
import time
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


class MultiTenantSessionManager:
    """多租户会话管理器
    
    管理多个租户的会话，每个租户有独立的SessionManager实例。
    提供统一的接口来管理所有租户的会话生命周期。
    """
    
    def __init__(self, tenant_configs: Dict[str, Dict[str, Any]]):
        """初始化多租户会话管理器
        
        Args:
            tenant_configs: 租户配置字典，格式：
                {
                    "tenant_id": {
                        "server_url": "https://tenant.local.vpc",
                        "username": "admin",
                        "password": "password",
                        "namespace": "tenant",
                        "enabled": True
                    }
                }
        """
        from session_manager import SessionManager
        
        self.tenant_configs = tenant_configs
        self.session_managers: Dict[str, SessionManager] = {}
        self.session_locks: Dict[str, threading.RLock] = {}
        self.is_initialized = False
        
        # 为每个租户创建SessionManager实例和锁
        for tenant_id, config in tenant_configs.items():
            if config.get("enabled", True):
                self.session_managers[tenant_id] = SessionManager(
                    server_url=config["server_url"],
                    namespace=config["namespace"],
                    username=config["username"],
                    password=config["password"]
                )
                self.session_locks[tenant_id] = threading.RLock()
                logger.debug(f"为租户 '{tenant_id}' 创建了SessionManager")
    
    def initialize_all(self) -> Dict[str, bool]:
        """初始化所有租户的会话
        
        Returns:
            字典：租户ID -> 初始化是否成功
        """
        if self.is_initialized:
            logger.warning("多租户会话管理器已经初始化")
            return {tid: True for tid in self.session_managers.keys()}
        
        results = {}
        for tenant_id, session_mgr in self.session_managers.items():
            with self.session_locks[tenant_id]:
                try:
                    success = session_mgr.create_session()
                    if success:
                        session_mgr.start_auto_refresh()
                        logger.info(f"租户 '{tenant_id}' 会话初始化成功")
                    else:
                        logger.error(f"租户 '{tenant_id}' 会话初始化失败")
                    results[tenant_id] = success
                except Exception as e:
                    logger.error(f"租户 '{tenant_id}' 会话初始化异常: {e}")
                    results[tenant_id] = False
        
        self.is_initialized = all(results.values())
        return results
    
    def get_session_manager(self, tenant_id: str = "autotest") -> Optional[Any]:
        """获取指定租户的SessionManager实例
        
        Args:
            tenant_id: 租户ID，默认为"autotest"
            
        Returns:
            SessionManager实例，如果租户不存在则返回None
        """
        return self.session_managers.get(tenant_id)
    
    def get_session(self, tenant_id: str = "autotest") -> Optional[Any]:
        """获取指定租户的工作会话
        
        Args:
            tenant_id: 租户ID，默认为"autotest"
            
        Returns:
            work_session对象，如果租户不存在或未登录则返回None
        """
        session_mgr = self.get_session_manager(tenant_id)
        if not session_mgr:
            logger.warning(f"租户 '{tenant_id}' 不存在")
            return None
        
        with self.session_locks[tenant_id]:
            if not session_mgr.is_logged_in:
                logger.warning(f"租户 '{tenant_id}' 未登录")
                return None
            
            return session_mgr.work_session
    
    def ensure_session_valid(self, tenant_id: str = "autotest") -> bool:
        """确保指定租户的会话有效
        
        Args:
            tenant_id: 租户ID，默认为"autotest"
            
        Returns:
            会话是否有效
        """
        session_mgr = self.get_session_manager(tenant_id)
        if not session_mgr:
            logger.error(f"租户 '{tenant_id}' 不存在")
            return False
        
        with self.session_locks[tenant_id]:
            # 检查会话是否已登录
            if not session_mgr.is_logged_in:
                logger.warning(f"租户 '{tenant_id}' 会话未登录，尝试重新登录")
                return session_mgr.create_session()
            
            # 检查会话是否超时
            current_time = time.time()
            if current_time - session_mgr.last_activity_time > session_mgr.session_timeout:
                logger.warning(f"租户 '{tenant_id}' 会话超时，尝试重新登录")
                return session_mgr.reconnect()
            
            # 检查是否需要刷新
            if current_time - session_mgr.last_refresh_time > session_mgr.refresh_interval:
                logger.debug(f"租户 '{tenant_id}' 会话需要刷新")
                return session_mgr.refresh_session()
            
            return True
    
    def execute_with_session_check(self, tenant_id: str, operation_func, *args, **kwargs) -> Any:
        """在确保会话有效的情况下执行操作
        
        Args:
            tenant_id: 租户ID
            operation_func: 要执行的操作函数
            *args, **kwargs: 操作函数的参数
            
        Returns:
            操作函数的返回值
            
        Raises:
            ValueError: 如果租户不存在
            RuntimeError: 如果会话无效且无法恢复
        """
        session_mgr = self.get_session_manager(tenant_id)
        if not session_mgr:
            raise ValueError(f"租户 '{tenant_id}' 不存在")
        
        with self.session_locks[tenant_id]:
            # 确保会话有效
            if not self.ensure_session_valid(tenant_id):
                raise RuntimeError(f"租户 '{tenant_id}' 会话无效且无法恢复")
            
            # 执行操作
            try:
                result = operation_func(*args, **kwargs)
                # 更新活动时间
                session_mgr.last_activity_time = time.time()
                return result
            except Exception as e:
                logger.error(f"租户 '{tenant_id}' 执行操作失败: {e}")
                raise
    
    def get_all_tenant_ids(self) -> List[str]:
        """获取所有租户ID列表
        
        Returns:
            租户ID列表
        """
        return list(self.session_managers.keys())
    
    def get_enabled_tenant_ids(self) -> List[str]:
        """获取所有启用的租户ID列表
        
        Returns:
            启用的租户ID列表
        """
        enabled_tenants = []
        for tenant_id, config in self.tenant_configs.items():
            if config.get("enabled", True) and tenant_id in self.session_managers:
                enabled_tenants.append(tenant_id)
        return enabled_tenants
    
    def start_all_auto_refresh(self) -> Dict[str, bool]:
        """启动所有租户的自动刷新
        
        Returns:
            字典：租户ID -> 启动是否成功
        """
        results = {}
        for tenant_id, session_mgr in self.session_managers.items():
            with self.session_locks[tenant_id]:
                try:
                    session_mgr.start_auto_refresh()
                    results[tenant_id] = True
                    logger.debug(f"租户 '{tenant_id}' 自动刷新已启动")
                except Exception as e:
                    results[tenant_id] = False
                    logger.error(f"租户 '{tenant_id}' 启动自动刷新失败: {e}")
        return results
    
    def stop_all_auto_refresh(self) -> Dict[str, bool]:
        """停止所有租户的自动刷新
        
        Returns:
            字典：租户ID -> 停止是否成功
        """
        results = {}
        for tenant_id, session_mgr in self.session_managers.items():
            with self.session_locks[tenant_id]:
                try:
                    session_mgr.stop_auto_refresh()
                    results[tenant_id] = True
                    logger.debug(f"租户 '{tenant_id}' 自动刷新已停止")
                except Exception as e:
                    results[tenant_id] = False
                    logger.error(f"租户 '{tenant_id}' 停止自动刷新失败: {e}")
        return results
    
    def close_all_sessions(self) -> Dict[str, bool]:
        """关闭所有租户的会话
        
        Returns:
            字典：租户ID -> 关闭是否成功
        """
        results = {}
        for tenant_id, session_mgr in self.session_managers.items():
            with self.session_locks[tenant_id]:
                try:
                    session_mgr.close_session()
                    results[tenant_id] = True
                    logger.debug(f"租户 '{tenant_id}' 会话已关闭")
                except Exception as e:
                    results[tenant_id] = False
                    logger.error(f"租户 '{tenant_id}' 关闭会话失败: {e}")
        
        self.is_initialized = False
        return results
    
    def get_tenant_status(self, tenant_id: str) -> Dict[str, Any]:
        """获取指定租户的会话状态
        
        Args:
            tenant_id: 租户ID
            
        Returns:
            会话状态字典
        """
        session_mgr = self.get_session_manager(tenant_id)
        if not session_mgr:
            return {"error": f"租户 '{tenant_id}' 不存在"}
        
        with self.session_locks[tenant_id]:
            return {
                "tenant_id": tenant_id,
                "is_logged_in": session_mgr.is_logged_in,
                "server_url": session_mgr.server_url,
                "namespace": session_mgr.namespace,
                "username": session_mgr.username,
                "last_activity_time": session_mgr.last_activity_time,
                "last_refresh_time": session_mgr.last_refresh_time,
                "session_timeout": session_mgr.session_timeout,
                "refresh_interval": session_mgr.refresh_interval,
                "is_auto_refresh_running": session_mgr.refresh_thread is not None and session_mgr.refresh_thread.is_alive()
            }
    
    def get_all_tenant_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有租户的会话状态
        
        Returns:
            字典：租户ID -> 会话状态
        """
        status = {}
        for tenant_id in self.session_managers.keys():
            status[tenant_id] = self.get_tenant_status(tenant_id)
        return status


class SDKFactory:
    """SDK工厂 - 为不同租户创建SDK实例
    
    提供SDK实例的缓存和管理，确保每个租户有独立的SDK实例。
    """
    
    def __init__(self, multi_tenant_mgr: MultiTenantSessionManager):
        """初始化SDK工厂
        
        Args:
            multi_tenant_mgr: 多租户会话管理器实例
        """
        self.multi_tenant_mgr = multi_tenant_mgr
        self.sdk_cache: Dict[str, Dict[str, Any]] = {}  # tenant_id -> {sdk_class_name: sdk_instance}
        self.sdk_cache_lock = threading.RLock()
    
    def get_sdk_for_tenant(self, tenant_id: str, sdk_class) -> Optional[Any]:
        """获取指定租户的SDK实例
        
        Args:
            tenant_id: 租户ID
            sdk_class: SDK类（如WarehouseSDK, ProductSDK等）
            
        Returns:
            SDK实例，如果租户不存在或创建失败则返回None
        """
        sdk_class_name = sdk_class.__name__
        
        with self.sdk_cache_lock:
            # 初始化租户的SDK缓存
            if tenant_id not in self.sdk_cache:
                self.sdk_cache[tenant_id] = {}
            
            # 如果缓存中已有该SDK实例，直接返回
            if sdk_class_name in self.sdk_cache[tenant_id]:
                return self.sdk_cache[tenant_id][sdk_class_name]
            
            # 创建新的SDK实例
            try:
                # 获取租户的工作会话
                work_session = self.multi_tenant_mgr.get_session(tenant_id)
                if not work_session:
                    logger.error(f"无法获取租户 '{tenant_id}' 的工作会话")
                    return None
                
                # 创建SDK实例
                sdk_instance = sdk_class(work_session)
                
                # 缓存SDK实例
                self.sdk_cache[tenant_id][sdk_class_name] = sdk_instance
                logger.debug(f"为租户 '{tenant_id}' 创建了 {sdk_class_name} 实例")
                
                return sdk_instance
                
            except Exception as e:
                logger.error(f"为租户 '{tenant_id}' 创建 {sdk_class_name} 失败: {e}")
                return None
    
    def clear_cache(self, tenant_id: Optional[str] = None):
        """清除SDK缓存
        
        Args:
            tenant_id: 如果指定，只清除该租户的缓存；如果为None，清除所有缓存
        """
        with self.sdk_cache_lock:
            if tenant_id:
                if tenant_id in self.sdk_cache:
                    del self.sdk_cache[tenant_id]
                    logger.debug(f"已清除租户 '{tenant_id}' 的SDK缓存")
            else:
                self.sdk_cache.clear()
                logger.debug("已清除所有SDK缓存")


# 全局多租户管理器实例（单例模式）
_global_multi_tenant_manager = None
_global_multi_tenant_manager_lock = threading.RLock()


def init_global_multi_tenant_manager() -> Optional[MultiTenantSessionManager]:
    """初始化全局多租户管理器
    
    从配置文件中加载租户配置，创建并初始化多租户管理器。
    
    Returns:
        初始化的MultiTenantSessionManager实例，如果失败则返回None
    """
    global _global_multi_tenant_manager
    
    with _global_multi_tenant_manager_lock:
        if _global_multi_tenant_manager is not None:
            logger.warning("全局多租户管理器已经初始化")
            return _global_multi_tenant_manager
        
        try:
            from tenant_config_helper import get_multi_tenant_config
            
            # 获取多租户配置
            config = get_multi_tenant_config()
            
            # 检查多租户是否启用
            if not config["enabled"]:
                logger.info("多租户功能未启用，使用默认autotest租户")
                # 只使用默认租户
                tenant_configs = {"autotest": config["tenants"]["autotest"]}
            else:
                tenant_configs = config["tenants"]
            
            # 创建多租户管理器
            _global_multi_tenant_manager = MultiTenantSessionManager(tenant_configs)
            
            # 初始化所有租户会话
            init_results = _global_multi_tenant_manager.initialize_all()
            
            # 检查初始化结果
            successful_tenants = [tid for tid, success in init_results.items() if success]
            failed_tenants = [tid for tid, success in init_results.items() if not success]
            
            if successful_tenants:
                logger.info(f"多租户管理器初始化成功，成功租户: {successful_tenants}")
            
            if failed_tenants:
                logger.warning(f"多租户管理器初始化部分失败，失败租户: {failed_tenants}")
            
            # 启动自动刷新
            _global_multi_tenant_manager.start_all_auto_refresh()
            
            return _global_multi_tenant_manager
            
        except Exception as e:
            logger.error(f"初始化全局多租户管理器失败: {e}")
            _global_multi_tenant_manager = None
            return None


def get_global_multi_tenant_manager() -> Optional[MultiTenantSessionManager]:
    """获取全局多租户管理器
    
    Returns:
        全局MultiTenantSessionManager实例，如果未初始化则返回None
    """
    global _global_multi_tenant_manager
    
    if _global_multi_tenant_manager is None:
        logger.warning("全局多租户管理器未初始化，尝试初始化")
        return init_global_multi_tenant_manager()
    
    return _global_multi_tenant_manager


def cleanup_global_multi_tenant_manager():
    """清理全局多租户管理器
    
    停止自动刷新并关闭所有会话。
    """
    global _global_multi_tenant_manager
    
    with _global_multi_tenant_manager_lock:
        if _global_multi_tenant_manager is not None:
            try:
                # 停止自动刷新
                _global_multi_tenant_manager.stop_all_auto_refresh()
                
                # 关闭所有会话
                _global_multi_tenant_manager.close_all_sessions()
                
                logger.info("全局多租户管理器已清理")
            except Exception as e:
                logger.error(f"清理全局多租户管理器失败: {e}")
            finally:
                _global_multi_tenant_manager = None


# 测试代码
if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 60)
    print("多租户会话管理器测试")
    print("=" * 60)
    
    # 创建测试配置
    test_tenant_configs = {
        "autotest": {
            "server_url": "https://autotest.local.vpc",
            "username": "administrator",
            "password": "administrator",
            "namespace": "autotest",
            "enabled": True
        },
        "tenant1": {
            "server_url": "https://tenant1.local.vpc",
            "username": "admin1",
            "password": "password1",
            "namespace": "tenant1",
            "enabled": True
        }
    }
    
    try:
        # 创建多租户管理器
        print("创建多租户管理器...")
        mt_manager = MultiTenantSessionManager(test_tenant_configs)
        
        # 获取租户列表
        tenant_ids = mt_manager.get_all_tenant_ids()
        print(f"租户列表: {tenant_ids}")
        
        # 获取启用的租户
        enabled_tenants = mt_manager.get_enabled_tenant_ids()
        print(f"启用的租户: {enabled_tenants}")
        
        # 测试SDK工厂
        print("\n测试SDK工厂...")
        sdk_factory = SDKFactory(mt_manager)
        
        # 模拟获取SDK（实际需要导入真实的SDK类）
        class MockSDK:
            def __init__(self, session):
                self.session = session
                print(f"创建MockSDK，会话: {session}")
        
        # 尝试为租户获取SDK
        for tenant_id in enabled_tenants:
            sdk = sdk_factory.get_sdk_for_tenant(tenant_id, MockSDK)
            if sdk:
                print(f"租户 '{tenant_id}' 的SDK创建成功")
            else:
                print(f"租户 '{tenant_id}' 的SDK创建失败")
        
        print("\n✅ 多租户会话管理器测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()