# MagicSession & MagicEntity 使用说明

## 概述

`MagicSession` 和 `MagicEntity` 是用于HTTP API交互的Python库，提供会话管理、认证支持和实体操作功能。优化后的版本增强了安全性、错误处理和代码可维护性。

## 安装与导入

### 导入方式
```python
# 方式1：直接导入
from session import MagicSession
from common import MagicEntity

# 方式2：通过包导入（如果配置了Python路径）
from magicTest.session import MagicSession
from magicTest.session.common import MagicEntity
```

## MagicSession 使用指南

### 初始化
```python
# 基本初始化
session = MagicSession(base_url="https://api.example.com")

# 带命名空间初始化
session = MagicSession(
    base_url="https://api.example.com",
    namespace="my-namespace"
)
```

### 认证配置

#### Bearer Token 认证
```python
session.bind_token("your-bearer-token-here")
```

#### 签名认证
```python
session.bind_auth_secret(
    endpoint="your-endpoint",
    auth_token="your-auth-token"
)
```

#### 应用标识
```python
session.bind_application("your-application-id")
```

### 环境变量配置

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `VERIFY_SSL` | `false` | 是否验证SSL证书（`true`/`false`） |
| `REQUEST_TIMEOUT` | `30.0` | 请求超时时间（秒） |
| `ENVIRONMENT` | `development` | 运行环境，开发环境会禁用SSL警告 |

### HTTP 方法

#### GET 请求
```python
response = session.get("/api/users", params={"page": 1, "limit": 10})
```

#### POST 请求
```python
data = {"name": "John", "email": "john@example.com"}
response = session.post("/api/users", params=data)
```

#### PUT 请求
```python
data = {"name": "John Updated"}
response = session.put("/api/users/123", params=data)
```

#### DELETE 请求
```python
response = session.delete("/api/users/123")
```

#### 文件上传
```python
files = {"file": open("document.pdf", "rb")}
response = session.upload("/api/upload", files=files)
```

#### 文件下载
```python
result = session.download("/api/files/123", dst_file="/tmp/file.pdf")
if isinstance(result, dict) and "error" in result:
    print(f"下载失败: {result['error']['message']}")
else:
    print(f"文件已下载到: {result}")
```

### 错误处理

所有方法返回统一的响应格式：

#### 成功响应
```python
{
    "value": {...},  # 或 "values": [...]
    # 其他响应字段...
}
```

#### 错误响应
```python
{
    "error": {
        "code": 100,  # 错误代码
        "message": "错误描述",
    }
}
```

### 创建新会话
```python
new_session = session.new_session()  # 复制当前配置创建新会话
```

## MagicEntity 使用指南

### 初始化
```python
session = MagicSession("https://api.example.com")
entity = MagicEntity(
    base_url="https://api.example.com/api/users",  # 实体基础URL
    work_session=session
)
```

### 实体操作

#### 1. 过滤查询（列表）
```python
# 查询所有用户
users = entity.filter({})

# 带条件过滤
filtered_users = entity.filter({"status": "active", "role": "admin"})
```

#### 2. 查询单个实体
```python
user = entity.query(123)  # 查询ID为123的用户
```

#### 3. 插入新实体
```python
new_user = entity.insert({
    "name": "Alice",
    "email": "alice@example.com",
    "role": "user"
})
```

#### 4. 更新实体
```python
updated_user = entity.update(123, {
    "name": "Alice Updated",
    "status": "active"
})
```

#### 5. 删除实体
```python
result = entity.delete(123)
```

#### 6. 特殊创建操作
```python
# 使用特殊的create端点（URL: {base_url}/create/）
created = entity.create({
    "type": "special",
    "data": {...}
})
```

#### 7. 特殊销毁操作
```python
# 使用特殊的destroy端点（URL: {base_url}/destroy/{id}）
result = entity.destroy(123)
```

### URL 模式说明

| 方法 | URL 模式 | 示例 |
|------|----------|------|
| `filter` | `{base_url}s/` | `https://api.example.com/api/userss/` |
| `query` | `{base_url}s/{id}` | `https://api.example.com/api/userss/123` |
| `insert` | `{base_url}s/` | `https://api.example.com/api/userss/` |
| `update` | `{base_url}s/{id}` | `https://api.example.com/api/userss/123` |
| `delete` | `{base_url}s/{id}` | `https://api.example.com/api/userss/123` |
| `create` | `{base_url}/create/` | `https://api.example.com/api/users/create/` |
| `destroy` | `{base_url}/destroy/{id}` | `https://api.example.com/api/users/destroy/123` |

**注意**：`create` 和 `destroy` 方法的URL模式保持不变，与原始实现一致。

## 错误处理与日志

### 日志配置
```python
import logging

# 配置日志级别
logging.basicConfig(level=logging.INFO)

# 如果需要更详细的日志
logging.getLogger("session").setLevel(logging.DEBUG)
```

### 错误检查
```python
response = entity.query(999)
if response is None:
    print("查询失败，请检查日志")
else:
    print(f"查询结果: {response}")
```

## 完整示例

### 示例1：完整的用户管理流程
```python
from session import MagicSession
from common import MagicEntity

# 1. 初始化会话
session = MagicSession("https://api.example.com")
session.bind_token("your-token-here")

# 2. 初始化用户实体
user_entity = MagicEntity(
    base_url="https://api.example.com/api/users",
    work_session=session
)

# 3. 创建新用户
new_user = user_entity.insert({
    "name": "John Doe",
    "email": "john@example.com",
    "role": "user"
})

if new_user:
    print(f"用户创建成功，ID: {new_user.get('id')}")
    
    # 4. 查询用户
    user = user_entity.query(new_user['id'])
    print(f"用户信息: {user}")
    
    # 5. 更新用户
    updated = user_entity.update(new_user['id'], {"status": "active"})
    
    # 6. 删除用户
    # result = user_entity.delete(new_user['id'])
else:
    print("用户创建失败")
```

### 示例2：批量操作
```python
# 查询所有活跃用户
active_users = user_entity.filter({"status": "active"})
if active_users:
    print(f"找到 {len(active_users)} 个活跃用户")
    
    # 批量更新
    for user in active_users:
        user_entity.update(user['id'], {"last_seen": "2024-01-01"})
```

## 最佳实践

1. **会话复用**：尽可能复用 `MagicSession` 实例，避免频繁创建新会话
2. **错误处理**：始终检查返回结果是否为 `None`，并查看日志了解详细错误
3. **超时设置**：根据网络环境调整 `REQUEST_TIMEOUT` 环境变量
4. **SSL验证**：生产环境务必设置 `VERIFY_SSL=true`
5. **日志记录**：合理配置日志级别，便于调试和监控

## 故障排除

### 常见问题

1. **SSL证书验证失败**
   ```
   设置环境变量：export VERIFY_SSL=false（仅限开发环境）
   ```

2. **请求超时**
   ```
   增加超时时间：export REQUEST_TIMEOUT=60.0
   ```

3. **认证失败**
   - 检查token是否正确绑定
   - 验证API端点是否支持当前认证方式

4. **响应解析错误**
   - 检查API返回的是否为有效的JSON格式
   - 查看日志中的详细错误信息

### 调试模式
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 版本说明

### 优化内容（当前版本）
1. 增强SSL验证安全性
2. 改进错误处理，支持更详细的错误信息
3. 添加类型注解，提高代码可读性
4. 提取公共方法，减少代码重复
5. 支持环境变量配置
6. 保持API完全兼容

### 向后兼容性
- 所有现有接口保持不变
- `create` 和 `destroy` 方法的URL模式保持不变
- 错误响应格式保持兼容