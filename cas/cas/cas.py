"""Cas"""

import logging
from session import MagicSession

# 配置日志
logger = logging.getLogger(__name__)


class Cas:
    """Cas"""

    def __init__(self, work_session):
        self.session = work_session
        self.session_token = None
        self.current_entity = None

    def get_session_token(self):
        """get_session_token"""
        return self.session_token

    def get_current_entity(self):
        return self.current_entity

    def login(self, account, password):
        """login"""
        params = {'account': account, 'password': password}
        val = self.session.post('/api/v1/cas/session/login/', params)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('登录失败, 账户: %s', account)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('登录失败: 无响应, 账户: %s', account)
            return False
        value = val.get('value')
        if value is None:
            logger.error('登录失败: 响应值为空, 账户: %s', account)
            return False
        self.session_token = value.get('sessionToken')
        self.current_entity = value.get('entity')
        logger.info('登录成功, 账户: %s, 实体: %s', account, self.current_entity)
        return self.session_token is not None

    def logout(self, session_token):
        """logout"""
        self.session.bind_token(session_token)
        val = self.session.delete('/api/v1/cas/session/logout/')
        if val is None or val.get('error') is not None:
            if val:
                logger.error('注销失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('注销失败: 无响应')
            return False
        logger.info('注销成功')
        return True

    def refresh(self, session_token):
        """verify"""
        self.session.bind_token(session_token)
        val = self.session.get('/api/v1/cas/session/refresh/')
        if val is None or val.get('error') is not None:
            if val:
                logger.error('会话刷新失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('会话刷新失败: 无响应')
            return None
        value = val.get('value')
        if value is None:
            logger.error('会话刷新失败: 响应值为空')
            return None
        self.session_token = value.get('sessionToken')
        self.current_entity = value.get('entity')
        logger.info('会话刷新成功, 实体: %s', self.current_entity)
        return self.session_token

    def get_system_all_privileges(self):
        """get_system_all_privileges"""
        val = self.session.get('/api/v1/cas/privileges/')
        if val is None or val.get('error') is not None:
            if val:
                logger.error('获取权限失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('获取权限失败: 无响应')
        else:
            return  val.get('values')

def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.refresh(app.session_token)
    privileges = app.get_privileges()
    print('权限列表: %s', privileges)
    app.logout(app.session_token)
