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
        val = self.session.get('/api/v1/cas/roles/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤角色错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤角色请求失败: 无响应')
            return None
        return val.get('values')

    def query_role(self, param):
        val = self.session.get('/api/v1/cas/roles/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询角色错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询角色请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')

    def create_role(self, param):
        val = self.session.post('/api/v1/cas/roles/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建角色错误, 角色: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建角色请求失败: 无响应, 角色: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_role(self, param):
        val = self.session.put('/api/v1/cas/roles/{0}'.format(param['id']), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新角色错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新角色请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_role(self, param):
        val = self.session.delete('/api/v1/cas/roles/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除角色错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除角色请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_role_param(namespace):
    # 生成一个简单的权限列表
    privilege_list = [
        {
            'id': 1,
            'module': 'magicCas',
            'uriPath': '/api/v1/totalizators',
            'value': 2,  # 写权限
            'description': '用户管理权限'
        }
    ]
    
    return {
        'name': common.word(),
        'description': common.sentence(),
        'group': 'admin',  # 管理员组
        'privilege': privilege_list,
        'status': 2,  # 启用状态
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Role(work_session)
    param = mock_role_param(namespace)
    
    # 保存原始参数用于验证
    original_param = param.copy()
    
    new_role = app.create_role(param)
    if not new_role:
        logger.error('创建角色失败')
        return False

    # 验证创建返回的角色包含所有必要字段
    required_fields = ['id', 'name', 'description', 'group', 'privilege', 'status']
    for field in required_fields:
        if field not in new_role:
            logger.error('创建角色失败, 缺少字段: %s', field)
            return False

    # 验证字段值匹配（除了id）
    if new_role['name'] != original_param['name']:
        logger.error('创建角色失败, 名称不匹配')
        return False
    if new_role['description'] != original_param['description']:
        logger.error('创建角色失败, 描述不匹配')
        return False
    if new_role['group'] != original_param['group']:
        logger.error('创建角色失败, 组别不匹配')
        return False
    if new_role['status'] != original_param['status']:
        logger.error('创建角色失败, 状态不匹配')
        return False
    
    # 验证权限列表
    if 'privilege' not in new_role or not isinstance(new_role['privilege'], list):
        logger.error('创建角色失败, 权限列表无效')
        return False
    if len(new_role['privilege']) != len(original_param['privilege']):
        logger.error('创建角色失败, 权限数量不匹配')
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
    
    # 验证过滤结果中的字段
    filtered_role = role_list[0]
    if filtered_role['name'] != new_role['name']:
        logger.error('过滤角色失败, 名称不匹配')
        return False
    if filtered_role['description'] != new_role['description']:
        logger.error('过滤角色失败, 描述不匹配')
        return False
    if filtered_role['group'] != new_role['group']:
        logger.error('过滤角色失败, 组别不匹配')
        return False
    if filtered_role['status'] != new_role['status']:
        logger.error('过滤角色失败, 状态不匹配')
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        logger.error('查询角色失败')
        return False

    # 更新角色 - 修改多个字段
    cur_role["description"] = common.sentence()
    cur_role['group'] = 'user'  # 修改组别
    cur_role['status'] = 1  # 改为禁用状态
    
    # 修改权限列表
    #if cur_role.get('privilege') and isinstance(cur_role['privilege'], list) and len(cur_role['privilege']) > 0:
    #    cur_role['privilege'][0]['value'] = 3  # 修改第一个权限的值
    
    new_role = app.update_role(cur_role)
    if not new_role:
        logger.error('更新角色失败')
        return False

    # 验证更新后的字段
    if new_role['description'] != cur_role['description']:
        logger.error("更新角色失败, 描述不匹配")
        return False
    if new_role['group'] != cur_role['group']:
        logger.error("更新角色失败, 组别不匹配")
        return False
    if new_role['status'] != cur_role['status']:
        logger.error("更新角色失败, 状态不匹配")
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        logger.error('查询角色失败')
        return False
    
    # 验证查询结果与更新结果一致
    if new_role['description'] != cur_role['description']:
        logger.error("更新角色失败, 查询的描述不匹配")
        return False
    if new_role['group'] != cur_role['group']:
        logger.error("更新角色失败, 查询的组别不匹配")
        return False
    if new_role['status'] != cur_role['status']:
        logger.error("更新角色失败, 查询的状态不匹配")
        return False

    old_role = app.delete_role(new_role['id'])
    if not old_role:
        logger.error('删除角色失败')
        return False
    if old_role['id'] != cur_role['id']:
        logger.error('删除角色失败, 角色ID不匹配')
        return False
    
    # 验证删除的角色包含必要字段
    if 'id' not in old_role or 'name' not in old_role:
        logger.error('删除角色失败, 返回数据不完整')
        return False
        
    return True

