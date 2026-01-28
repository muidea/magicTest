#!/usr/bin/env python3
"""简单测试网络请求是否真的发送到服务器"""

import sys
import os
import logging
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("=== 开始测试网络请求 ===")

# 添加路径
sys.path.insert(0, '/home/rangh/codespace/magicTest/session')

try:
    # 直接导入MagicSession
    from session import MagicSession
    print("✓ 成功导入 MagicSession")
    
    # 创建session
    server_url = 'https://autotest.local.vpc'
    work_session = MagicSession(server_url, '')
    print(f"✓ 创建 MagicSession: {server_url}")
    
    # 测试CAS登录（直接发送请求）
    print("\n=== 测试CAS登录 ===")
    
    # 直接使用session发送登录请求
    login_url = '/api/v1/cas/session/login/'
    login_data = {
        'account': 'administrator',
        'password': 'administrator'
    }
    
    print(f"发送登录请求到: {server_url}{login_url}")
    print(f"登录数据: {login_data}")
    
    # 使用session的post方法
    response = work_session.post(login_url, login_data)
    print(f"登录响应: {response}")
    
    if response and response.get('error') is None:
        value = response.get('value')
        if value:
            session_token = value.get('sessionToken')
            entity = value.get('entity')
            print(f"✓ 登录成功!")
            print(f"  Session Token: {session_token[:50]}...")
            print(f"  Entity: {entity}")
            
            # 绑定token
            work_session.bind_token(session_token)
            print("✓ 绑定token到session")
            
            # 测试获取店铺列表
            print("\n=== 测试获取店铺列表 ===")
            stores_url = '/api/v1/vmi/stores/'
            print(f"发送请求到: {server_url}{stores_url}")
            
            stores_response = work_session.get(stores_url, {})
            print(f"店铺列表响应: {stores_response}")
            
            if stores_response and stores_response.get('error') is None:
                stores = stores_response.get('value') or stores_response.get('values')
                if stores:
                    print(f"✓ 成功获取店铺列表，数量: {len(stores)}")
                    if len(stores) > 0:
                        first_store = stores[0]
                        print(f"  第一个店铺: ID={first_store.get('id')}, Name={first_store.get('name')}")
                else:
                    print("✓ 获取店铺列表成功，但列表为空")
            else:
                print("✗ 获取店铺列表失败")
                if stores_response:
                    error = stores_response.get('error')
                    print(f"  错误代码: {error.get('code')}")
                    print(f"  错误消息: {error.get('message')}")
        else:
            print("✗ 登录响应中没有value字段")
    else:
        print("✗ 登录失败")
        if response:
            error = response.get('error')
            print(f"  错误代码: {error.get('code')}")
            print(f"  错误消息: {error.get('message')}")
            
except Exception as e:
    print(f"✗ 测试过程中出现异常: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 测试完成 ===")