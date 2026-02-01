# VMI多租户测试框架使用指南

## 概述

VMI多租户测试框架在保持与现有autotest租户完全兼容的前提下，提供了灵活的多租户测试支持。框架默认禁用多租户功能，确保现有测试不受影响。

## 核心组件

### 1. 配置系统扩展 (`tenant_config_helper.py`)
- 向后兼容现有`test_config.json`格式
- 支持可选的多租户配置扩展
- 默认禁用多租户功能

### 2. 多租户会话管理器 (`multi_tenant_manager.py`)
- 包装现有的`SessionManager`，为每个租户创建独立实例
- 提供统一的租户会话管理接口
- 支持租户隔离和会话池管理

### 3. 多租户测试基类 (`test_base_multi_tenant.py`)
- 继承自现有的`TestBaseWithSessionManager`
- 添加多租户测试专用方法
- 保持现有测试代码完全兼容

## 使用方法

### 步骤1：配置多租户测试

1. 复制配置模板：
   ```bash
   cp test_config_multi_tenant_template.json test_config.json
   ```

2. 修改配置文件：
   - 将`"enabled": false`改为`"enabled": true`启用多租户
   - 配置实际的租户服务器地址和认证信息
   - 租户数量根据实际测试需求配置

### 步骤2：编写多租户测试

#### 方式1：使用多租户测试基类
```python
from test_base_multi_tenant import TestBaseMultiTenant

class TestMultiTenantWarehouse(TestBaseMultiTenant):
    def test_create_warehouse_in_all_tenants(self):
        """在所有租户中创建仓库"""
        def create_warehouse(tenant_id):
            # 获取租户特定的SDK
            warehouse_sdk = self.get_sdk_for_tenant(tenant_id, WarehouseSDK)
            
            # 创建仓库
            warehouse_data = {
                'name': f'仓库_{tenant_id}',
                'description': f'租户{tenant_id}的测试仓库'
            }
            result = warehouse_sdk.create_warehouse(warehouse_data)
            self.assertIsNotNone(result)
            return result
        
        # 为所有租户执行测试
        results = self.run_for_all_tenants(create_warehouse)
        
        # 验证所有租户都成功
        for tenant_id, result in results.items():
            self.assertEqual(result['status'], 'passed')
```

#### 方式2：使用上下文管理器
```python
from test_base_multi_tenant import SimpleMultiTenantTest

class TestMultiTenantWithContext(SimpleMultiTenantTest):
    def test_tenant_context(self):
        """使用上下文管理器切换租户"""
        with self.for_tenant("tenant1"):
            # 在这个代码块中，所有操作都在tenant1租户上执行
            result = self.warehouse_sdk.create_warehouse(data)
            self.assertIsNotNone(result)
        
        # 自动切换回原租户
```

#### 方式3：验证租户隔离性
```python
def test_tenant_isolation(self):
    """验证租户隔离性"""
    self.assert_tenant_isolation(
        "tenant1", "tenant2",
        lambda tenant_id: self.get_sdk_for_tenant(tenant_id, WarehouseSDK).list_warehouses()
    )
```

### 步骤3：运行测试

#### 单租户模式（默认）
```bash
# 多租户功能禁用，使用现有autotest租户
python3 run_all_tests.py --basic
```

#### 多租户模式
```bash
# 启用多租户功能后，可以运行多租户测试
python3 -m unittest test_multi_tenant_example.py
```

## 配置说明

### 配置文件结构
```json
{
  "server_url": "https://autotest.local.vpc",
  "username": "administrator",
  "password": "administrator",
  "namespace": "autotest",
  "multi_tenant": {
    "enabled": false,  // 多租户功能开关
    "default_tenant": "autotest",  // 默认租户
    "tenants": [  // 租户配置列表
      {
        "id": "autotest",
        "server_url": "https://autotest.local.vpc",
        "username": "administrator",
        "password": "administrator",
        "namespace": "autotest",
        "enabled": true
      },
      {
        "id": "tenant1",
        "server_url": "https://tenant1.local.vpc",
        "username": "admin1",
        "password": "password1",
        "namespace": "tenant1",
        "enabled": true
      }
    ]
  }
}
```

### 租户配置字段说明
- `id`: 租户唯一标识符
- `server_url`: 租户服务器地址（通过不同域名区分租户）
- `username`/`password`: 租户认证信息
- `namespace`: 租户命名空间（通常与id相同）
- `enabled`: 是否启用该租户测试

## 向后兼容性

### 完全兼容现有功能
1. **配置兼容**: 现有`test_config.json`无需修改
2. **代码兼容**: 现有测试代码无需修改
3. **行为兼容**: 多租户功能默认禁用，现有测试行为不变

### 平滑迁移路径
1. **阶段1**: 使用现有autotest租户，多租户功能禁用
2. **阶段2**: 启用多租户，配置实际租户信息
3. **阶段3**: 编写多租户测试用例
4. **阶段4**: 运行多租户测试验证

## 最佳实践

### 1. 租户命名规范
- 使用有意义的租户ID（如：`autotest`, `tenant1`, `production`）
- 保持租户ID与域名一致（如：`autotest.local.vpc`对应`autotest`租户）

### 2. 测试数据隔离
- 每个租户使用独立的数据集
- 验证租户间数据不可见
- 清理测试数据时按租户清理

### 3. 错误处理
- 一个租户的失败不应影响其他租户
- 提供详细的租户级错误报告
- 实现租户级别的重试机制

### 4. 性能考虑
- 控制并发租户数量
- 监控每个租户的资源使用
- 实现连接池和会话复用

## 故障排除

### 常见问题

#### Q1: 多租户功能未启用？
A: 检查`test_config.json`中的`multi_tenant.enabled`是否为`true`

#### Q2: 租户会话创建失败？
A: 检查租户配置的服务器地址、用户名和密码是否正确

#### Q3: 租户间数据泄露？
A: 使用`assert_tenant_isolation`方法验证租户隔离性

#### Q4: 性能下降？
A: 减少并发租户数量，优化会话管理配置

### 调试方法
```python
# 查看多租户配置
from tenant_config_helper import get_multi_tenant_config
config = get_multi_tenant_config()
print(f"多租户启用: {config['enabled']}")
print(f"租户列表: {list(config['tenants'].keys())}")

# 查看租户状态
from test_base_multi_tenant import TestBaseMultiTenant
test = TestBaseMultiTenant()
test.setUpClass()
status = test.get_all_tenant_status()
print(f"租户状态: {status}")
```

## 扩展开发

### 添加新的多租户功能
1. 在`multi_tenant_manager.py`中添加新功能
2. 在`test_base_multi_tenant.py`中暴露接口
3. 编写测试用例验证功能
4. 更新使用文档

### 集成现有测试
1. 将现有测试类改为继承`TestBaseMultiTenant`
2. 使用`run_for_all_tenants`方法运行多租户测试
3. 验证测试结果符合预期

## 版本历史

### v1.0.0 (2026-02-01)
- 初始版本发布
- 支持多租户配置管理
- 提供多租户测试基类
- 保持与现有autotest租户完全兼容

## 支持与反馈

如有问题或建议，请参考项目文档或联系开发团队。