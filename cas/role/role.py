"""Role"""

from session import session
from cas import cas
from mock import common


class Role:
    """Role"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_role(self, param):
        val = self.session.get('/cas/roles', param)
        if val.get('error') is not None:
            print('--------filter_role-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('values')

    def query_role(self, param):
        val = self.session.get('/cas/roles/{0}'.format(param))
        if val.get('error') is not None:
            print('--------query_role-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def create_role(self, param):
        val = self.session.post('/cas/roles', param)
        if val.get('error') is not None:
            print('--------create_role-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def update_role(self, param):
        val = self.session.put('/cas/roles/{0}'.format(param['id']), param)
        if val.get('error') is not None:
            print('--------update_role-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def delete_role(self, param):
        val = self.session.delete('/cas/roles/{0}'.format(param))
        if val.get('error') is not None:
            print('--------delete_role-----------')
            print("Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')


def mock_role_param(namespace):
    return {'name': common.word(), 'description': common.sentence(), 'namespace': namespace}


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Role(work_session)
    new_role = app.create_role(mock_role_param(namespace))
    if not new_role:
        print('create role failed')
        return False

    # if duplicate name, update
    duplicate_role = app.create_role(new_role)
    if not duplicate_role:
        print('create duplicate role failed')
        return False

    filter_value = {
        'name': new_role['name'],
    }

    role_list = app.filter_role(filter_value)
    if not role_list or len(role_list) != 1:
        print('filter role failed')
        return False
    if role_list[0]['name'] != new_role['name'] or role_list[0]['description'] != new_role['description']:
        print('filter role failed')
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        print('query role failed')
        return False

    cur_role["description"] = common.sentence()
    new_role = app.update_role(cur_role)
    if not new_role:
        print('update role failed')
        return False

    cur_role = app.query_role(new_role['id'])
    if not cur_role:
        print('query role failed')
        return False
    if new_role['description'] != cur_role['description']:
        print("update role failed")
        return False

    old_role = app.delete_role(new_role['id'])
    if not old_role:
        print('delete role failed')
        return False
    if old_role['id'] != cur_role['id']:
        print('delete role failed, mismatch role')
        return False
    return True

