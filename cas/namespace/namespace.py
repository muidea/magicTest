"""Namespace"""

from session import session
from cas import cas
from mock import common


class Namespace:
    """Namespace"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_namespace(self, param):
        val = self.session.get('/cas/namespace/query/', param)
        if val and val['errorCode'] == 0:
            return val['namespace']

        print('--------filter_namespace-----------')
        print(val['reason'])
        return None

    def query_namespace(self, param):
        val = self.session.get('/cas/namespace/query/{0}'.format(param))
        if val and val['errorCode'] == 0:
            return val['namespace']

        print('--------query_namespace-----------')
        print(val['reason'])
        return None

    def create_namespace(self, param):
        val = self.session.post('/cas/namespace/create/', param)
        if val and val['errorCode'] == 0:
            return val['namespace']

        return None

    def update_namespace(self, param):
        val = self.session.put('/cas/namespace/update/{0}'.format(param['id']), param)
        if val and val['errorCode'] == 0:
            return val['namespace']

        print('--------update_namespace-----------')
        print(val['reason'])
        return None

    def delete_namespace(self, param):
        val = self.session.delete('/cas/namespace/delete/{0}'.format(param))
        if val and val['errorCode'] == 0:
            return val['namespace']

        print('--------delete_namespace-----------')
        print(val['reason'])
        return None


def mock_namespace_param():
    return {'name': common.word(), 'description': common.sentence(), 'validity': 10}


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Namespace(work_session)
    param = mock_namespace_param()
    new_namespace = app.create_namespace(param)
    if not new_namespace:
        print('create namespace failed')
        return False

    duplicate_namespace = app.create_namespace(new_namespace)
    if duplicate_namespace:
        print('create duplicate namespace failed')
        return False

    filter_value = {
        'name': new_namespace['name'],
    }

    namespace_list = app.filter_namespace(filter_value)
    if not namespace_list or len(namespace_list) != 1:
        print('filter namespace failed')
        return False
    if namespace_list[0]['name'] != new_namespace['name'] or namespace_list[0]['description'] != new_namespace['description']:
        print('filter namespace failed')
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        print('query namespace failed')
        return False

    param["description"] = common.sentence()
    param['id'] = cur_namespace['id']
    new_namespace = app.update_namespace(param)
    if not new_namespace:
        print('update namespace failed')
        return False

    cur_namespace = app.query_namespace(new_namespace['id'])
    if not cur_namespace:
        print('query namespace failed')
        return False
    if new_namespace['description'] != cur_namespace['description']:
        print("update namespace failed")
        return False

    old_namespace = app.delete_namespace(new_namespace['id'])
    if not old_namespace:
        print('delete namespace failed')
        return False
    if old_namespace['id'] != cur_namespace['id']:
        print('delete namespace failed, mismatch namespace')
        return False
    return True

