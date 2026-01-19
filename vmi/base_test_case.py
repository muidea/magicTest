import logging
import time
import unittest

from cas.cas import cas
from session import session, common
from .sdk import WarehouseSDK, ShelfSDK, StoreSDK, ProductSDK


def mock_warehouse(idx):
    return {
        'name': 'CK_{0}'.format(idx),
        'description': '测试仓库{0}的描述信息'.format(idx),
    }


def mock_shelf(idx, warehouse):
    return {
        'description': '测试货架{0}的描述信息'.format(idx),
        'capacity': 5000,
        'used': 0,
        'warehouse': warehouse,
    }


def mock_store(idx, shelf_val):
    """创建店铺mock数据，shelf_val可以是货架对象、货架ID或货架对象列表"""
    # 根据readme.txt，每个店铺有2个货架，所以shelf字段应该是一个数组
    if isinstance(shelf_val, list):
        # 如果已经是列表，直接使用
        shelf_list = shelf_val
    else:
        # 否则创建包含单个货架的列表
        shelf_list = [shelf_val]
    
    # 将列表中的货架ID转换为包含id的对象
    processed_shelves = []
    for shelf in shelf_list:
        if isinstance(shelf, dict) and 'id' in shelf:
            processed_shelves.append(shelf)
        elif isinstance(shelf, (int, str)):
            processed_shelves.append({'id': shelf})
        else:
            processed_shelves.append(shelf)
    
    return {
        'name': 'STORE_{0}'.format(idx),
        'description': '测试店铺{0}的描述信息'.format(idx),
        'shelf': processed_shelves,  # 货架字段应该是一个货架对象数组
        'goods': []
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
        'status': {'id': 17},
        'tags': ['a', 'b', 'c'],
    }


def create_warehouse(work_session, idx):
    """使用 WarehouseSDK 创建仓库"""
    warehouse_sdk = WarehouseSDK(work_session)
    warehouse_val = warehouse_sdk.create_warehouse(mock_warehouse(idx))
    if not warehouse_val:
        logging.warning("create new warehouse {0} failed".format(idx))
        return None
    return warehouse_val


def destroy_warehouse(work_session, warehouse_val):
    """使用 WarehouseSDK 删除仓库"""
    warehouse_sdk = WarehouseSDK(work_session)
    result = warehouse_sdk.delete_warehouse(warehouse_val['id'])
    if not result:
        logging.warning("delete warehouse {0} failed".format(warehouse_val['name']))
        return None
    return result


def count_warehouse(work_session):
    """使用 WarehouseSDK 统计仓库数量"""
    warehouse_sdk = WarehouseSDK(work_session)
    count = warehouse_sdk.count_warehouse({})
    if count is None:
        logging.warning("count warehouse failed")
        return None
    return count


def create_shelf(work_session, idx, warehouse_val):
    """使用 ShelfSDK 创建货架"""
    shelf_sdk = ShelfSDK(work_session)
    shelf_val = shelf_sdk.create_shelf(mock_shelf(idx, warehouse_val))
    if not shelf_val:
        logging.warning("create new shelf {0} failed".format(idx))
        return None
    return shelf_val


def destroy_shelf(work_session, shelf_val):
    """使用 ShelfSDK 删除货架"""
    shelf_sdk = ShelfSDK(work_session)
    result = shelf_sdk.delete_shelf(shelf_val['id'])
    if not result:
        logging.warning("delete shelf {0} failed".format(shelf_val.get('code', 'unknown')))
        return None
    return result


def count_shelf(work_session):
    """使用 ShelfSDK 统计货架数量"""
    shelf_sdk = ShelfSDK(work_session)
    count = shelf_sdk.count_shelf()
    if count is None:
        logging.warning("count shelf failed")
        return None
    return count


def create_store(work_session, idx, shelf_val):
    """使用 StoreSDK 创建店铺"""
    store_sdk = StoreSDK(work_session)
    # 直接传递货架对象或货架对象列表
    store_val = store_sdk.create_store(mock_store(idx, shelf_val))
    if not store_val:
        logging.warning("create new store {0} failed".format(idx))
        return None
    return store_val


