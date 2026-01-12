# Account Python 客户端

## 概述

`Account` 类是一个用于管理 CAS (Central Authentication Service) 账户的 Python 客户端。它提供了账户的完整 CRUD 操作（创建、读取、更新、删除）以及过滤查询功能，通过 HTTP 请求与后端 CAS API 通信。账户是系统用户的基本实体，可以关联角色和命名空间。

**文件位置**: [`magicTest/cas/account/account.py`](magicTest/cas/account/account.py)

## 类定义

```python
class Account:
    """Account"""
    
    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session
```

### 构造函数参数
- `work_session`: 一个 `MagicSession` 实例，用于处理 HTTP 请求和认证。

### 属性
- `session`: 绑定的 `MagicSession` 实例

## 方法详细说明

### 1. `filter_account(param)`
**功能**: 过滤查询账户列表

**参数**:
- `param`: `dict` - 过滤条件参数，支持按账户名、邮箱、命名空间等字段过滤

**返回**: `list` 或 `None` - 匹配的账户列表，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/accounts/` 并传递过滤参数
2. 检查响应中的错误信息
3. 成功时返回 `values` 字段中的账户列表
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/accounts/`

**示例**:
```python
filter_param = {'account': 'admin', 'namespace': 'default'}
accounts = account_app.filter_account(filter_param)
```

### 2. `query_account(account_id)`
**功能**: 查询单个账户的详细信息

**参数**:
- `account_id`: `int` - 账户的唯一标识符（ID）

**返回**: `dict` 或 `None` - 账户的详细信息，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/accounts/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的账户数据
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/accounts/{id}`

**示例**:
```python
account_id = 12345
account_info = account_app.query_account(account_id)
```

### 3. `create_account(param)`
**功能**: 创建新的账户

**参数**:
- `param`: `dict` - 账户创建参数，包含以下字段：
  - `account`: `str` - 账户名称（必填）
  - `password`: `str` - 账户密码
  - `email`: `str` - 邮箱地址
  - `description`: `str` - 账户描述
  - `namespace`: `str` - 命名空间标识符
  - `roleLite`: `dict` - 可选的角色关联信息，包含：
    - `id`: `int` - 角色ID
    - `name`: `str` - 角色名称

**返回**: `dict` 或 `None` - 创建的账户信息，失败返回 `None`

**内部流程**:
1. 发送 POST 请求到 `/cas/accounts/`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的账户数据
4. 失败时记录详细的错误日志

**API 端点**: `POST /cas/accounts/`

**示例**:
```python
param = {
    'account': 'testuser',
    'password': 'SecurePass123',
    'email': 'test@example.com',
    'description': '测试账户',
    'namespace': 'default',
    'roleLite': {
        'id': 1,
        'name': '管理员'
    }
}
new_account = account_app.create_account(param)
```

### 4. `update_account(param)`
**功能**: 更新现有账户

**参数**:
- `param`: `dict` - 账户更新参数，必须包含 `id` 字段

**返回**: `dict` 或 `None` - 更新后的账户信息，失败返回 `None`

**内部流程**:
1. 发送 PUT 请求到 `/cas/accounts/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的账户数据
4. 失败时记录详细的错误日志

**API 端点**: `PUT /cas/accounts/{id}`

**示例**:
```python
update_param = {
    'id': 12345,
    'account': 'updateduser',
    'email': 'updated@example.com',
    'description': '更新后的描述',
    'namespace': 'new-namespace'
}
updated_account = account_app.update_account(update_param)
```

### 5. `delete_account(account_id)`
**功能**: 删除账户

**参数**:
- `account_id`: `int` - 要删除的账户 ID

**返回**: `dict` 或 `None` - 被删除的账户信息，失败返回 `None`

**内部流程**:
1. 发送 DELETE 请求到 `/cas/accounts/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的账户数据
4. 失败时记录详细的错误日志

**API 端点**: `DELETE /cas/accounts/{id}`

**示例**:
```python
account_id = 12345
deleted_account = account_app.delete_account(account_id)
```

## 辅助函数

### `mock_account_param(namespace)`
**功能**: 生成模拟的账户参数，用于测试

**参数**:
- `namespace`: `str` - 命名空间标识符

**返回**: `dict` - 包含随机生成的账户参数

**参数说明**:
- 使用 `mock.common` 模块生成随机账户名、邮箱和描述
- 默认密码为 "123"
- 使用传入的命名空间参数

**示例**:
```python
from account.account import mock_account_param
param = mock_account_param("test-namespace")
```

### `main(server_url, namespace)`
**功能**: 主函数，演示完整的账户操作流程

**参数**:
- `server_url`: `str` - CAS 服务器 URL
- `namespace`: `str` - 命名空间标识符

**流程**:
1. 创建会话并登录 CAS
2. 生成模拟参数并创建账户
3. 验证创建结果
4. 过滤查询账户
5. 查询单个账户
6. 更新账户
7. 删除账户
8. 返回操作结果

## 错误处理机制

`Account` 类实现了完善的错误处理：

1. **HTTP 请求错误**: 检查响应是否为 `None` 或包含 `error` 字段
2. **响应数据验证**: 检查 `value` 或 `values` 字段是否存在
3. **详细日志记录**: 使用 Python `logging` 模块记录不同级别的日志
   - `logger.error()`: 记录错误详情，包括错误代码和消息
   - `logger.info()`: 记录成功操作
4. **错误返回类型**: 所有方法在失败时返回 `None`
5. **类型提示**: 使用 Python 类型提示提高代码可读性和类型安全性

## 账户数据结构

### 核心字段
| 字段名 | 类型 | 描述 | 示例 |
|--------|------|------|------|
| `id` | `int` | 账户唯一标识符 | `12345` |
| `account` | `str` | 账户名称 | `"testuser"` |
| `email` | `str` | 邮箱地址 | `"test@example.com"` |
| `description` | `str` | 账户描述 | `"测试账户"` |
| `namespace` | `str` | 命名空间标识符 | `"default"` |
| `roleLite` | `dict` | 关联的角色信息（可选） | `{"id": 1, "name": "管理员"}` |

### 角色关联对象结构
| 字段名 | 类型 | 描述 | 示例 |
|--------|------|------|------|
| `id` | `int` | 角色ID | `1` |
| `name` | `str` | 角色名称 | `"管理员"` |

### 安全注意事项
- **密码字段**: 创建和更新时传入的 `password` 字段不会在返回的账户信息中显示
- **敏感信息**: 账户信息中不包含明文密码，确保密码安全

## 依赖关系

### 核心依赖
- `session.MagicSession`: HTTP 客户端会话管理
- `cas.Cas`: CAS 认证客户端
- `mock.common`: 模拟数据生成
- `logging`: Python 标准日志模块
- `typing`: Python 类型提示模块

### 导入语句
```python
import logging
from typing import Optional, Dict, Any, List
from session import session
from cas import cas
from mock import common
```

## 使用示例

### 基本用法
```python
from session import session
from cas import cas
from account.account import Account

