from mock import common as mock
from session import session, common
from cas.cas import cas


def mock_goods(product):
    return {
        'sku': 'a003',
        'product': product,
        'type': 1,
        'count': 100,
        'price': 120,
        'shelf': [],
        'description': '',
        'parameter': '',
        'serviceInfo': ''
    }


def mock_stockin_param(store, product):
    return {
        'goodsInfo': [mock_goods(product), ],
        'description': mock.sentence(),
        'store': store,
        'status': {
            'id': 16
        }
    }


def mock_warehouse_param():
    return {
        'name': 'CK'+mock.name(),
        'description': mock.sentence(),
    }


def mock_shelf_param(warehouse):
    return {
        'name': 'HJ'+mock.name(),
        'description': mock.sentence(),
        'capacity': mock.int(),
        'warehouse': warehouse,
    }


def mock_product_sku_info_param():
    return {
        "sku": "a003",
        'description': mock.sentence(),
        'image': [mock.url()],
    }


def mock_product_param():
    return {
        'name': mock.name(),
        'description': mock.sentence(),
        'skuInfo': [mock_product_sku_info_param()],
        'image': [mock.url()],
        'expire': 100,
        'tags': ['a', 'b', 'c'],
    }


def mock_store_param():
    return {
        'name': 'STORE'+mock.name(),
        'description': mock.sentence(),
    }


def setup_data(session):
    warehouse_instance = common.MagicEntity("/vmi/warehouse", session)
    warehouse_param = mock_warehouse_param()
    new_warehouse = warehouse_instance.insert(warehouse_param)
    if not new_warehouse:
        print('create new warehouse failed')
        return

    shelf_instance = common.MagicEntity("/vmi/warehouse/shelf", session)
    shelf_param = mock_shelf_param(new_warehouse)
    new_shelf = shelf_instance.insert(shelf_param)
    if not new_shelf:
        print('create new shelf failed')
        return

    product_sku_info_instance = common.MagicEntity("/vmi/product/skuInfo", session)
    product_sku_info_param = mock_product_sku_info_param()
    new_product_sku = product_sku_info_instance.insert(product_sku_info_param)
    if not new_product_sku:
        print('create new product sku failed')
        return
    product_instance = common.MagicEntity("/vmi/product", session)
    product_param = mock_product_param()
    new_product = product_instance.insert(product_param)
    if not new_product:
        print('create new product failed')
        return

    store_instance = common.MagicEntity("/vmi/store", session)
    store_param = mock_store_param()
    new_store = store_instance.insert(store_param)
    if not new_store:
        print('create new store failed')
        return

    return new_warehouse, new_shelf, new_product, new_store


def teardown_data(session, warehouse, shelf, product, store):
    store_instance = common.MagicEntity("/vmi/store", session)
    store_instance.delete(store['id'])
    product_instance = common.MagicEntity("/vmi/product", session)
    product_instance.delete(product['id'])
    shelf_instance = common.MagicEntity("/vmi/warehouse/shelf", session)
    shelf_instance.delete(shelf['id'])
    warehouse_instance = common.MagicEntity("/vmi/warehouse", session)
    warehouse_instance.delete(warehouse['id'])


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        print('cas failed')
        return False

    work_session.bind_token(cas_session.get_session_token())

    warehouse, shelf, product, store = setup_data(work_session)

    stockin_instance = common.MagicEntity("/vmi/store/stockin", work_session)
    stockin_param = mock_stockin_param(store, product)
    print(stockin_param)
    new_stockin001 = stockin_instance.insert(stockin_param)
    if not new_stockin001:
        print('create new stockin failed')
        return
    print(new_stockin001)

    cur_stockin001 = stockin_instance.query(new_stockin001['id'])
    if not cur_stockin001:
        print('query new stockin failed')

    print(cur_stockin001)
    cur_stockin001['description'] = mock.sentence()
    cur_stockin001 = stockin_instance.update(new_stockin001['id'], new_stockin001)
    if not cur_stockin001:
        print('update new stockin failed')

    stockin_instance.delete(new_stockin001['id'])
