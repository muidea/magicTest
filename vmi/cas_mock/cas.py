"""
cas模块模拟 - 用于测试框架
"""

import logging


logger = logging.getLogger(__name__)


class Cas:
    def __init__(self, session):
        self.session = session
        self.token = None

    def login(self, username, password):
        """模拟登录"""
        logger.info("[Cas Mock] 模拟登录: %s", username)
        self.token = f"mock_token_{username}"
        return True

    def get_session_token(self):
        """获取会话令牌"""
        return self.token if self.token else "mock_default_token"
