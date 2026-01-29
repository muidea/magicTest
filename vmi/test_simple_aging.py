#!/usr/bin/env python3
"""
简化版老化测试 - 只测试partner创建
"""

import sys
import os
import time
import random
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
    from sdk import PartnerSDK
    
    # 导入配置助手
    from config_helper import get_server_url, get_credentials
    
    # 初始化会话
    server_url = get_server_url()
    credentials = get_credentials()
    
    work_session = session.MagicSession(server_url, '')
    cas_session = Cas(work_session)
    
    if not cas_session.login(credentials['username'], credentials['password']):
        logger.error("CAS登录失败")
        sys.exit(1)
    
    work_session.bind_token(cas_session.get_session_token())
    logger.info("登录成功")
    
    # 初始化SDK
    partner_sdk = PartnerSDK(work_session)
    
    # 运行简单测试
    operation_count = 0
    success_count = 0
    start_time = time.time()
    
    logger.info("开始简单老化测试...")
    
    for i in range(10):  # 只运行10次操作
        try:
            operation_count += 1
            
            # 创建partner
            partner_data = {
                'name': f'简单测试合作伙伴_{i}_{int(time.time())}',
                'telephone': f'138{random.randint(10000000, 99999999)}',
                'wechat': f'wechat_{i}',
                'description': f'简单测试合作伙伴描述_{i}',
                'status': {'id': 3}
            }
            
            logger.info(f"尝试创建partner: {partner_data['name']}")
            result = partner_sdk.create_partner(partner_data)
            
            if result and 'id' in result:
                success_count += 1
                logger.info(f"成功创建partner, ID: {result['id']}")
            else:
                logger.error(f"创建partner失败: {result}")
            
            # 等待1秒
            time.sleep(1.0)
            
        except Exception as e:
            logger.error(f"操作异常: {e}")
            import traceback
            traceback.print_exc()
    
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info("测试完成")
    logger.info(f"总操作数: {operation_count}")
    logger.info(f"成功操作数: {success_count}")
    logger.info(f"成功率: {success_count/operation_count*100:.1f}%")
    logger.info(f"总耗时: {duration:.1f}秒")
    logger.info(f"平均操作耗时: {duration/operation_count:.3f}秒")
    
except Exception as e:
    logger.error(f"测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)