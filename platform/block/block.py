from mock import common as mock
from session import session


class Block:
    """Block"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_block(self, filter):
        url = '/core/block/filter/'

        val = self.session.post(url, filter)
        if val and val['errorCode'] == 0:
            return val['values']

        print('--------filter_block-----------')
        print(val['reason'])
        return None

    def query_block(self, id):
        val = self.session.get('/core/block/query/{0}'.format(id))
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------query_block-----------')
        print(val['reason'])
        return None

    def create_block(self, param):
        val = self.session.post('/core/block/create/', param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------create_block-----------')
        print(val['reason'])
        return None

    def update_block(self, id, param):
        val = self.session.put('/core/block/update/{0}'.format(id), param)
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------update_block-----------')
        print(val['reason'])
        return None

    def delete_block(self, id):
        val = self.session.delete('/core/block/destroy/{0}'.format(id))
        if val and val['errorCode'] == 0:
            return val['value']

        print('--------delete_block-----------')
        print(val['reason'])
        return None


def mock_block_param():
    return {
        'name': mock.name(),
        'scope': mock.name(),
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    block_instance = Block(work_session)

    block001 = mock_block_param()
    new_block10 = block_instance.create_block(block001)
    if not new_block10:
        print('create new block failed')
        return

    new_block10['scope'] = mock.name()
    new_block11 = block_instance.update_block(new_block10['id'], new_block10)
    if new_block11['scope'] != new_block10['scope']:
        print('update block failed')

    block002 = mock_block_param()
    new_block20 = block_instance.create_block(block002)
    if not new_block20:
        print('create new block failed')
        return

    block_filter = {
        'params': {
            'items': {
                "name": '{0}|='.format(block002['name'])
            }
        }
    }

    block_list = block_instance.filter_block(block_filter)
    if not block_list:
        print('filter block failed')
    elif len(block_list) != 1:
        print(block_list)
        print('filter block failed, illegal list size')

    block_instance.delete_block(new_block10['id'])
    block_instance.delete_block(new_block20['id'])

