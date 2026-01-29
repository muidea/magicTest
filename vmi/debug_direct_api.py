#!/usr/bin/env python3
"""
直接API调用测试productInfo
"""

import sys
import os
import json
import logging

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas

def test_direct_api():
    """直接API调用测试"""
    print("直接API调用测试productInfo...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 先创建product
    print("创建product...")
    product_param = {
        'name': 'API测试产品',
        'description': '直接API测试用',
        'status': {'id': 19}
    }
    
    # 使用session直接调用API
    try:
        # 创建product
        product_response = work_session.post('/api/v1/vmi/products/', product_param)
        if not product_response or 'id' not in product_response:
            print("创建product失败")
            return False
        
        product_id = product_response['id']
        print(f"创建product成功: ID={product_id}")
        
        # 测试不同路径的productInfo API
        test_paths = [
            '/api/v1/vmi/product/productInfo/',
            '/api/v1/vmi/product/productInfos/',
            '/api/v1/vmi/productInfo/',
            '/api/v1/vmi/productInfos/',
        ]
        
        for path in test_paths:
            print(f"\n测试路径: {path}")
            
            # 测试1: 使用字符串sku
            product_info_param1 = {
                'sku': 'API1001',
                'description': '直接API测试',
                'product': {'id': product_id}
            }
            
            print(f"请求参数1: {product_info_param1}")
            response1 = work_session.post(path, product_info_param1)
            print(f"响应1: {response1}")
            
            # 测试2: 使用整数sku
            product_info_param2 = {
                'sku': 1002,
                'description': '直接API测试整数',
                'product': {'id': product_id}
            }
            
            print(f"请求参数2: {product_info_param2}")
            response2 = work_session.post(path, product_info_param2)
            print(f"响应2: {response2}")
            
            # 测试3: 使用浮点数格式的sku
            product_info_param3 = {
                'sku': '1003.000000',
                'description': '直接API测试浮点格式',
                'product': {'id': product_id}
            }
            
            print(f"请求参数3: {product_info_param3}")
            response3 = work_session.post(path, product_info_param3)
            print(f"响应3: {response3}")
        
        # 清理product
        delete_response = work_session.delete(f'/api/v1/vmi/products/{product_id}')
        print(f"清理product: {delete_response}")
        
        return True
        
    except Exception as e:
        print(f"API调用异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_direct_api()
    sys.exit(0 if success else 1)