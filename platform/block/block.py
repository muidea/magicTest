from mock import common as mock
from session import session


class Block:
    """Block"""

    def __init__(self, work_session):
        self.session = work_session

    def filter_block(self, filter):
        url = '/core/blocks'

        val = self.session.post(url, filter)
        if 'error' in val:
            print("过滤区块失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('values')

    def query_block(self, id):
        val = self.session.get('/core/blocks/{0}'.format(id))
        if 'error' in val:
            print("查询区块失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def create_block(self, param):
        val = self.session.post('/core/blocks', param)
        if 'error' in val:
            print("创建区块失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def update_block(self, id, param):
        val = self.session.put('/core/blocks/{0}'.format(id), param)
        if 'error' in val:
            print("更新区块失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')

    def delete_block(self, id):
        val = self.session.delete('/core/block/destroy/{0}'.format(id))
        if 'error' in val:
            print("删除区块失败 Code: %s, Message: %s" % (val['error']['code'], val['error']['message']))
            return None
        return val.get('value')


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
        return False

    new_block10['scope'] = mock.name()
    new_block11 = block_instance.update_block(new_block10['id'], new_block10)
    if not new_block11 or new_block11['scope'] != new_block10['scope']:
        print('update block failed')
        return False

    block002 = mock_block_param()
    new_block20 = block_instance.create_block(block002)
    if not new_block20:
        print('create new block failed')
        return False

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
        return False
    elif len(block_list) != 1:
        print(block_list)
        print('filter block failed, illegal list size')
        return False

    deleted_block1 = block_instance.delete_block(new_block10['id'])
    if not deleted_block1:
        print('delete block failed')
        return False

    deleted_block2 = block_instance.delete_block(new_block20['id'])
    if not deleted_block2:
        print('delete block failed')
        return False

    return True

