"""Account"""

from session import session
from cas import cas
from mock import common


class Endpoint:
    """Endpoint"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_endpoint(self, param):
        val = self.session.get('/cas/endpoint/filter/', param)
        if 'error' in val:
            print('--------filter_endpoint-----------')
            print(f"Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('values')

    def query_endpoint(self, param):
        val = self.session.get('/cas/endpoint/query/{0}'.format(param))
        if 'error' in val:
            print('--------query_endpoint-----------')
            print(f"Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def create_endpoint(self, param):
        val = self.session.post('/cas/endpoint/create/', param)
        if 'error' in val:
            print('--------create_endpoint-----------')
            print(f"Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def update_endpoint(self, param):
        val = self.session.put('/cas/endpoint/update/{0}'.format(param['id']), param)
        if 'error' in val:
            print('--------update_endpoint-----------')
            print(f"Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def delete_endpoint(self, param):
        val = self.session.delete('/cas/endpoint/delete/{0}'.format(param))
        if 'error' in val:
            print('--------delete_endpoint-----------')
            print(f"Code: {val['error']['code']}, Message: {val['error']['message']}")
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
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())
    app = Endpoint(work_session)
    new_endpoint = app.create_endpoint(mock_endpoint_param())
    if not new_endpoint:
        print('create endpoint failed')
        return False

    duplicate_endpoint = app.create_endpoint(new_endpoint)
    if duplicate_endpoint:
        print('create duplicate endpoint failed')
        return False

    filter_value = {
        'endpoint': new_endpoint['endpoint'],
    }

    endpoint_list = app.filter_endpoint(filter_value)
    if not endpoint_list or len(endpoint_list) != 1:
        print('filter endpoint failed')
        return False
    if endpoint_list[0]['endpoint'] != new_endpoint['endpoint'] or endpoint_list[0]['authToken'] != new_endpoint['authToken']:
        print('filter endpoint failed')
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        print('query endpoint failed')
        return False

    cur_endpoint["description"] = common.sentence()
    new_endpoint = app.update_endpoint(cur_endpoint)
    if not new_endpoint:
        print('update endpoint failed')
        return False

    cur_endpoint = app.query_endpoint(new_endpoint['id'])
    if not cur_endpoint:
        print('query endpoint failed')
        return False
    if new_endpoint['description'] != cur_endpoint['description']:
        print("update endpoint failed")
        return False

    old_endpoint = app.delete_endpoint(new_endpoint['id'])
    if not old_endpoint:
        print('delete endpoint failed')
        return False
    if old_endpoint['id'] != cur_endpoint['id']:
        print('delete endpoint failed, mismatch endpoint')
        return False
    return True
