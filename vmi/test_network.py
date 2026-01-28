#!/usr/bin/env python3
"""测试网络请求是否真的发送到服务器"""

import sys
import os
import logging

# 添加路径
sys.path.insert(0, '/home/rangh/codespace/magicTest/session')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas/cas')

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("=== 开始测试网络请求 ===")

try:
    from session import MagicSession
    print("✓ 成功导入 MagicSession")
    
    from cas.cas import Cas
    print("✓ 成功导入 Cas")
    
    # 创建session
    server_url = 'https://autotest.local.vpc'
    work_session = MagicSession(server_url, '')
    print(f"✓ 创建 MagicSession: {server_url}")
    
    # 创建CAS实例
    cas_session = Cas(work_session)
    print("✓ 创建 Cas 实例")
    
    # 尝试登录
    print("尝试登录到 CAS...")
    username = 'administrator'
    password = 'administrator'
    
    login_result = cas_session.login(username, password)
    print(f"登录结果: {login_result}")
    
    if login_result:
        token = cas_session.get_session_token()
        print(f"✓ 获取到 token: {token[:50]}...")
        
        # 绑定token
        work_session.bind_token(token)
        print("✓ 绑定 token 到 session")
        
        # 测试一个简单的API请求
        print("\n=== 测试API请求 ===")
        
        # 导入common模块
        sys.path.insert(0, '/home/rangh/codespace/magicTest/session')
        import common
        
        # 创建MagicEntity
        entity = common.MagicEntity('/api/v1/vmi/store', work_session)
        print("✓ 创建 MagicEntity")
        
        # 尝试过滤（获取店铺列表）
        print("尝试获取店铺列表...")
        stores = entity.filter({})
        
        if stores is not None:
            print(f"✓ 成功获取店铺列表，数量: {len(stores)}")
            if stores:
                print(f"第一个店铺: ID={stores[0].get('id')}, Name={stores[0].get('name')}")
        else:
            print("✗ 获取店铺列表失败")
            
        # 尝试创建一个测试店铺
        print("\n=== 测试创建店铺 ===")
        import time
        test_store_name = f"TEST_STORE_{int(time.time())}"
        store_param = {
            'name': test_store_name,
            'description': '测试店铺，用于验证网络请求'
        }
        
        print(f"尝试创建店铺: {test_store_name}")
        new_store = entity.insert(store_param)
        
        if new_store is not None:
            print(f"✓ 成功创建店铺: ID={new_store.get('id')}, Name={new_store.get('name')}")
            
            # 删除测试店铺
            print(f"尝试删除测试店铺 ID={new_store.get('id')}")
            deleted = entity.delete(new_store.get('id'))
            if deleted is not None:
                print("✓ 成功删除测试店铺")
            else:
                print("✗ 删除测试店铺失败")
        else:
            print("✗ 创建店铺失败")
            
    else:
        print("✗ CAS登录失败")
        
except Exception as e:
    print(f"✗ 测试过程中出现异常: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 测试完成 ===")