# 创建会话并登录
server_url = 'https://autotest.local.vpc/api/v1'
work_session = session.MagicSession(server_url, '')
cas_session = cas.Cas(work_session)
if not cas_session.login('administrator', 'administrator'):
    print("CAS登录失败")
    exit(1)

work_session.bind_token(cas_session.get_session_token())

# 创建 Account 客户端
account_app = Account(work_session)

# 创建账户
from account.account import mock_account_param
param = mock_account_param("default")
new_account = account_app.create_account(param)
if new_account:
    print(f"创建成功: {new_account['account']} (ID: {new_account['id']})")
    
    # 查询账户
    queried_account = account_app.query_account(new_account['id'])
    print(f"查询结果: {queried_account['email']}")
    
    # 更新账户
    update_param = new_account.copy()
    update_param['description'] = '更新后的描述'
    updated_account = account_app.update_account(update_param)
    
    # 删除账户
    deleted_account = account_app.delete_account(new_account['id'])
    print(f"删除成功: {deleted_account['account']}")
```

## API 端点总结

| 方法 | HTTP 方法 | 端点 | 功能 |
|------|-----------|------|------|
| `filter_account()` | GET | `/cas/accounts/` | 过滤查询账户列表 |
| `query_account()` | GET | `/cas/accounts/{id}` | 查询单个账户 |
| `create_account()` | POST | `/cas/accounts/` | 创建账户 |
| `update_account()` | PUT | `/cas/accounts/{id}` | 更新账户 |
| `delete_account()` | DELETE | `/cas/accounts/{id}` | 删除账户 |

## 注意事项

1. **认证要求**: 所有操作需要有效的 CAS 会话令牌
2. **命名空间隔离**: 账户受命名空间隔离，不同命名空间的账户可以同名
3. **角色关联**: 角色关联是可选的，但关联的角色必须存在
4. **密码安全**: 密码在传输和存储时会被加密，返回的账户信息中不包含明文密码
5. **邮箱唯一性**: 邮箱地址在系统中应该是唯一的（除非有命名空间隔离）
6. **错误处理**: 调用方需要检查每个方法的返回值
7. **日志配置**: 需要预先配置 Python logging 以查看日志输出

## 扩展建议

1. **添加密码验证功能**: 实现密码验证接口，用于用户登录验证
2. **增加密码重置功能**: 添加密码重置和修改功能
3. **支持批量操作**: 支持批量创建、更新、删除账户
4. **添加账户状态管理**: 支持启用/禁用账户状态
5. **完善权限控制**: 添加基于角色的账户权限验证
6. **添加类型提示**: 为所有公共方法添加完整的类型提示
7. **支持异步操作**: 添加异步 API 支持以提高性能
8. **添加缓存机制**: 对频繁查询的账户信息添加缓存

## 相关文件

- [`magicTest/cas/account/account.py`](magicTest/cas/account/account.py): 主实现文件
- [`magicTest/cas/account/account_test.py`](magicTest/cas/account/account_test.py): 单元测试文件
- [`magicTest/cas/account/test_cases.md`](magicTest/cas/account/test_cases.md): 测试用例文档
- [`magicTest/session/session.py`](magicTest/session/session.py): HTTP 会话管理
- [`magicTest/cas/cas/cas.py`](magicTest/cas/cas/cas.py): CAS 认证客户端
- [`magicTest/mock/common.py`](magicTest/mock/common.py): 模拟数据生成工具
- [`magicTest/cas/role/role.py`](magicTest/cas/role/role.py): Role 模块（账户可能关联角色）
- [`magicTest/cas/namespace/namespace_documentation.md`](magicTest/cas/namespace/namespace_documentation.md): Namespace 模块文档
- [`magicTest/cas/role/role_documentation.md`](magicTest/cas/role/role_documentation.md): Role 模块文档