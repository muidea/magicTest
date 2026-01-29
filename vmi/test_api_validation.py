#!/usr/bin/env python3
"""
API验证测试脚本
用于验证各个API的字段要求
"""

import sys
import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from session import session
    from cas.cas import Cas
    from sdk import PartnerSDK, ProductSDK, GoodsSDK, StockinSDK, StockoutSDK
    
    # 初始化会话
    server_url = 'https://autotest.local.vpc'
    work_session = session.MagicSession(server_url, '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        logger.error("CAS登录失败")
        sys.exit(1)
    
    work_session.bind_token(cas_session.get_session_token())
    logger.info("登录成功")
    
    # 测试Partner创建
    logger.info("测试Partner创建...")
    partner_sdk = PartnerSDK(work_session)
    partner_data = {
        'name': '测试合作伙伴_验证',
        'telephone': '13812345678',
        'wechat': 'test_wechat',
        'description': '测试描述',
        'status': {'id': 3}
    }
    partner_result = partner_sdk.create_partner(partner_data)
    logger.info(f"Partner创建结果: {partner_result}")
    
    # 测试Product创建
    logger.info("测试Product创建...")
    product_sdk = ProductSDK(work_session)
    product_data = {
        'name': '测试产品_验证',
        'code': 'PROD_TEST',
        'price': 100.0,
        'description': '测试产品描述',
        'status': {'id': 1}
    }
    product_result = product_sdk.create_product(product_data)
    logger.info(f"Product创建结果: {product_result}")
    
    # 测试Goods创建（需要product_id、shelf数组和store）
    logger.info("测试Goods创建...")
    goods_sdk = GoodsSDK(work_session)
    if product_result and 'id' in product_result:
        goods_data = {
            'name': '测试商品_验证',
            'code': 'GOODS_TEST',
            'sku': 'SKU_TEST_001',
            'price': 50.0,
            'count': 100,
            'description': '测试商品描述',
            'status': {'id': 1},
            'product': {'id': product_result['id']},
            'shelf': [{'id': 1}],  # shelf应该是数组
            'store': {'id': 1}     # 需要store字段
        }
        goods_result = goods_sdk.create_goods(goods_data)
        logger.info(f"Goods创建结果: {goods_result}")
        
        # 测试Stockin创建（需要goods_id）
        if goods_result and 'id' in goods_result:
            logger.info("测试Stockin创建...")
            stockin_sdk = StockinSDK(work_session)
            stockin_data = {
                'warehouse': {'id': 1},
                'goodsInfo': [{'id': goods_result['id']}],  # goodsInfo应该是数组
                'quantity': 10,
                'type': 'in',
                'remark': '测试入库',
                'operator': 'test_operator',
                'status': {'id': 1},  # 需要status字段
                'store': {'id': 1}    # 需要store字段
            }
            stockin_result = stockin_sdk.create_stockin(stockin_data)
            logger.info(f"Stockin创建结果: {stockin_result}")
            
            # 测试Stockout创建
            logger.info("测试Stockout创建...")
            stockout_sdk = StockoutSDK(work_session)
            stockout_data = {
                'warehouse': {'id': 1},
                'goodsInfo': [{'id': goods_result['id']}],  # goodsInfo应该是数组
                'quantity': 5,
                'type': 'out',
                'remark': '测试出库',
                'operator': 'test_operator',
                'status': {'id': 1},  # 需要status字段
                'store': {'id': 1}    # 需要store字段
            }
            stockout_result = stockout_sdk.create_stockout(stockout_data)
            logger.info(f"Stockout创建结果: {stockout_result}")
    
    logger.info("API验证测试完成")
    
except Exception as e:
    logger.error(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)