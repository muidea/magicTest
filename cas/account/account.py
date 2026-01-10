"""Account"""

import logging
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class Account:
    """Account"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_account(self, param):
        val = self.session.get('/cas/accounts', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤账户错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤账户请求失败: 无响应')
            return None
        return val.get('values')

    def query_account(self, param):
        val = self.session.get('/cas/accounts/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询账户错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询账户请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')

    def create_account(self, param):
        val = self.session.post('/cas/accounts', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建账户错误, 账户: %s', param.get('account', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建账户请求失败: 无响应, 账户: %s', param.get('account', '未知'))
            return None
        return val.get('value')

    def update_account(self, param):
        val = self.session.put('/cas/accounts/{0}'.format(param['id']), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新账户错误, ID: %s', param['id'])
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新账户请求失败: 无响应, ID: %s', param['id'])
            return None
        return val.get('value')

    def delete_account(self, param):
        val = self.session.delete('/cas/accounts/{0}'.format(param))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除账户错误, ID: %s', param)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除账户请求失败: 无响应, ID: %s', param)
            return None
        return val.get('value')


def mock_account_param(namespace):
    return {
        'account': common.word(),
        'password': '123',
        'email': common.email(),
        'description': common.sentence(),
        'namespace': namespace
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Account(work_session)
    new_account = app.create_account(mock_account_param(namespace))
    if not new_account:
        logger.error('创建账户失败')
        return False

    filter_value = {
        'account': new_account['account'],
        'email': new_account['email'],
    }

    account_list = app.filter_account(filter_value)
    if not account_list or len(account_list) != 1:
        logger.error('过滤账户失败')
        return False
    if account_list[0]['account'] != new_account['account'] or account_list[0]['email'] != new_account['email']:
        logger.error('过滤账户失败, 账户不匹配')
        return False

    cur_account = app.query_account(new_account['id'])
    if not cur_account:
        logger.error('查询账户失败')
        return False

    cur_account["description"] = common.sentence()
    new_account = app.update_account(cur_account)
    if not new_account:
        logger.error('更新账户失败')
        return False

    cur_account = app.query_account(new_account['id'])
    if not cur_account:
        logger.error('查询账户失败')
        return
    if new_account['description'] != cur_account['description']:
        logger.error("更新账户失败, 描述不匹配")
        return False

    old_account = app.delete_account(new_account['id'])
    if not old_account:
        logger.error('删除账户失败')
        return False
    if old_account['id'] != cur_account['id']:
        logger.error('删除账户失败, 账户ID不匹配')
        return False

    return True
