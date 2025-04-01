from mock import common as mock
from session import session

from application import application
from block import block
from entity import entity


def mock_basic_type_value(type):
    if type['value'] == 100:
        return False
    elif type['value'] == 101:
        return mock.int(0, 125)
    elif type['value'] == 102:
        return mock.int(-254, 255)
    elif type['value'] == 103:
        return mock.int(0, 1024)
    elif type['value'] == 104:
        return mock.int(0, 4096)
    elif type['value'] == 105:
        return mock.int(0, 10240)
    elif type['value'] == 106:
        return mock.int(0, 500)
    elif type['value'] == 107:
        return mock.int(0, 500)
    elif type['value'] == 108:
        return mock.int(0, 1024)
    elif type['value'] == 109:
        return mock.int(0, 4096)
    elif type['value'] == 110:
        return mock.int(0, 10240)
    elif type['value'] == 111:
        return mock.int(0, 123450)
    elif type['value'] == 112:
        return mock.int(0, 1234567890)
    elif type['value'] == 113:
        return mock.sentence()
    elif type['value'] == 114:
        return mock.time()


def get_tag_name(tag):
    return tag['value'].split()[0]


def mock_field_value(field):
    return {
        'name': field['name'],
        'value': mock_basic_type_value(field['type'])
    }


def mock_entity_value(entity):
    values = {
        'name': entity['name'],
        'pkgPath': entity['pkgPath'],
        'fields': [],
    }

    vals = []
    idx = 1
    while idx < len(entity['fields']):
        field_val = mock_field_value(entity['fields'][idx])
        vals.append(field_val)
        idx = idx + 1

    values['fields'] = vals

    return values


def update_value(entity, value):
    idx = 1
    while idx < len(entity['fields']):
        value['fields'][idx] = mock_field_value(entity['fields'][idx])
        idx = idx + 1
    return value


def mock_entity_query(entity, value):
    query = {
        'name': entity['name'],
        'pkgPath': entity['pkgPath'],
        'fields': [],
    }

    vals = []
    idx = 1
    while idx < len(value['fields']) - 1:
        vals.append(value['fields'][idx])
        idx = idx + 1
    query['fields'] = vals

    return query


def mock_entity_filter(entity, value):
    filter = {
        'pagination': {
            'pageSize': 10,
            'pageNum': 1,
        },
        'params': {
            'name': entity['name'],
            'pkgPath': entity['pkgPath'],
        },
    }

    return filter


class Value:
    """Value"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_value(self, filter):
        url = '/core/value/filter/'

        val = self.session.post(url, filter)
        if 'error' in val:
            print(f"过滤数值失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('values')

    def query_value(self, data):
        val = self.session.post('/core/value/query/', data)
        if 'error' in val:
            print(f"查询数值失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def insert_value(self, param):
        val = self.session.post('/core/value/insert/', param)
        if 'error' in val:
            print(f"插入数值失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def update_value(self, param):
        val = self.session.post('/core/value/update/', param)
        if 'error' in val:
            print(f"更新数值失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
            return None
        return val.get('value')

    def delete_value(self, param):
        val = self.session.post('/core/value/delete/', param)
        if 'error' in val:
            print(f"删除数值失败 Code: {val['error']['code']}, Message: {val['error']['message']}")
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

    session.bind_application(new_app10['uuid'])
    entity_instance = entity.Entity(session)
    entity001 = entity.mock_entity_param([new_block10])
    new_entity10 = entity_instance.create_entity(entity001)
    if not new_entity10:
        print('create new entity failed')
        block_instance.delete_block(new_block10['id'])
        app_instance.delete_application(new_app10['id'])
        return

    entity_instance.enable_entity(new_entity10['id'])

    return new_app10, new_block10, new_entity10


def teardown_data(session, av, bv, ev):
    app_instance = application.Application(session)
    block_instance = block.Block(session)

    session.bind_application(av['uuid'])
    entity_instance = entity.Entity(session)

    entity_instance.disable_entity(ev['id'])
    entity_instance.delete_entity(ev['id'])
    app_instance.delete_application(av['id'])
    block_instance.delete_block(bv['id'])


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    app, block, entity = setup_data(work_session)
    if not app or not block:
        print('setup_data failed')
        return

    work_session.bind_application(app['uuid'])

    value_instance = Value(work_session)

    value001 = mock_entity_value(entity)
    new_value10 = value_instance.insert_value(value001)
    if not new_value10:
        teardown_data(work_session, app, block, entity)
        print('create new value failed')
        return

    print(new_value10)
    new_value10 = update_value(entity, new_value10)
    value_instance.update_value(new_value10)
    print(new_value10)

    query_value = value_instance.query_value(mock_entity_query(entity, new_value10))
    print(query_value)

    value_instance.insert_value(new_value10)

    value_list = value_instance.filter_value(mock_entity_filter(entity, new_value10))
    if not value_list or len(value_list['values']) != 2:
        print('filter value failed')
    print(value_list)

    value_instance.delete_value(new_value10)

    teardown_data(work_session, app, block, entity)

