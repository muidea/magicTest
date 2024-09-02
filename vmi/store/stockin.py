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


def mock_stockin_param():
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

    stockin_instance = common.MagicEntity("/vmi/store/stockin", work_session)
    stockin_param = mock_stockin_param()
    new_stockin001 = stockin_instance.insert(stockin_param)
    if not new_stockin001:
        print('create new stockin failed')
        return

    cur_stockin001 = stockin_instance.query(new_stockin001['id'])
    if not cur_stockin001:
        print('query new stockin failed')

    cur_stockin001['description'] = mock.sentence()
    cur_stockin001 = stockin_instance.update(new_stockin001['id'], new_stockin001)
    if not cur_stockin001:
        print('update new stockin failed')

    stockin_instance.delete(new_stockin001['id'])



