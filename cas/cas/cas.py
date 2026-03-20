"""Cas"""

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from session import MagicSession

# 配置日志
logger = logging.getLogger(__name__)


class Cas:
    """Cas"""

    def __init__(self, work_session):
        self.session = work_session
        self.session_token = None
        self.current_entity = None
        self.last_error = None
        self.last_response = None

    def get_session_token(self):
        """get_session_token"""
        return self.session_token

    def get_current_entity(self):
        return self.current_entity

    def get_last_error(self):
        return self.last_error

    def _set_response(self, val):
        self.last_response = val
        self.last_error = None if val is None else val.get('error')
        return val

    def _extract_entity(self, val):
        if not isinstance(val, dict):
            return None
        return val.get('entity') or val.get('value') or val.get('vlaue')

    def _decode_session_claims(self) -> Optional[Dict[str, Any]]:
        """解码当前 JWT token claims。"""
        if not self.session_token:
            return None
        try:
            parts = self.session_token.split('.')
            if len(parts) != 3:
                return None
            payload = parts[1]
            payload += '=' * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(payload.encode('utf-8'))
            return json.loads(decoded.decode('utf-8'))
        except Exception as exc:
            logger.error('解码 session token 失败: %s', exc)
            return None

    def get_session_claims(self) -> Optional[Dict[str, Any]]:
        """返回当前 JWT token claims。"""
        return self._decode_session_claims()

    def get_session_id(self) -> Optional[str]:
        """从 JWT session token 中提取内部 sessionID。"""
        claims = self._decode_session_claims()
        if claims is None:
            return None
        return claims.get('_sessionID')

    def get_session_scope(self) -> Optional[str]:
        """从 JWT session token 中提取当前 auth scope。"""
        claims = self._decode_session_claims()
        if claims is None:
            return None
        return claims.get('X-Mp-Auth-Scope')

    def login(self, account, password):
        """login"""
        params = {'account': account, 'password': password}
        val = self._set_response(self.session.post('/api/v1/cas/session/login/', params))
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
        self.session.bind_token(self.session_token)
        logger.info('登录成功, 账户: %s, 实体: %s', account, self.current_entity)
        return self.session_token is not None

    def logout(self, session_token):
        """logout"""
        self.session.bind_token(session_token)
        val = self._set_response(self.session.delete('/api/v1/cas/session/logout/'))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('注销失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('注销失败: 无响应')
            return False
        self.session_token = None
        self.current_entity = None
        self.session.bind_token(None)
        logger.info('注销成功')
        return True

    def refresh(self, session_token):
        """verify"""
        self.session.bind_token(session_token)
        val = self._set_response(self.session.get('/api/v1/cas/session/refresh/'))
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
        self.session.bind_token(self.session_token)
        logger.info('会话刷新成功, 实体: %s', self.current_entity)
        return self.session_token

    def get_system_all_privileges(self):
        """get_system_all_privileges"""
        val = self._set_response(self.session.get('/api/v1/cas/privileges/'))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('获取权限失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('获取权限失败: 无响应')
        else:
            return val.get('values')

    def filter_entity(self, param: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """获取实体列表。"""
        val = self._set_response(self.session.get('/api/v1/cas/entitys/', param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('获取实体列表失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('获取实体列表失败: 无响应')
            return None
        return val.get('values') or val.get('entity')

    def query_entity(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """查询单个实体。"""
        val = self._set_response(self.session.get(f'/api/v1/cas/entitys/{entity_id}'))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询实体失败, ID: %s', entity_id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询实体失败: 无响应, ID: %s', entity_id)
            return None
        return self._extract_entity(val)

    def query_entity_role(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """查询实体当前角色绑定。"""
        val = self._set_response(self.session.get(f'/api/v1/cas/entity/roles/{entity_id}'))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询实体角色失败, ID: %s', entity_id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询实体角色失败: 无响应, ID: %s', entity_id)
            return None
        return val.get('value')

    def verify_session_namespace(self) -> bool:
        """验证当前 session 是否有权访问当前 namespace。"""
        val = self._set_response(self.session.get('/api/v1/cas/session/namespace/verify/'))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('验证 session namespace 失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('验证 session namespace 失败: 无响应')
            return False
        return True

    def verify_session_entity(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证当前 session 对实体绑定是否仍然有效。"""
        val = self._set_response(self.session.post('/api/v1/cas/session/entity/verify/', param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('验证 session entity 失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('验证 session entity 失败: 无响应')
            return None
        return self._extract_entity(val)

    def verify_session_entity_role(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """验证当前 session 的实体与角色绑定。"""
        val = self._set_response(self.session.post('/api/v1/cas/session/entity/role/verify/', param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('验证 session entity role 失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('验证 session entity role 失败: 无响应')
            return None
        return val.get('value')

    def update_account_password(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新 account 密码。"""
        val = self._set_response(self.session.put('/api/v1/cas/account/password/', param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新 account 密码失败')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新 account 密码失败: 无响应')
            return None
        return val.get('value')

    def verify_account(self, account: str, password: str) -> Optional[Dict[str, Any]]:
        """校验账号密码并返回 account 对应实体。"""
        val = self._set_response(self.session.get('/api/v1/cas/account/verify/', {
            'account': account,
            'password': password,
        }))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('验证 account 失败, account: %s', account)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('验证 account 失败: 无响应, account: %s', account)
            return None
        return self._extract_entity(val)

    def allocate_auth_secret(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """为 account/endpoint 对应的实体签发 AuthSecret。"""
        val = self._set_response(self.session.post('/api/v1/cas/entity/authsecret/', param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('签发 AuthSecret 失败, endpoint: %s', param.get('endpoint'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('签发 AuthSecret 失败: 无响应, endpoint: %s', param.get('endpoint'))
            return None
        return val.get('value')

def main(server_url, namespace):
    """main"""
    work_session = MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.refresh(app.session_token)
    privileges = app.get_system_all_privileges()
    print('权限列表: %s', privileges)
    app.logout(app.session_token)
