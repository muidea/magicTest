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
        val = self.session.get('/cas/endpoints/', param)
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
        val = self.session.post('/cas/endpoints/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建端点错误, 端点: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建端点请求失败: 无响应, 端点: %s', param.get('name', '未知'))
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
    import time as dt
    # 获取当前 UTC 时间戳（毫秒）
    current_time_ms = int(dt.time() * 1000)
    # 生成未来30天的 UTC 毫秒时间戳作为过期时间
    expire_time_ms = current_time_ms + 30 * 24 * 60 * 60 * 1000
    
    # 创建 AccountLite 对象
    account_lite = {
        'id': 1,
        'account': 'admin',
        'status': 2  # 启用状态
    }
    
    # 创建 RoleLite 对象
    role_lite = {
        'id': 1,
        'name': 'administrator',
        'status': 2  # 启用状态
    }
    
    return {
        'name': common.word(),
        'description': common.sentence(),
        'account': account_lite,
        'role': role_lite,
        'scope': '*',  # 全局作用域
        'status': 2,  # 启用状态
        'startTime': current_time_ms,  # UTC 毫秒时间戳
        'expireTime': expire_time_ms,  # UTC 毫秒时间戳
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
    param = mock_endpoint_param()
    
    # 保存原始参数用于验证
    original_param = param.copy()
    
    new_endpoint = app.create_endpoint(param)
    if not new_endpoint:
        logger.error('创建端点失败')
        return False

    # 验证创建返回的端点包含所有必要字段
    required_fields = ['id', 'name', 'description', 'account', 'role', 'scope', 'status', 'startTime', 'expireTime']
    for field in required_fields:
        if field not in new_endpoint:
            logger.error('创建端点失败, 缺少字段: %s', field)
            return False

    # 验证字段值匹配（除了id和可能由服务器生成的时间字段）
    if new_endpoint['name'] != original_param['name']:
        logger.error('创建端点失败, 端点地址不匹配')
        return False
    if new_endpoint['description'] != original_param['description']:
        logger.error('创建端点失败, 描述不匹配')
        return False
    if new_endpoint['scope'] != original_param['scope']:
        logger.error('创建端点失败, 作用域不匹配')
        return False
    if new_endpoint['status'] != original_param['status']:
        logger.error('创建端点失败, 状态不匹配')
        return False
    
    # 验证账户信息
    if 'account' not in new_endpoint or not isinstance(new_endpoint['account'], dict):
        logger.error('创建端点失败, 账户信息无效')
        return False
    if new_endpoint['account'].get('account') != original_param['account'].get('account'):
        logger.error('创建端点失败, 账户名称不匹配')
        return False
    
    # 验证角色信息
    if 'role' not in new_endpoint or not isinstance(new_endpoint['role'], dict):
        logger.error('创建端点失败, 角色信息无效')
        return False
    if new_endpoint['role'].get('name') != original_param['role'].get('name'):
        logger.error('创建端点失败, 角色名称不匹配')
        return False

    # 尝试创建重复端点（应该失败）
    duplicate_endpoint = app.create_endpoint(new_endpoint)
    if duplicate_endpoint:
        logger.error('创建重复端点应该失败但成功了')
        return False

    filter_value = {
        'name': new_endpoint['name'],
    }

    endpoint_list = app.filter_endpoint(filter_value)
    if not endpoint_list or len(endpoint_list) != 1:
        logger.error('过滤端点失败')
        return False
    
    # 验证过滤结果中的字段
    filtered_endpoint = endpoint_list[0]
    if filtered_endpoint['name'] != new_endpoint['name']:
        logger.error('过滤端点失败, 端点地址不匹配')
        return False
    if filtered_endpoint['description'] != new_endpoint['description']:
        logger.error('过滤端点失败, 描述不匹配')
        return False
    if filtered_endpoint['scope'] != new_endpoint['scope']:
        logger.error('过滤端点失败, 作用域不匹配')
        return False
    if filtered_endpoint['status'] != new_endpoint['status']:
        logger.error('过滤端点失败, 状态不匹配')
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        logger.error('查询端点失败')
        return False

    # 更新端点 - 修改多个字段
    cur_endpoint["description"] = common.sentence()
    cur_endpoint['scope'] = 'n1,n2'  # 修改作用域
    cur_endpoint['status'] = 1  # 改为禁用状态
    
    # 修改时间字段
    import time as dt
    new_start_time = int(dt.time() * 1000) + 3600000  # 1小时后
    new_expire_time = new_start_time + 7 * 24 * 60 * 60 * 1000  # 7天后
    cur_endpoint['startTime'] = new_start_time
    cur_endpoint['expireTime'] = new_expire_time
    
    new_endpoint = app.update_endpoint(cur_endpoint)
    if not new_endpoint:
        logger.error('更新端点失败')
        return False

    # 验证更新后的字段
    if new_endpoint['description'] != cur_endpoint['description']:
        logger.error("更新端点失败, 描述不匹配")
        return False
    if new_endpoint['scope'] != cur_endpoint['scope']:
        logger.error("更新端点失败, 作用域不匹配")
        return False
    if new_endpoint['status'] != cur_endpoint['status']:
        logger.error("更新端点失败, 状态不匹配")
        return False
    if new_endpoint['startTime'] != cur_endpoint['startTime']:
        logger.error("更新端点失败, 开始时间不匹配")
        return False
    if new_endpoint['expireTime'] != cur_endpoint['expireTime']:
        logger.error("更新端点失败, 过期时间不匹配")
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        logger.error('查询端点失败')
        return False
    
    # 验证查询结果与更新结果一致
    if new_endpoint['description'] != cur_endpoint['description']:
        logger.error("更新端点失败, 查询的描述不匹配")
        return False
    if new_endpoint['scope'] != cur_endpoint['scope']:
        logger.error("更新端点失败, 查询的作用域不匹配")
        return False
    if new_endpoint['status'] != cur_endpoint['status']:
        logger.error("更新端点失败, 查询的状态不匹配")
        return False

    old_endpoint = app.delete_endpoint(new_endpoint['id'])
    if not old_endpoint:
        logger.error('删除端点失败')
        return False
    if old_endpoint['id'] != cur_endpoint['id']:
        logger.error('删除端点失败, 端点ID不匹配')
        return False
    
    # 验证删除的端点包含必要字段
    if 'id' not in old_endpoint or 'name' not in old_endpoint:
        logger.error('删除端点失败, 返回数据不完整')
        return False
        
    return True
