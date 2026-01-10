"""Role"""

import logging
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class Role:
    """Role"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_role(self, param):
        val = self.session.get('/cas/roles', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤角色错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤角色请求失败: 无响应')
            return None
        return val.get('values')

    def query_role(self, param):
        val = self.session.get('/cas/roles/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询角色错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询角色请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')

    def create_role(self, param):
        val = self.session.post('/cas/roles', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建角色错误, 角色: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建角色请求失败: 无响应, 角色: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_role(self, param):
        val = self.session.put('/cas/roles/{0}'.format(param['id']), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新角色错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新角色请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_role(self, param):
        val = self.session.delete('/cas/roles/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除角色错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除角色请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_role_param(namespace):
    return {'name': common.word(), 'description': common.sentence(), 'namespace': namespace}


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Role(work_session)
    new_role = app.create_role(mock_role_param(namespace))
    if not new_role:
        logger.error('创建角色失败')
        return False

    # if duplicate name, update
    duplicate_role = app.create_role(new_role)
    if not duplicate_role:
        logger.error('创建重复角色失败')
        return False

    filter_value = {
        'name': new_role['name'],
    }

    role_list = app.filter_role(filter_value)
    if not role_list or len(role_list) != 1:
        logger.error('过滤角色失败')
        return False
    if role_list[0]['name'] != new_role['name'] or role_list[0]['description'] != new_role['description']:
        logger.error('过滤角色失败, 角色不匹配')
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        logger.error('查询角色失败')
        return False

    cur_role["description"] = common.sentence()
    new_role = app.update_role(cur_role)
    if not new_role:
        logger.error('更新角色失败')
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        logger.error('查询角色失败')
        return False
    if new_role['description'] != cur_role['description']:
        logger.error("更新角色失败, 描述不匹配")
        return False

    old_role = app.delete_role(new_role['id'])
    if not old_role:
        logger.error('删除角色失败')
        return False
    if old_role['id'] != cur_role['id']:
        logger.error('删除角色失败, 角色ID不匹配')
        return False
    return True

