from mock import common as mock
from session import session, common
from cas.cas import cas
from warehouse import warehouse


"""
{
    "id": 100,
    "code": "HJ-0003"
    "description": "保利书或月达断学就达格领。",
    "used": 10,
    "capacity": 77,
    "warehouse": 1
}
"""


def mock_shelf_param(warehouse):
    return {
        'name': 'HJ'+mock.name(),
        'description': mock.sentence(),
        'capacity': mock.int(),
        'warehouse': warehouse['id'],
    }


def setup_data(session):
    warehouse_instance = common.MagicEntity("/vmi/warehouse", session)
    warehouse_param = warehouse.mock_warehouse_param()
    new_warehouse001 = warehouse_instance.insert(warehouse_param)
    if not new_warehouse001:
        print('create new warehouse failed')
        return None
    return new_warehouse001


def teardown_data(session, warehouse):
    warehouse_instance = common.MagicEntity("/vmi/warehouse", session)
    warehouse_instance.delete(warehouse['id'])


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return

    work_session.bind_token(cas_session.get_session_token())

    warehouse_val = setup_data(work_session)
    if not warehouse_val:
        print('setup_date failed')
        return

    shelf_instance = common.MagicEntity("/vmi/warehouse/shelf", work_session)
    shelf_param = mock_shelf_param(warehouse_val)
    new_shelf001 = shelf_instance.insert(shelf_param)
    if not new_shelf001:
        print('create new shelf failed')
        teardown_data(work_session, warehouse_val)
        return

    cur_shelf001 = shelf_instance.query(new_shelf001['id'])
    if not cur_shelf001:
        print('query new shelf failed')

    cur_shelf001['description'] = mock.sentence()
    cur_shelf001 = shelf_instance.update(new_shelf001['id'], new_shelf001)
    if not cur_shelf001:
        print('update new shelf failed')

    shelf_instance.delete(new_shelf001['id'])

    teardown_data(work_session, warehouse_val)


