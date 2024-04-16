from mock import common as mock
from session import session, common
from cas.cas import cas

"""
{
    "sku": "abc2323",
    "description": "测试SKU001",
    "image": "fsdffsd"
}

{
    "id": 1,
    "name": "testPro",
    "description": "测试产品描述",
    "sku":[
        {
            "sku": "abc2323",
            "description": "测试SKU001",
            "image": "fsdffsd"
        },
    ],
    "image": ["afd"],
    "expire": 100,
    "status": 3,
    "tags": [],
}
"""


def mock_product_param():
    return {
        'name': mock.name(),
        'description': mock.sentence(),
        'sku': [{
            'sku': 'a001',
            'description': mock.sentence(),
            'image': [mock.url(), mock.url(), ],
        }],
        'image': [mock.url()],
        'expire': 100,
        'tags': ['a', 'b', 'c'],
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())

    product_instance = common.MagicEntity('/vmi/product', work_session)
    product_param = mock_product_param()
    new_product001 = product_instance.insert(product_param)
    if not new_product001:
        print('insert new product failed')
        return

    cur_product001 = product_instance.query(new_product001['id'])
    if not cur_product001:
        print('query new product failed')

    cur_product001['description'] = mock.sentence()
    cur_product001 = product_instance.update(new_product001['id'], new_product001)
    if not cur_product001:
        print('update new product failed')

    product_instance.delete(new_product001['id'])


