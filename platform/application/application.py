from mock import common as mock
from session import session


class Application:
    """Application"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_application(self, filter):
        url = '/core/application/filter/'

        val = self.session.post(url, filter)
        if val and val['errorCode'] == 0:
            return val['values']

        print('--------filter_application-----------')
        print(val['reason'])
        return None

    def query_application(self, id):
        val = self.session.get('/core/application/query/{0}'.format(id))
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------query_application-----------')
        print(val['reason'])
        return None

    def create_application(self, param):
        val = self.session.post('/core/application/create/', param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------create_application-----------')
        print(val['reason'])
        return None

    def update_application(self, id, param):
        val = self.session.put('/core/application/update/{0}'.format(id), param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------update_application-----------')
        print(val['reason'])
        return None

    def delete_application(self, id):
        val = self.session.delete('/core/application/destroy/{0}'.format(id))
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------delete_application-----------')
        print(val['reason'])
        return None


def mock_application_param():
    return {
        'uuid': mock.uuid(),
        'name': mock.name(),
        'version': '0.0.1',
        'domain': mock.url(),
        'email': mock.email(),
        'author': mock.name(),
        'description': mock.sentence(),
        'database': {
            'dbserver': '127.0.0.1:3306',
            'dbname': 'testdb',
            'username': 'root',
            'password': 'rootkit',
        }
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    app_instance = Application(work_session)

    app001 = mock_application_param()
    new_app10 = app_instance.create_application(app001)
    if not new_app10:
        print('create new application failed')
        return

    new_app10['version'] = '0.0.2'
    new_app10['description'] = mock.sentence()
    new_app11 = app_instance.update_application(new_app10['id'], new_app10)
    if new_app11['description'] != new_app10['description'] :
        print('update application failed')

    app002 = mock_application_param()
    new_app20 = app_instance.create_application(app002)
    if not new_app20:
        print('create new application failed')
        return

    app_filter = {
        'params': {
            'items': {
                "uuid": '{0}|='.format(app002['uuid'])
            }
        }
    }

    app_list = app_instance.filter_application(app_filter)
    if not app_list:
        print('filter application failed')
    elif len(app_list) != 1:
        print(app_list)
        print('filter application failed, illegal list size')

    app_instance.delete_application(new_app10['id'])
    app_instance.delete_application(new_app20['id'])

