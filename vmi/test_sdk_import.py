"""测试 VMI SDK 导入和基本功能"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    # 测试导入 SDK 类
    from sdk import (
        VMISDKBase,
        PartnerSDK,
        StoreSDK,
        WarehouseSDK,
        ProductSDK,
        ShelfSDK
    )
    
    print("✅ SDK 类导入成功:")
    print(f"  - VMISDKBase: {VMISDKBase}")
    print(f"  - PartnerSDK: {PartnerSDK}")
    print(f"  - StoreSDK: {StoreSDK}")
    print(f"  - WarehouseSDK: {WarehouseSDK}")
    print(f"  - ProductSDK: {ProductSDK}")
    print(f"  - ShelfSDK: {ShelfSDK}")
    
    # 测试从现有文件导入
    try:
        from partner.partner import main as partner_main
        from store.store import main as store_main
        from warehouse.warehouse import main as warehouse_main
        from product.product import main as product_main
        
        print("\n✅ 现有测试文件导入成功:")
        print(f"  - partner.main: {partner_main}")
        print(f"  - store.main: {store_main}")
        print(f"  - warehouse.main: {warehouse_main}")
        print(f"  - product.main: {product_main}")
        
    except ImportError as e:
        print(f"\n⚠️  现有测试文件导入警告: {e}")
    
    print("\n✅ VMI SDK 封装验证完成！")
    print("现在可以针对各类实体编写测试用例，例如：")
    print("""
# 示例测试用例
from session import session
from sdk import PartnerSDK

# 创建会话
work_session = session.MagicSession('https://server.url', 'namespace')

# 使用 SDK
partner_sdk = PartnerSDK(work_session)

# 执行 CRUD 操作
# partner = partner_sdk.create_partner({...})
# partners = partner_sdk.filter_partner({...})
# partner = partner_sdk.query_partner(1)
# partner = partner_sdk.update_partner(1, {...})
# partner = partner_sdk.delete_partner(1)
""")
    
except ImportError as e:
    print(f"❌ SDK 导入失败: {e}")
    print("当前 Python 路径:")
    for p in sys.path:
        print(f"  - {p}")