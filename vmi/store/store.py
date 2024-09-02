from mock import common as mock
from session import session, common
from cas.cas import cas


"""
{
    "id": 199,
    "cod": "CK-0001",
    "name": "testCK",
    "description": "测试仓库描述"
}
"""


def mock_store_param():
    return {
        'name': 'STORE'+mock.name(),
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

    store_instance = common.MagicEntity("/vmi/store", work_session)
    store_param = mock_store_param()
    new_store001 = store_instance.insert(store_param)
    if not new_store001:
        print('create new store failed')
        return

    cur_store001 = store_instance.query(new_store001['id'])
    if not cur_store001:
        print('query new store failed')

    cur_store001['description'] = mock.sentence()
    cur_store001 = store_instance.update(new_store001['id'], new_store001)
    if not cur_store001:
        print('update new store failed')

    store_instance.delete(new_store001['id'])



