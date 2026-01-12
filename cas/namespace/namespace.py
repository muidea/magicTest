"""Namespace"""

import logging
import time as dt
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class Namespace:
    """Namespace"""

    def __init__(self, work_session, defaultNamespace):
        self.session = work_session
        self.defaultNamespace = defaultNamespace

    def filter_namespace(self, param):
        val = self.session.get('/cas/namespaces/', param)
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
        val = self.session.post('/cas/namespaces/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建命名空间错误, 名称: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建命名空间请求失败: 无响应, 名称: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_namespace(self, param):
        val = self.session.put('/cas/namespaces/{0}'.format(param['id']), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新命名空间错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新命名空间请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_namespace(self, param):
        val = self.session.delete('/cas/namespaces/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除命名空间错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除命名空间请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_namespace_param():
    # 获取当前 UTC 时间戳（毫秒）
    current_time_ms = int(dt.time() * 1000)
    # 生成未来30天的 UTC 毫秒时间戳作为过期时间
    expire_time_ms = current_time_ms + 30 * 24 * 60 * 60 * 1000
    
    return {
        'name': common.word(),
        'description': common.sentence(),
        'status': 2,  # 启用状态
        'startTime': current_time_ms,  # UTC 毫秒时间戳
        'expireTime': expire_time_ms,  # UTC 毫秒时间戳
        'scope': '*'  # 全局作用域
    }


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
    
    # 保存原始参数用于验证
    original_param = param.copy()
    
    new_namespace = app.create_namespace(param)
    if not new_namespace:
        logger.error('创建命名空间失败')
        return False

    # 验证创建返回的命名空间包含所有必要字段
    required_fields = ['id', 'name', 'description', 'status', 'startTime', 'expireTime', 'scope']
    for field in required_fields:
        if field not in new_namespace:
            logger.error('创建命名空间失败, 缺少字段: %s', field)
            return False

    # 验证字段值匹配（除了id和可能由服务器生成的时间字段）
    if new_namespace['name'] != original_param['name']:
        logger.error('创建命名空间失败, 名称不匹配')
        return False
    if new_namespace['description'] != original_param['description']:
        logger.error('创建命名空间失败, 描述不匹配')
        return False
    if new_namespace['status'] != original_param['status']:
        logger.error('创建命名空间失败, 状态不匹配')
        return False
    if new_namespace['scope'] != original_param['scope']:
        logger.error('创建命名空间失败, 作用域不匹配')
        return False

    filter_value = {
        'name': new_namespace['name'],
    }

    namespace_list = app.filter_namespace(filter_value)
    if not namespace_list or len(namespace_list) != 1:
        logger.error('过滤命名空间失败')
        return False
    
    # 验证过滤结果中的字段
    filtered_ns = namespace_list[0]
    if filtered_ns['name'] != new_namespace['name']:
        logger.error('过滤命名空间失败, 名称不匹配')
        return False
    if filtered_ns['description'] != new_namespace['description']:
        logger.error('过滤命名空间失败, 描述不匹配')
        return False
    if filtered_ns['status'] != new_namespace['status']:
        logger.error('过滤命名空间失败, 状态不匹配')
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        logger.error('查询命名空间失败')
        return False

    # 更新命名空间 - 修改多个字段
    param["description"] = common.sentence()
    param['status'] = 1  # 改为禁用状态
    param['scope'] = 'n1,n2'  # 修改作用域
    param['id'] = cur_namespace['id']
    
    new_namespace = app.update_namespace(param)
    if not new_namespace:
        logger.error('更新命名空间失败')
        return False

    # 验证更新后的字段
    if new_namespace['description'] != param['description']:
        logger.error("更新命名空间失败, 描述不匹配")
        return False
    if new_namespace['status'] != param['status']:
        logger.error("更新命名空间失败, 状态不匹配")
        return False
    if new_namespace['scope'] != param['scope']:
        logger.error("更新命名空间失败, 作用域不匹配")
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        logger.error('查询命名空间失败')
        return False
    
    # 验证查询结果与更新结果一致
    if new_namespace['description'] != cur_namespace['description']:
        logger.error("更新命名空间失败, 查询的描述不匹配")
        return False
    if new_namespace['status'] != cur_namespace['status']:
        logger.error("更新命名空间失败, 查询的状态不匹配")
        return False
    if new_namespace['scope'] != cur_namespace['scope']:
        logger.error("更新命名空间失败, 查询的作用域不匹配")
        return False

    old_namespace = app.delete_namespace(new_namespace['id'])
    if not old_namespace:
        logger.error('删除命名空间失败')
        return False
    if old_namespace['id'] != cur_namespace['id']:
        logger.error('删除命名空间失败, 命名空间ID不匹配')
        return False
    
    # 验证删除的命名空间包含必要字段
    if 'id' not in old_namespace or 'name' not in old_namespace:
        logger.error('删除命名空间失败, 返回数据不完整')
        return False
        
    return True

