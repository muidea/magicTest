import logging
import time
import unittest

from cas.cas import cas
from session import session, common


def mock_warehouse(idx):
    return {
        'name': 'CK_{0}'.format(idx),
        'description': '测试仓库{0}的描述信息'.format(idx),
    }


def mock_shelf(idx, warehouse):
    return {
        'description': '测试货架{0}的描述信息'.format(idx),
        'capacity': 5000,
        'warehouse': warehouse,
    }


def mock_store(idx, shelf):
    return {
        'name': 'STORE_{0}'.format(idx),
        'description': '测试店铺{0}的描述信息'.format(idx),
        'shelf': shelf
    }


def mock_product(idx):
    return {
        'name': 'PRODUCT_{0}'.format(idx),
        'description': '测试产品{0}描述信息'.format(idx),
        'skuInfo': [{
            'sku': 'sku00{0}0'.format(idx),
            'description': '测试SKU:sku00{0}0描述信息'.format(idx),
            'image': [
                'https://xijian.mulife.vip/api/v1/static/file/?fileSource=magicvmi_xijian&fileToken=rw17dxt6exricyfhjtwtfnwnillpljhg', ],
        }, {
            'sku': 'sku00{0}1'.format(idx),
            'description': '测试SKU:sku00{0}1描述信息'.format(idx),
            'image': [
                'https://xijian.mulife.vip/api/v1/static/file/?fileSource=magicvmi_xijian&fileToken=rw17dxt6exricyfhjtwtfnwnillpljhg', ],
        }, {
            'sku': 'sku00{0}2'.format(idx),
            'description': '测试SKU:sku00{0}2描述信息'.format(idx),
            'image': [
                'https://xijian.mulife.vip/api/v1/static/file/?fileSource=magicvmi_xijian&fileToken=rw17dxt6exricyfhjtwtfnwnillpljhg', ],
        }],
        'image': [
            'https://xijian.mulife.vip/api/v1/static/file/?fileSource=magicvmi_xijian&fileToken=rw17dxt6exricyfhjtwtfnwnillpljhg'],
        'expire': 100,
        'tags': ['a', 'b', 'c'],
    }


def create_warehouse(work_session, idx):
    warehouse_instance = common.MagicEntity("/api/v1/vmi/warehouse", work_session)
    warehouse_val = warehouse_instance.insert(mock_warehouse(idx))
    if not warehouse_val:
        logging.warning("create new warehouse {0} failed".format(idx))
        return None
    return warehouse_val


def destroy_warehouse(work_session, warehouse_val):
    warehouse_instance = common.MagicEntity("/api/v1/vmi/warehouse", work_session)
    warehouse_val = warehouse_instance.delete(warehouse_val['id'])
    if not warehouse_val:
        logging.warning("delete warehouse {0} failed".format(warehouse_val['name']))
        return None
    return warehouse_val


def count_warehouse(work_session):
    warehouse_instance = common.MagicEntity("/api/v1/vmi/warehouse", work_session)
    warehouse_val = warehouse_instance.count()
    if not warehouse_val:
        logging.warning("count warehouse failed")
        return None
    return warehouse_val


def create_shelf(work_session, idx, warehouse_val):
    shelf_instance = common.MagicEntity("/api/v1/vmi/warehouse/shelf", work_session)
    shelf_val = shelf_instance.insert(mock_shelf(idx, warehouse_val))
    if not shelf_val:
        logging.warning("create new shelf {0} failed".format(idx))
        return None
    return shelf_val


def destroy_shelf(work_session, shelf_val):
    shelf_instance = common.MagicEntity("/api/v1/vmi/warehouse/shelf", work_session)
    shelf_val = shelf_instance.delete(shelf_val)
    if not shelf_val:
        logging.warning("create new shelf {0} failed".format(shelf_val['code']))
        return None
    return shelf_val


def count_shelf(work_session):
    shelf_instance = common.MagicEntity("/api/v1/vmi/warehouse/shelf", work_session)
    shelf_val = shelf_instance.count()
    if not shelf_val:
        logging.warning("count shelf failed")
        return None
    return shelf_val


def create_store(work_session, idx, shelf_val):
    store_instance = common.MagicEntity("/api/v1/vmi/store", work_session)
    store_val = store_instance.insert(mock_store(idx, shelf_val))
    if not store_val:
        logging.warning("create new store {0} failed".format(idx))
        return None
    return store_val


def destroy_store(work_session, store_val):
    store_instance = common.MagicEntity("/api/v1/vmi/store", work_session)
    store_val = store_instance.delete(store_val['id'])
    if not store_val:
        logging.warning("delete store {0} failed".format(store_val['name']))
        return None
    return store_val


def count_store(work_session):
    store_instance = common.MagicEntity("/api/v1/vmi/store", work_session)
    store_val = store_instance.count()
    if not store_val:
        logging.warning("count store failed")
        return None
    return store_val


def create_product(work_session, idx):
    product_instance = common.MagicEntity("/api/v1/vmi/product", work_session)
    product_val = product_instance.insert(mock_product(idx))
    if not product_val:
        logging.warning("create new product {0} failed".format(idx))
        return None
    return product_val


