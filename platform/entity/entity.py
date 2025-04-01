from mock import common as mock
from session import session

from application import application
from block import block


basic_type_element = [
        {
            'value': 100,
            'name': 'bool',
            'pkgPath': '',
        },
        {
            'value': 101,
            'name': 'int8',
            'pkgPath': '',
        },
        {
            'value': 102,
            'name': 'int16',
            'pkgPath': '',
        },
        {
            'value': 103,
            'name': 'int32',
            'pkgPath': '',
        },
        {
            'value': 104,
            'name': 'int',
            'pkgPath': '',
        },
        {
            'value': 105,
            'name': 'int64',
            'pkgPath': '',
        },
        {
            'value': 106,
            'name': 'uint8',
            'pkgPath': '',
        },
        {
            'value': 107,
            'name': 'uint16',
            'pkgPath': '',
        },
        {
            'value': 108,
            'name': 'uint32',
            'pkgPath': '',
        },
        {
            'value': 109,
            'name': 'uint',
            'pkgPath': '',
        },
        {
            'value': 110,
            'name': 'uint64',
            'pkgPath': '',
        },
        {
            'value': 111,
            'name': 'float32',
            'pkgPath': '',
        },
        {
            'value': 112,
            'name': 'float64',
            'pkgPath': '',
        },
        {
            'value': 113,
            'name': 'string',
            'pkgPath': '',
        },
        {
            'value': 114,
            'name': 'time',
            'pkgPath': '',
        },
    ]

compose_type_element = [
    {
        'value': 115,
        'name': 'struct',
        'pkgPath': '',
    },
    {
        'value': 116,
        'name': 'slice',
        'pkgPath': '',
    },
]


class Entity:
    """Entity"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_entity(self, filter):
        url = '/core/entity/filter/'

        val = self.session.post(url, filter)
        if 'error' in val:
            print(f"过滤实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('values')

    def query_entity(self, id):
        val = self.session.get('/core/entity/query/{0}'.format(id))
        if 'error' in val:
            print(f"查询实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def create_entity(self, param):
        val = self.session.post('/core/entity/create/', param)
        if 'error' in val:
            print(f"创建实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def update_entity(self, id, param):
        val = self.session.put('/core/entity/update/{0}'.format(id), param)
        if 'error' in val:
            print(f"更新实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def delete_entity(self, id):
        val = self.session.delete('/core/entity/destroy/{0}'.format(id))
        if 'error' in val:
            print(f"删除实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def enable_entity(self, id):
        val = self.session.put('/core/entity/enable/{0}'.format(id), None)
        if 'error' in val:
            print(f"启用实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def disable_entity(self, id):
        val = self.session.put('/core/entity/disable/{0}'.format(id), None)
        if 'error' in val:
            print(f"禁用实体失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')


def setup_data(session):
    app_instance = application.Application(session)
    app001 = application.mock_application_param()
    new_app10 = app_instance.create_application(app001)
    if not new_app10:
        print('create new application failed')
        return

    block_instance = block.Block(session)
    block001 = block.mock_block_param()
    new_block10 = block_instance.create_block(block001)
    if not new_block10:
        print('create new block failed')
        app_instance.delete_application(new_app10['id'])
        return

    return new_app10, new_block10


def teardown_data(session, av, bv):
    app_instance = application.Application(session)
    block_instance = block.Block(session)

    app_instance.delete_application(av['id'])
    block_instance.delete_block(bv['id'])


def mock_basic_type():
    idx = mock.int(0, len(basic_type_element) - 1)
    return basic_type_element[idx]


def mock_field(idx):
    return {
        'index': idx,
        'name': mock.name(),
        "spec": {
            "viewDeclare": [1, 2],
        },
        'type': mock_basic_type(),
    }


def mock_entity_param(blocks):
    val = {
        'name': mock.name(),
        'pkgPath': mock.name(),
        'isPtr': False,
        'block': blocks,
        'version': '0.0.1',
    }

    fields = [
        {
            "index": 0,
            "name": "id",
            "spec": {
                "primaryKey": True,
                "valueDeclare": 1,
                "viewDeclare": [1, 2],
            },
            "type": {
                "name": "int",
                "value": 104,
                "pkgPath": "",
                "isPtr": False,
            }
        },
    ]

    #field_size = mock.int(4, 300)
    field_size = mock.int(2, 6)
    idx = 1
    while idx < field_size:
        fields.append(mock_field(idx))
        idx = idx + 1

    val['fields'] = fields

    return val


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    app, block = setup_data(work_session)
    if not app or not block:
        print('setup_data failed')
        return

    work_session.bind_application(app['uuid'])

    entity_instance = Entity(work_session)

    entity001 = mock_entity_param([block])
    new_entity10 = entity_instance.create_entity(entity001)
    if not new_entity10:
        print('create new entity failed')
        return

    new_entity10['version'] = '0.0.2'
    new_entity11 = entity_instance.update_entity(new_entity10['id'], new_entity10)
    if new_entity11['version'] != new_entity10['version']:
        print('update entity failed')

    entity002 = mock_entity_param([block])
    new_entity20 = entity_instance.create_entity(entity002)
    if not new_entity20:
        teardown_data(work_session, app, block)
        print('create new entity failed')
        return

    entity_filter = {
        'params': {
            'items': {
                "name": '{0}|='.format(entity002['name'])
            }
        }
    }

    entity_list = entity_instance.filter_entity(entity_filter)
    if not entity_list:
        print('filter entity failed')
    elif len(entity_list) != 1:
        print('filter entity failed, illegal list size')

    entity_instance.enable_entity(new_entity10['id'])
    entity_instance.disable_entity(new_entity10['id'])

    entity_instance.delete_entity(new_entity10['id'])
    entity_instance.delete_entity(new_entity20['id'])

    teardown_data(work_session, app, block)

