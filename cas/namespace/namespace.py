"""Namespace"""

import logging
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class Namespace:
    """Namespace"""

    def __init__(self, work_session, superNamespace):
        self.session = work_session
        self.superNamespace = superNamespace

    def filter_namespace(self, param):
        val = self.session.get('/cas/namespaces', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤命名空间错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤命名空间请求失败: 无响应')
            return None
        return val.get('values')

    def query_namespace(self, param):
        val = self.session.get('/cas/namespaces/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询命名空间错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询命名空间请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')

    def create_namespace(self, param):
        val = self.session.post('/cas/namespaces?X-Mp-Namespace={0}'.format(self.superNamespace), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建命名空间错误, 名称: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建命名空间请求失败: 无响应, 名称: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_namespace(self, param):
        val = self.session.put('/cas/namespaces/{0}?X-Mp-Namespace={1}'.format(param['id'], self.superNamespace), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新命名空间错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新命名空间请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_namespace(self, param):
        val = self.session.delete('/cas/namespaces/{0}?X-Mp-Namespace={1}'.format(param, self.superNamespace))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除命名空间错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除命名空间请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_namespace_param():
    return {'name': common.word(), 'description': common.sentence(), 'validity': 10}


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Namespace(work_session, "super")
    param = mock_namespace_param()
    new_namespace = app.create_namespace(param)
    if not new_namespace:
        logger.error('创建命名空间失败')
        return False

    filter_value = {
        'name': new_namespace['name'],
    }

    namespace_list = app.filter_namespace(filter_value)
    if not namespace_list or len(namespace_list) != 1:
        logger.error('过滤命名空间失败')
        return False
    if namespace_list[0]['name'] != new_namespace['name'] or namespace_list[0]['description'] != new_namespace['description']:
        logger.error('过滤命名空间失败, 名称或描述不匹配')
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        logger.error('查询命名空间失败')
        return False

    param["description"] = common.sentence()
    param['id'] = cur_namespace['id']
    new_namespace = app.update_namespace(param)
    if not new_namespace:
        logger.error('更新命名空间失败')
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        logger.error('查询命名空间失败')
        return False
    if new_namespace['description'] != cur_namespace['description']:
        logger.error("更新命名空间失败, 描述不匹配")
        return False

    old_namespace = app.delete_namespace(new_namespace['id'])
    if not old_namespace:
        logger.error('删除命名空间失败')
        return False
    if old_namespace['id'] != cur_namespace['id']:
        logger.error('删除命名空间失败, 命名空间ID不匹配')
        return False
    return True

