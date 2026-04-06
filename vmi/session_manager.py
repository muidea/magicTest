#!/usr/bin/env python3
"""
会话管理器 - 管理测试会话的创建、刷新和超时处理
"""

import logging
import os
import threading
import time
from typing import Optional, Tuple

from test_bootstrap import ensure_test_paths

ensure_test_paths(__file__)

from session import MagicSession
from cas.cas import Cas

logger = logging.getLogger(__name__)


class SessionManager:
    """会话管理器类

    管理测试会话的生命周期，包括：
    1. 会话创建和登录
    2. 定期刷新避免超时
    3. 超时检测和自动重新登录
    """

    def __init__(
        self,
        server_url: str,
        namespace: str,
        username: str,
        password: str,
        refresh_interval: int = 540,  # 9分钟刷新一次（服务器要求不超过10分钟）
        session_timeout: int = 1800,
        request_observer=None,
        request_application: Optional[str] = None,
    ):  # 30分钟会话超时
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
        self.request_observer = request_observer
        self.request_application = request_application or os.getenv(
            "MAGICTEST_REQUEST_APPLICATION", ""
        ).strip()

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
        self._session_lock = threading.RLock()

    @staticmethod
    def _session_has_auth(session: Optional[MagicSession]) -> bool:
        if session is None:
            return False
        if getattr(session, "session_token", None):
            return True
        return bool(
            getattr(session, "session_auth_endpoint", None)
            and getattr(session, "session_auth_token", None)
        )

    @staticmethod
    def _summarize_session(session: Optional[MagicSession]) -> str:
        if session is None:
            return "session=None"
        if hasattr(session, "auth_summary"):
            return session.auth_summary()
        return f"session_obj=0x{id(session):x}"

    def create_session(self) -> bool:
        """创建会话并登录

        Returns:
            登录是否成功
        """
        with self._session_lock:
            next_session = None
            try:
                # 先在局部对象上完成登录，避免失败时暴露未认证 session。
                # 若当前已有业务线程持有 work_session，则登录成功后复用该对象，
                # 避免长事务/长场景继续引用旧 session。
                current_session = self.work_session
                next_session = MagicSession(self.server_url, self.namespace)
                next_cas_session = Cas(next_session)

                # 登录
                if not next_cas_session.login(self.username, self.password):
                    logger.error("会话管理器: 登录失败")
                    try:
                        next_session.close()
                    except Exception:
                        pass
                    return False

                session_token = next_cas_session.get_session_token()
                next_session.bind_token(session_token)
                if self.request_application:
                    next_session.bind_application(self.request_application)
                if self.request_observer and hasattr(next_session, "set_request_observer"):
                    next_session.set_request_observer(self.request_observer)

                if not self._session_has_auth(next_session):
                    logger.error("会话管理器: 登录成功但未获得认证信息")
                    try:
                        next_session.close()
                    except Exception:
                        pass
                    return False

                if current_session is not None and current_session is not next_session:
                    current_session.sync_from(next_session)
                    try:
                        next_session.close()
                    except Exception:
                        pass
                    next_cas_session.session = current_session
                    self.work_session = current_session
                else:
                    self.work_session = next_session

                self.cas_session = next_cas_session

                # 更新状态
                self.last_activity_time = time.time()
                self.last_refresh_time = time.time()
                self.is_logged_in = True

                logger.info(
                    "会话管理器: 登录成功%s state=%s",
                    f", application={self.request_application}"
                    if self.request_application
                    else "",
                    self._summarize_session(self.work_session),
                )
                return True

            except Exception as e:
                logger.error(f"会话管理器: 创建会话失败 - {e}")
                if next_session is not None:
                    try:
                        next_session.close()
                    except Exception:
                        pass
                return False

    def refresh_session(self) -> bool:
        """刷新会话

        Returns:
            刷新是否成功
        """
        with self._session_lock:
            if not self.is_logged_in or not self.cas_session:
                logger.warning("会话管理器: 尝试刷新未登录的会话")
                return False

            try:
                session_token = self.cas_session.get_session_token()
                if not session_token:
                    logger.warning(
                        "会话管理器: 会话令牌为空，需要重新登录 state=%s",
                        self._summarize_session(self.work_session),
                    )
                    return self.reconnect()

                # 调用刷新API
                old_summary = self._summarize_session(self.work_session)
                new_token = self.cas_session.refresh(session_token)
                if new_token:
                    self.work_session.bind_token(new_token)
                    self.last_refresh_time = time.time()
                    self.last_activity_time = time.time()
                    logger.info(
                        "会话管理器: 会话刷新成功 old_state=%s new_state=%s",
                        old_summary,
                        self._summarize_session(self.work_session),
                    )
                    return True

                logger.warning(
                    "会话管理器: 会话刷新失败，尝试重新登录 state=%s",
                    self._summarize_session(self.work_session),
                )
                return self.reconnect()

            except Exception as e:
                logger.error(
                    "会话管理器: 刷新会话异常 - %s state=%s",
                    e,
                    self._summarize_session(self.work_session),
                )
                return self.reconnect()

    def reconnect(self) -> bool:
        """重新连接（重新登录）

        Returns:
            重新登录是否成功
        """
        with self._session_lock:
            logger.info(
                "会话管理器: 尝试重新登录 state=%s",
                self._summarize_session(self.work_session),
            )

            in_refresh_thread = self.refresh_thread is threading.current_thread()

            # 创建新会话
            success = self.create_session()
            if success and in_refresh_thread:
                self.stop_refresh.clear()
            logger.info(
                "会话管理器: 重新登录完成 success=%s state=%s",
                success,
                self._summarize_session(self.work_session),
            )
            return success

    def _close_session_locked(self, stop_refresh_thread: bool = True):
        """关闭会话"""
        if self.work_session:
            try:
                self.work_session.close()
            except:
                pass

        self.work_session = None
        self.cas_session = None
        self.is_logged_in = False
        if stop_refresh_thread:
            self.stop_refresh.set()

        current_thread = threading.current_thread()
        if (
            stop_refresh_thread
            and self.refresh_thread
            and self.refresh_thread.is_alive()
            and self.refresh_thread is not current_thread
        ):
            self.refresh_thread.join(timeout=5)

    def close_session(self):
        with self._session_lock:
            self._close_session_locked(stop_refresh_thread=True)

    def start_auto_refresh(self):
        """启动自动刷新线程"""
        if self.refresh_thread and self.refresh_thread.is_alive():
            logger.warning("会话管理器: 自动刷新线程已在运行")
            return

        self.stop_refresh.clear()
        self.refresh_thread = threading.Thread(
            target=self._refresh_worker, daemon=True, name="SessionRefreshThread"
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
                    logger.debug(
                        f"会话管理器: 达到刷新间隔({self.refresh_interval}s)，刷新会话"
                    )
                    self.refresh_session()

                # 如果超过会话超时时间，重新登录
                elif time_since_activity >= self.session_timeout:
                    logger.warning(
                        f"会话管理器: 会话超时({self.session_timeout}s)，重新登录"
                    )
                    self.reconnect()

                # 使用更短的睡眠时间，并检查停止信号
                for _ in range(60):  # 将60秒分解为60个1秒的检查
                    if self.stop_refresh.is_set():
                        break
                    time.sleep(1)

            except Exception as e:
                logger.error(f"会话管理器: 刷新工作线程异常 - {e}")
                # 异常时也使用短睡眠
                for _ in range(60):
                    if self.stop_refresh.is_set():
                        break
                    time.sleep(1)

        logger.debug("会话管理器: 刷新工作线程退出")

    def update_activity(self):
        """更新活动时间"""
        self.last_activity_time = time.time()

    def get_session(self):
        """获取当前会话

        Returns:
            work_session对象
        """
        with self._session_lock:
            self.update_activity()
            if not self.is_logged_in or not self._session_has_auth(self.work_session):
                logger.warning(
                    "会话管理器: 当前会话未认证，拒绝向业务侧暴露 session state=%s is_logged_in=%s",
                    self._summarize_session(self.work_session),
                    self.is_logged_in,
                )
                return None
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


def init_global_session_manager(
    server_url: str,
    namespace: str,
    username: str,
    password: str,
    refresh_interval: int = 540,  # 9分钟（服务器要求不超过10分钟）
    session_timeout: int = 1800,
) -> SessionManager:
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
        server_url, namespace, username, password, refresh_interval, session_timeout
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
