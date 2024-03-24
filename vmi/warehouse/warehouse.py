from mock import common as mock
from session import session, common
from cas.cas import cas


def mock_warehouse_param():
    return {
        'name': mock.name(),
        'description': mock.sentence(),
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())

    warehouse_instance = common.MagicEntity("/vmi/warehouse", work_session)
    warehouse_param = mock_warehouse_param()
    new_warehouse001 = warehouse_instance.insert(warehouse_param)
    if not new_warehouse001:
        print('create new warehouse failed')
        return

    warehouse_instance.delete(new_warehouse001['id'])



