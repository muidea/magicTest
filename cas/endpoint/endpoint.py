"""Account"""

import logging
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class Endpoint:
    """Endpoint"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_endpoint(self, param):
        val = self.session.get('/cas/endpoints', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤端点错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤端点请求失败: 无响应')
            return None
        return val.get('values')

    def query_endpoint(self, param):
        val = self.session.get('/cas/endpoints/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询端点错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询端点请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')

    def create_endpoint(self, param):
        val = self.session.post('/cas/endpoints', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建端点错误, 端点: %s', param.get('endpoint', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建端点请求失败: 无响应, 端点: %s', param.get('endpoint', '未知'))
            return None
        return val.get('value')

    def update_endpoint(self, param):
        val = self.session.put('/cas/endpoints/{0}'.format(param['id']), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新端点错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新端点请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_endpoint(self, param):
        val = self.session.delete('/cas/endpoints/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除端点错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除端点请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_endpoint_param():
    return {
        'endpoint': common.word(),
        'description': common.sentence(),
        'authToken': common.word(),
        'status': {"id": 0, "name": ""},
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Endpoint(work_session)
    new_endpoint = app.create_endpoint(mock_endpoint_param())
    if not new_endpoint:
        logger.error('创建端点失败')
        return False

    duplicate_endpoint = app.create_endpoint(new_endpoint)
    if duplicate_endpoint:
        logger.error('创建重复端点失败')
        return False

    filter_value = {
        'endpoint': new_endpoint['endpoint'],
    }

    endpoint_list = app.filter_endpoint(filter_value)
    if not endpoint_list or len(endpoint_list) != 1:
        logger.error('过滤端点失败')
        return False
    if endpoint_list[0]['endpoint'] != new_endpoint['endpoint'] or endpoint_list[0]['authToken'] != new_endpoint['authToken']:
        logger.error('过滤端点失败, 端点或认证令牌不匹配')
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        logger.error('查询端点失败')
        return False

    cur_endpoint["description"] = common.sentence()
    new_endpoint = app.update_endpoint(cur_endpoint)
    if not new_endpoint:
        logger.error('更新端点失败')
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        logger.error('查询端点失败')
        return False
    if new_endpoint['description'] != cur_endpoint['description']:
        logger.error("更新端点失败, 描述不匹配")
        return False

    old_endpoint = app.delete_endpoint(new_endpoint['id'])
    if not old_endpoint:
        logger.error('删除端点失败')
        return False
    if old_endpoint['id'] != cur_endpoint['id']:
        logger.error('删除端点失败, 端点ID不匹配')
        return False
    return True