def destroy_store(work_session, store_val):
    """使用 StoreSDK 删除店铺"""
    store_sdk = StoreSDK(work_session)
    result = store_sdk.delete_store(store_val['id'])
    if not result:
        logging.warning("delete store {0} failed".format(store_val['name']))
        return None
    return result


def count_store(work_session):
    """使用 StoreSDK 统计店铺数量"""
    store_sdk = StoreSDK(work_session)
    count = store_sdk.count_store()
    if count is None:
        logging.warning("count store failed")
        return None
    return count


def create_product(work_session, idx):
    """使用 ProductSDK 创建产品"""
    product_sdk = ProductSDK(work_session)
    product_val = product_sdk.create_product(mock_product(idx))
    if not product_val:
        logging.warning("create new product {0} failed".format(idx))
        return None
    return product_val


def destroy_product(work_session, product_val):
    """使用 ProductSDK 删除产品"""
    product_sdk = ProductSDK(work_session)
    result = product_sdk.delete_product(product_val['id'])
    if not result:
        logging.warning("delete product {0} failed".format(product_val['name']))
        return None
    return result


def count_product(work_session):
    """使用 ProductSDK 统计产品数量"""
    product_sdk = ProductSDK(work_session)
    count = product_sdk.count_product()
    if count is None:
        logging.warning("count product failed")
        return None
    return count


def filter_product_sku(work_session, page_idx, page_size):
    """过滤产品 SKU（暂未提供 SDK，保留原有实现）"""
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
    """删除产品 SKU（暂未提供 SDK，保留原有实现）"""
    product_sku_instance = common.MagicEntity("/api/v1/vmi/product/skuInfo", work_session)
    sku_val = product_sku_instance.delete(product_sku_val['sku'])
    if not sku_val:
        logging.warning("delete product skuInfo {0} failed".format(sku_val['sku']))
        return None
    return sku_val