def destroy_product(work_session, product_val):
    product_instance = common.MagicEntity("/api/v1/vmi/product", work_session)
    product_val = product_instance.delete(product_val['id'])
    if not product_val:
        logging.warning("delete product {0} failed".format(product_val['name']))
        return None
    return product_val


def count_product(work_session):
    product_instance = common.MagicEntity("/api/v1/vmi/product", work_session)
    product_val = product_instance.count()
    if not product_val:
        logging.warning("count product failed")
        return None
    return product_val


def filter_product_sku(work_session, page_idx, page_size):
    product_sku_instance = common.MagicEntity("/api/v1/vmi/product/skuInfo", work_session)
    sku_list = product_sku_instance.filter({
        'pageIndex': page_idx,
        'pageSize': page_size
    })
    if not sku_list:
        logging.warning("filter product skuInfo failed")
        return None
    return sku_list


def destroy_product_sku(work_session, product_sku_val):
    product_sku_instance = common.MagicEntity("/api/v1/vmi/product/skuInfo", work_session)
    sku_val = product_sku_instance.delete(product_sku_val['sku'])
    if not sku_val:
        logging.warning("delete product skuInfo {0} failed".format(sku_val['sku']))
        return None
    return sku_val


def count_product_sku(work_session):
    product_sku_instance = common.MagicEntity("/api/v1/vmi/product/skuInfo", work_session)
    sku_val = product_sku_instance.count()
    if not sku_val:
        logging.warning("count product skuInfo failed")
        return None
    return sku_val


def refresh_session(cas_session, work_session):
    new_token = cas_session.refresh(cas_session.get_session_token())
    work_session.bind_token(new_token)


class BaseTestCase(unittest.TestCase):
    _server_url = 'https://autotest.local.vpc'
    _user = 'administrator'
    _password = 'administrator'
    _warehouse_count = 1
    _shelf_count = 1
    _store_count = 1
    _product_count = 1
    _warehouse_list = []
    _shelf_list = []
    _store_list = []
    _product_list = []
    _interval_val = 0.2

    def setUp(self):
        work_session = session.MagicSession('{0}'.format(self._server_url), '')
        cas_session = cas.Cas(work_session)
        if not cas_session.login(self._user, self._password):
            print('cas failed')
            return False
        work_session.bind_token(cas_session.get_session_token())
        self._work_session = work_session

        ii = 0
        while ii < self._warehouse_count:
            warehouse_val = create_warehouse(self._work_session, ii)
            if warehouse_val:
                self._warehouse_list.append(warehouse_val)
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._warehouse_list) != self._warehouse_count:
            logging.error("initialize warehouse failed")
            return

        ii = 0
        while ii < self._shelf_count:
            shelf_val = create_shelf(self._work_session, ii, self._warehouse_list[0])
            if shelf_val:
                self._shelf_list.append(shelf_val)
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._shelf_list) != self._shelf_count:
            logging.error("initialize shelf failed")
            return

        ii = 0
        while ii < self._store_count:
            store_val = create_store(self._work_session, ii, self._shelf_list[ii * 2:ii * 2 + 2])
            if store_val:
                self._store_list.append(store_val)
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._store_list) != self._store_count:
            logging.error("initialize store failed")
            return

        ii = 0
        while ii < self._product_count:
            product_val = create_product(self._work_session, ii)
            if product_val:
                self._product_list.append(product_val)
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._product_list) != self._product_count:
            logging.error("initialize product failed")
            return

    def tearDown(self):
        return
        ii = 0
        while ii < self._warehouse_count:
            destroy_warehouse(self._work_session, self._warehouse_list[ii])
            time.sleep(self._interval_val)
            ii += 1

        ii = 0
        while ii < self._shelf_count:
            destroy_shelf(self._work_session, self._shelf_list[ii])
            time.sleep(self._interval_val)
            ii += 1

        ii = 0
        while ii < self._product_count:
            destroy_product(self._work_session, self._product_list[ii])
            time.sleep(self._interval_val)
            ii += 1

        while True:
            sku_list = filter_product_sku(self._work_session, 0, 200)
            if not sku_list:
                break
            ii = 0
            while ii < 200:
                destroy_product_sku(self._work_session, sku_list[ii])
                time.sleep(self._interval_val)
                ii += 1

    def test_something(self):
        warehouse_count = count_warehouse(self._work_session)
        self.assertEqual(warehouse_count, self._warehouse_count)  # add assertion here
        shelf_count = count_shelf(self._work_session)
        self.assertEqual(shelf_count, self._shelf_count)  # add assertion here
        store_count = count_store(self._work_session)
        self.assertEqual(store_count, self._store_count)  # add assertion here
        product_count = count_product(self._work_session)
        self.assertEqual(product_count, self._product_count)  # add assertion here
        sku_count = count_product_sku(self._work_session)
        self.assertEqual(sku_count, self._product_count * 3)  # add assertion here
