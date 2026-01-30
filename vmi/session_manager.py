#!/usr/bin/env python3
"""
会话管理器 - 管理测试会话的创建、刷新和超时处理
"""

import time
import logging
import threading
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器类
    
    管理测试会话的生命周期，包括：
    1. 会话创建和登录
    2. 定期刷新避免超时
    3. 超时检测和自动重新登录
    """
    
    def __init__(self, server_url: str, namespace: str, 
                 username: str, password: str,
                 refresh_interval: int = 540,  # 9分钟刷新一次（服务器要求不超过10分钟）
                 session_timeout: int = 1800):  # 30分钟会话超时
        """初始化会话管理器
        
        Args:
            server_url: 服务器URL
            namespace: 命名空间
            username: 用户名
            password: 密码
            refresh_interval: 刷新间隔（秒）
            session_timeout: 会话超时时间（秒）
        """
        self.server_url = server_url
        self.namespace = namespace
        self.username = username
        self.password = password
        self.refresh_interval = refresh_interval
        self.session_timeout = session_timeout
        
        # 会话相关对象
        self.work_session = None
        self.cas_session = None
        
        # 会话状态
        self.last_activity_time = 0
        self.last_refresh_time = 0
        self.is_logged_in = False
        
        # 刷新线程
        self.refresh_thread = None
        self.stop_refresh = threading.Event()
    
    def create_session(self) -> bool:
        """创建会话并登录
        
        Returns:
            登录是否成功
        """
        try:
            # 添加必要的Python路径
            import sys
            import os
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            
            # 确保session模块在路径中
            session_path = os.path.join(parent_dir, 'session')
            if session_path not in sys.path:
                sys.path.insert(0, session_path)
            
            import session
            
            # 确保cas模块在路径中
            cas_dir = os.path.join(parent_dir, 'cas')
            if cas_dir not in sys.path:
                sys.path.insert(0, cas_dir)
            
            from cas.cas import Cas
            
            # 创建会话
            self.work_session = session.MagicSession(self.server_url, self.namespace)
            self.cas_session = Cas(self.work_session)
            
            # 登录
            if not self.cas_session.login(self.username, self.password):
                logger.error("会话管理器: 登录失败")
                return False
            
            self.work_session.bind_token(self.cas_session.get_session_token())
            
            # 更新状态
            self.last_activity_time = time.time()
            self.last_refresh_time = time.time()
            self.is_logged_in = True
            
            logger.info("会话管理器: 登录成功")
            return True
            
        except Exception as e:
            logger.error(f"会话管理器: 创建会话失败 - {e}")
            return False
    
    def refresh_session(self) -> bool:
        """刷新会话
        
        Returns:
            刷新是否成功
        """
        if not self.is_logged_in or not self.cas_session:
            logger.warning("会话管理器: 尝试刷新未登录的会话")
            return False
        
        try:
            session_token = self.cas_session.get_session_token()
            if not session_token:
                logger.warning("会话管理器: 会话令牌为空，需要重新登录")
                return self.reconnect()
            
            # 调用刷新API
            new_token = self.cas_session.refresh(session_token)
            if new_token:
                self.work_session.bind_token(new_token)
                self.last_refresh_time = time.time()
                self.last_activity_time = time.time()
                logger.debug("会话管理器: 会话刷新成功")
                return True
            else:
                logger.warning("会话管理器: 会话刷新失败，尝试重新登录")
                return self.reconnect()
                
        except Exception as e:
            logger.error(f"会话管理器: 刷新会话异常 - {e}")
            return self.reconnect()
    
    def reconnect(self) -> bool:
        """重新连接（重新登录）
        
        Returns:
            重新登录是否成功
        """
        logger.info("会话管理器: 尝试重新登录")
        
        # 关闭现有会话
        self.close_session()
        
        # 创建新会话
        return self.create_session()
    
    def close_session(self):
        """关闭会话"""
        if self.work_session:
            try:
                self.work_session.close()
            except:
                pass
        
        self.work_session = None
        self.cas_session = None
        self.is_logged_in = False
        self.stop_refresh.set()
        
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.refresh_thread.join(timeout=5)
    
    def start_auto_refresh(self):
        """启动自动刷新线程"""
        if self.refresh_thread and self.refresh_thread.is_alive():
            logger.warning("会话管理器: 自动刷新线程已在运行")
            return
        
        self.stop_refresh.clear()
        self.refresh_thread = threading.Thread(
            target=self._refresh_worker,
            daemon=True,
            name="SessionRefreshThread"
        )
        self.refresh_thread.start()
        logger.info("会话管理器: 自动刷新线程已启动")
    
    def stop_auto_refresh(self):
        """停止自动刷新线程"""
        self.stop_refresh.set()
        if self.refresh_thread and self.refresh_thread.is_alive():
            self.refresh_thread.join(timeout=5)
            logger.info("会话管理器: 自动刷新线程已停止")
    
    def _refresh_worker(self):
        """刷新工作线程"""
        logger.debug("会话管理器: 刷新工作线程启动")
        
        while not self.stop_refresh.is_set():
            try:
                # 检查是否需要刷新
                current_time = time.time()
                time_since_refresh = current_time - self.last_refresh_time
                time_since_activity = current_time - self.last_activity_time
                
                # 如果超过刷新间隔，刷新会话
                if time_since_refresh >= self.refresh_interval:
                    logger.debug(f"会话管理器: 达到刷新间隔({self.refresh_interval}s)，刷新会话")
                    self.refresh_session()
                
                # 如果超过会话超时时间，重新登录
                elif time_since_activity >= self.session_timeout:
                    logger.warning(f"会话管理器: 会话超时({self.session_timeout}s)，重新登录")
                    self.reconnect()
                
                # 休眠1分钟检查一次
                time.sleep(60)
                
            except Exception as e:
                logger.error(f"会话管理器: 刷新工作线程异常 - {e}")
                time.sleep(60)
        
        logger.debug("会话管理器: 刷新工作线程退出")
    
    def update_activity(self):
        """更新活动时间"""
        self.last_activity_time = time.time()
    
    def get_session(self):
        """获取当前会话
        
        Returns:
            work_session对象
        """
        self.update_activity()
        return self.work_session
    
    def get_cas_session(self):
        """获取CAS会话
        
        Returns:
            cas_session对象
        """
        return self.cas_session
    
    def is_session_valid(self) -> bool:
        """检查会话是否有效
        
        Returns:
            会话是否有效
        """
        if not self.is_logged_in:
            return False
        
        current_time = time.time()
        time_since_activity = current_time - self.last_activity_time
        
        # 如果超过超时时间的一半，认为可能需要刷新
        if time_since_activity > self.session_timeout / 2:
            logger.debug(f"会话管理器: 会话已空闲{time_since_activity:.0f}s，建议刷新")
        
        return time_since_activity < self.session_timeout


# 全局会话管理器实例
_global_session_manager = None


def get_global_session_manager() -> Optional[SessionManager]:
    """获取全局会话管理器
    
    Returns:
        全局会话管理器实例
    """
    return _global_session_manager


def init_global_session_manager(server_url: str, namespace: str, 
                               username: str, password: str,
                               refresh_interval: int = 540,  # 9分钟（服务器要求不超过10分钟）
                               session_timeout: int = 1800) -> SessionManager:
    """初始化全局会话管理器
    
    Args:
        server_url: 服务器URL
        namespace: 命名空间
        username: 用户名
        password: 密码
        refresh_interval: 刷新间隔（秒）
        session_timeout: 会话超时时间（秒）
    
    Returns:
        初始化的会话管理器
    """
    global _global_session_manager
    
    if _global_session_manager:
        _global_session_manager.close_session()
    
    _global_session_manager = SessionManager(
        server_url, namespace, username, password,
        refresh_interval, session_timeout
    )
    
    return _global_session_manager


def ensure_session_valid(session_manager: SessionManager = None) -> bool:
    """确保会话有效
    
    Args:
        session_manager: 会话管理器，如果为None则使用全局管理器
    
    Returns:
        会话是否有效
    """
    if session_manager is None:
        session_manager = _global_session_manager
    
    if not session_manager:
        logger.error("会话管理器: 未初始化会话管理器")
        return False
    
    # 检查会话是否有效
    if not session_manager.is_session_valid():
        logger.warning("会话管理器: 会话无效，尝试重新连接")
        return session_manager.reconnect()
    
    return True