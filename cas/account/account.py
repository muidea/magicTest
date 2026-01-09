"""Account"""

from session import session
from cas import cas
from mock import common


class Account:
    """Account"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_account(self, param):
        val = self.session.get('/cas/accounts', param)
        if val.get('error') is not None:
            print('--------filter_account-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('values')

    def query_account(self, param):
        val = self.session.get('/cas/accounts/{0}'.format(param))
        if val.get('error') is not None:
            print('--------query_account-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def create_account(self, param):
        val = self.session.post('/cas/accounts', param)
        if val.get('error') is not None:
            print('--------create_account-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def update_account(self, param):
        val = self.session.put('/cas/accounts/{0}'.format(param['id']), param)
        if val.get('error') is not None:
            print('--------update_account-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def delete_account(self, param):
        val = self.session.delete('/cas/accounts/{0}'.format(param))
        if val.get('error') is not None:
            print('--------delete_account-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
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
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Account(work_session)
    new_account = app.create_account(mock_account_param(namespace))
    if not new_account:
        print('create account failed')
        return False

    duplicate_account = app.create_account(new_account)
    if duplicate_account:
        print('create duplicate account failed')
        return False

    filter_value = {
        'account': new_account['account'],
        'email': new_account['email'],
    }

    account_list = app.filter_account(filter_value)
    if not account_list or len(account_list) != 1:
        print('filter account failed')
        return False
    if account_list[0]['account'] != new_account['account'] or account_list[0]['email'] != new_account['email']:
        print('filter account failed, mismatch account')
        return False

    cur_account = app.query_account(new_account['id'])
    if not cur_account:
        print('query account failed')
        return False

    cur_account["description"] = common.sentence()
    new_account = app.update_account(cur_account)
    if not new_account:
        print('update account failed')
        return False

    cur_account = app.query_account(new_account['id'])
    if not cur_account:
        print('query account failed')
        return
    if new_account['description'] != cur_account['description']:
        print("update account failed")
        return False

    old_account = app.delete_account(new_account['id'])
    if not old_account:
        print('delete account failed')
        return False
    if old_account['id'] != cur_account['id']:
        print('delete account failed, mismatch account')
        return False

    return True