def count_product_sku(work_session):
    """统计产品 SKU 数量（暂未提供 SDK，保留原有实现）"""
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
    _shelf_count = 20
    _store_count = 10
    _product_count = 50
    _warehouse_list = []
    _shelf_list = []
    _store_list = []
    _product_list = []
    _interval_val = 0.2

    def setUp(self):
        # 清空所有列表，确保每个测试开始时都是干净的状态
        self._warehouse_list.clear()
        self._shelf_list.clear()
        self._store_list.clear()
        self._product_list.clear()
        
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
            else:
                self.fail(f"创建仓库 {ii} 失败")
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._warehouse_list) != self._warehouse_count:
            self.fail(f"仓库初始化失败: 期望{self._warehouse_count}个，实际创建{len(self._warehouse_list)}个")

        ii = 0
        while ii < self._shelf_count:
            shelf_val = create_shelf(self._work_session, ii, self._warehouse_list[0])
            if shelf_val:
                self._shelf_list.append(shelf_val)
            else:
                self.fail(f"创建货架 {ii} 失败")
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._shelf_list) != self._shelf_count:
            self.fail(f"货架初始化失败: 期望{self._shelf_count}个，实际创建{len(self._shelf_list)}个")

        ii = 0
        while ii < self._store_count:
            # 每个店铺需要2个货架
            shelf_idx = ii * 2
            if shelf_idx + 1 < len(self._shelf_list):
                # 获取2个货架
                shelf1 = self._shelf_list[shelf_idx]
                shelf2 = self._shelf_list[shelf_idx + 1]
                # 传递2个货架给店铺
                store_val = create_store(self._work_session, ii, [shelf1, shelf2])
                if store_val:
                    self._store_list.append(store_val)
                else:
                    self.fail(f"创建店铺 {ii} 失败")
            else:
                self.fail(f"没有足够的货架分配给店铺 {ii}")
            time.sleep(self._interval_val)

            refresh_session(cas_session, work_session)
            ii += 1
        if len(self._store_list) != self._store_count:
            self.fail(f"店铺初始化失败: 期望{self._store_count}个，实际创建{len(self._store_list)}个")

        ii = 0
        # 对于大量产品创建，减少间隔时间以提高速度
        product_interval = 0.01  # 0.01秒间隔
        # 每1000个产品打印一次进度
        progress_interval = 1000
        while ii < self._product_count:
            product_val = create_product(self._work_session, ii)
            if product_val:
                self._product_list.append(product_val)
            else:
                self.fail(f"创建产品 {ii} 失败")
            time.sleep(product_interval)

            refresh_session(cas_session, work_session)
            ii += 1
            
            # 打印进度
            if ii % progress_interval == 0:
                logging.info(f"已创建 {ii}/{self._test_product_count} 个产品")
                
        if len(self._product_list) != self._product_count:
            self.fail(f"产品初始化失败: 期望{self._product_count}个，实际创建{len(self._product_list)}个")
        else:
            logging.info(f"成功创建 {len(self._product_list)} 个产品（测试模式下限制为{self._product_count}个）")

    def tearDown(self):
        """清理测试数据"""
        logging.info("开始清理测试数据...")
        
        # 清理店铺
        if hasattr(self, '_store_list') and self._store_list:
            logging.info(f"清理 {len(self._store_list)} 个店铺...")
            ii = 0
            while ii < len(self._store_list):
                try:
                    destroy_store(self._work_session, self._store_list[ii])
                except Exception as e:
                    logging.warning(f"清理店铺 {ii} 时出错: {e}")
                time.sleep(self._interval_val)
                ii += 1
        
        # 清理货架
        if hasattr(self, '_shelf_list') and self._shelf_list:
            logging.info(f"清理 {len(self._shelf_list)} 个货架...")
            ii = 0
            while ii < len(self._shelf_list):
                try:
                    destroy_shelf(self._work_session, self._shelf_list[ii])
                except Exception as e:
                    logging.warning(f"清理货架 {ii} 时出错: {e}")
                time.sleep(self._interval_val)
                ii += 1
        
        # 清理产品
        if hasattr(self, '_product_list') and self._product_list:
            # 由于产品数量可能很大，只清理前1000个作为示例
            cleanup_count = min(1000, len(self._product_list))
            logging.info(f"清理 {cleanup_count} 个产品（总共{len(self._product_list)}个）...")
            ii = 0
            while ii < cleanup_count:
                try:
                    destroy_product(self._work_session, self._product_list[ii])
                except Exception as e:
                    logging.warning(f"清理产品 {ii} 时出错: {e}")
                time.sleep(self._interval_val)
                ii += 1
        
        # 清理仓库
        if hasattr(self, '_warehouse_list') and self._warehouse_list:
            logging.info(f"清理 {len(self._warehouse_list)} 个仓库...")
            ii = 0
            while ii < len(self._warehouse_list):
                try:
                    destroy_warehouse(self._work_session, self._warehouse_list[ii])
                except Exception as e:
                    logging.warning(f"清理仓库 {ii} 时出错: {e}")
                time.sleep(self._interval_val)
                ii += 1
        
        # 清理SKU（如果需要）
        try:
            sku_count = 0
            while True:
                sku_list = filter_product_sku(self._work_session, 0, 200)
                if not sku_list or sku_count > 1000:  # 限制最多清理1000个SKU
                    break
                for sku in sku_list[:10]:  # 每次只清理10个
                    try:
                        destroy_product_sku(self._work_session, sku)
                        sku_count += 1
                    except Exception as e:
                        logging.warning(f"清理SKU时出错: {e}")
                    time.sleep(self._interval_val)
                if sku_count % 100 == 0:
                    logging.info(f"已清理 {sku_count} 个SKU...")
        except Exception as e:
            logging.warning(f"清理SKU时发生异常: {e}")
        
        logging.info("测试数据清理完成")

    def test_something(self):
        """基础数据校验测试"""
        warehouse_count = count_warehouse(self._work_session)
        self.assertEqual(warehouse_count, self._warehouse_count, f"仓库数量不正确: 期望{self._warehouse_count}, 实际{warehouse_count}")
        shelf_count = count_shelf(self._work_session)
        self.assertEqual(shelf_count, self._shelf_count, f"货架数量不正确: 期望{self._shelf_count}, 实际{shelf_count}")
        store_count = count_store(self._work_session)
        self.assertEqual(store_count, self._store_count, f"店铺数量不正确: 期望{self._store_count}, 实际{store_count}")
        product_count = count_product(self._work_session)
        self.assertEqual(product_count, self._product_count, f"产品数量不正确: 期望{self._product_count}, 实际{product_count}")
        sku_count = count_product_sku(self._work_session)
        expected_sku_count = self._product_count * 3
        self.assertEqual(sku_count, expected_sku_count, f"SKU数量不正确: 期望{expected_sku_count}, 实际{sku_count}")
        
        # 打印校验结果
        print(f"✓ 仓库数量: {warehouse_count}")
        print(f"✓ 货架数量: {shelf_count}")
        print(f"✓ 店铺数量: {store_count}")
        print(f"✓ 产品数量: {product_count}")
        print(f"✓ SKU数量: {sku_count}")
        
    def test_data_validation(self):
        """详细数据校验测试"""
        # 校验仓库数据
        self.assertEqual(len(self._warehouse_list), self._warehouse_count, "仓库列表长度不匹配")
        if self._warehouse_list:
            warehouse = self._warehouse_list[0]
            self.assertIn('id', warehouse, "仓库缺少id字段")
            self.assertIn('name', warehouse, "仓库缺少name字段")
            print(f"仓库信息: ID={warehouse.get('id')}, 名称={warehouse.get('name')}")
        
        # 校验货架数据
        self.assertEqual(len(self._shelf_list), self._shelf_count, "货架列表长度不匹配")
        for i, shelf in enumerate(self._shelf_list[:3]):  # 只检查前3个货架
            self.assertIn('id', shelf, f"货架{i}缺少id字段")
            self.assertEqual(shelf.get('capacity'), 5000, f"货架{i}容量不是5000")
            print(f"货架{i}: ID={shelf.get('id')}, 容量={shelf.get('capacity')}")
        
        # 校验店铺数据
        self.assertEqual(len(self._store_list), self._store_count, "店铺列表长度不匹配")
        for i, store in enumerate(self._store_list[:3]):  # 只检查前3个店铺
            self.assertIn('id', store, f"店铺{i}缺少id字段")
            self.assertIn('name', store, f"店铺{i}缺少name字段")
            print(f"店铺{i}: ID={store.get('id')}, 名称={store.get('name')}")
        
        # 校验产品数据
        self.assertEqual(len(self._product_list), self._product_count, f"产品列表长度不匹配: 期望{self._product_count}个（测试模式），实际{len(self._product_list)}个")
        for i, product in enumerate(self._product_list[:3]):  # 只检查前3个产品
            self.assertIn('id', product, f"产品{i}缺少id字段")
            self.assertIn('name', product, f"产品{i}缺少name字段")
            self.assertIn('skuInfo', product, f"产品{i}缺少skuInfo字段")
            sku_count = len(product.get('skuInfo', []))
            self.assertEqual(sku_count, 3, f"产品{i}的SKU数量不是3")
            print(f"产品{i}: ID={product.get('id')}, 名称={product.get('name')}, SKU数量={sku_count}")

    def test_warehouse_crud(self):
        """测试仓库的 CRUD 操作"""
        sdk = WarehouseSDK(self._work_session)
        # 创建
        mock_data = mock_warehouse(100)
        created = sdk.create_warehouse(mock_data)
        self.assertIsNotNone(created, "创建仓库失败")
        self.assertIn('id', created)
        warehouse_id = created['id']
        # 查询
        queried = sdk.query_warehouse(warehouse_id)
        self.assertIsNotNone(queried, "查询仓库失败")
        self.assertEqual(queried['name'], mock_data['name'])
        self.assertEqual(queried['description'], mock_data['description'])
        # 更新
        update_data = {'description': '更新后的描述'}
        updated = sdk.update_warehouse(warehouse_id, update_data)
        self.assertIsNotNone(updated, "更新仓库失败")
        self.assertEqual(updated['description'], update_data['description'])
        # 再次查询验证更新
        queried2 = sdk.query_warehouse(warehouse_id)
        self.assertEqual(queried2['description'], update_data['description'])
        # 删除
        deleted = sdk.delete_warehouse(warehouse_id)
        self.assertIsNotNone(deleted, "删除仓库失败")
        # 验证删除后查询不到
        queried3 = sdk.query_warehouse(warehouse_id)
        self.assertIsNone(queried3, "仓库删除后仍能查询到")
