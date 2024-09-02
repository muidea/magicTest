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


def mock_stockout_param():
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

    stockout_instance = common.MagicEntity("/vmi/store/stockout", work_session)
    stockout_param = mock_stockout_param()
    new_stockout001 = stockout_instance.insert(stockout_param)
    if not new_stockout001:
        print('create new stockout failed')
        return

    cur_stockout001 = stockout_instance.query(new_stockout001['id'])
    if not cur_stockout001:
        print('query new stockout failed')

    cur_stockout001['description'] = mock.sentence()
    cur_stockout001 = stockout_instance.update(new_stockout001['id'], new_stockout001)
    if not cur_stockout001:
        print('update new stockout failed')

    stockout_instance.delete(new_stockout001['id'])



