#!/usr/bin/env python3
"""
调试product创建，对比product和productInfo
"""

import sys
import os
import logging

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas
from sdk import ProductSDK

def test_product_create():
    """测试product创建"""
    print("测试product创建...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 创建SDK实例
    product_sdk = ProductSDK(work_session)
    
    # 测试创建product
    print("创建product...")
    product_param = {
        'name': '调试测试产品',
        'description': '测试product创建',
        'status': {'id': 19}
    }
    
    try:
        product = product_sdk.create_product(product_param)
        if product:
            print(f"✓ product创建成功: ID={product.get('id')}")
            print(f"  返回数据: {product}")
            
            # 清理
            deleted = product_sdk.delete_product(product['id'])
            if deleted:
                print(f"✓ product删除成功: ID={deleted.get('id')}")
            else:
                print("✗ product删除失败")
            return True
        else:
            print("✗ product创建失败: 返回None")
            return False
    except Exception as e:
        print(f"✗ product创建异常: {e}")
        return False

if __name__ == '__main__':
    success = test_product_create()
    sys.exit(0 if success else 1)