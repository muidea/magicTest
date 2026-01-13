# Endpoint Python 客户端

## 概述

`Endpoint` 类是一个用于管理 CAS (Central Authentication Service) 端点的 Python 客户端。它提供了端点的完整 CRUD 操作（创建、读取、更新、删除）以及过滤查询功能，通过 HTTP 请求与后端 CAS API 通信。端点用于定义 API 访问路径及其关联的权限控制。

**文件位置**: [`magicTest/cas/endpoint/endpoint.py`](magicTest/cas/endpoint/endpoint.py)

## 类定义

```python
class Endpoint:
    """Endpoint"""
    
    def __init__(self, work_session):
        self.session = work_session
```

### 构造函数参数
- `work_session`: 一个 `MagicSession` 实例，用于处理 HTTP 请求和认证。

### 属性
- `session`: 绑定的 `MagicSession` 实例

## 方法详细说明

### 1. `filter_endpoint(param)`
**功能**: 过滤查询端点列表

**参数**:
- `param`: `dict` - 过滤条件参数，支持按端点路径、状态、作用域、时间范围等字段过滤

**返回**: `list` 或 `None` - 匹配的端点列表，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/endpoints/` 并传递过滤参数
2. 检查响应中的错误信息
3. 成功时返回 `values` 字段中的端点列表
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/endpoints/`

**示例**:
```python
filter_param = {'endpoint': '/api/v1/test', 'status': 2}
endpoints = endpoint_app.filter_endpoint(filter_param)
```

### 2. `query_endpoint(param)`
**功能**: 查询单个端点的详细信息

**参数**:
- `param`: `str` - 端点的唯一标识符（ID）

**返回**: `dict` 或 `None` - 端点的详细信息，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/endpoints/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的端点数据
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/endpoints/{id}`

**示例**:
```python
endpoint_id = "1234567890abcdef"
endpoint_info = endpoint_app.query_endpoint(endpoint_id)
```

### 3. `create_endpoint(param)`
**功能**: 创建新的端点

**参数**:
- `param`: `dict` - 端点创建参数，包含以下字段：
  - `name`: `str` - 端点名称（必填）
  - `description`: `str` - 端点描述
  - `account`: `dict` - 关联的账户信息（AccountLite 对象）
  - `role`: `dict` - 关联的角色信息（RoleLite 对象）
  - `scope`: `str` - 作用域（如 "*" 表示全局，"n1,n2" 表示多作用域）
  - `status`: `int` - 状态（1=禁用，2=启用）
  - `startTime`: `int` - 开始时间（UTC 毫秒时间戳）
  - `expireTime`: `int` - 过期时间（UTC 毫秒时间戳）

**返回**: `dict` 或 `None` - 创建的端点信息，失败返回 `None`

**内部流程**:
1. 发送 POST 请求到 `/cas/endpoints/`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的端点数据
4. 失败时记录详细的错误日志

**API 端点**: `POST /cas/endpoints/`

**示例**:
```python
param = {
    'name': 'users',
    'description': '用户管理端点',
    'account': {'id': 1, 'account': 'admin', 'status': 2},
    'role': {'id': 1, 'name': 'administrator', 'status': 2},
    'scope': '*',
    'status': 2,
    'startTime': 1672531200000,
    'expireTime': 1675123200000
}
new_endpoint = endpoint_app.create_endpoint(param)
```

### 4. `update_endpoint(param)`
**功能**: 更新现有端点

**参数**:
- `param`: `dict` - 端点更新参数，必须包含 `id` 字段

**返回**: `dict` 或 `None` - 更新后的端点信息，失败返回 `None`

**内部流程**:
1. 发送 PUT 请求到 `/cas/endpoints/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的端点数据
4. 失败时记录详细的错误日志

**API 端点**: `PUT /cas/endpoints/{id}`

**示例**:
```python
update_param = {
    'id': '1234567890abcdef',
    'name': 'users',
    'description': '更新后的用户管理端点',
    'scope': 'n1,n2',
    'status': 1,
    'startTime': 1672531200000,
    'expireTime': 1675123200000
}
updated_endpoint = endpoint_app.update_endpoint(update_param)
```

### 5. `delete_endpoint(param)`
**功能**: 删除端点

**参数**:
- `param`: `str` - 要删除的端点 ID

**返回**: `dict` 或 `None` - 被删除的端点信息，失败返回 `None`

**内部流程**:
1. 发送 DELETE 请求到 `/cas/endpoints/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的端点数据
4. 失败时记录详细的错误日志

**API 端点**: `DELETE /cas/endpoints/{id}`

**示例**:
```python
endpoint_id = "1234567890abcdef"
deleted_endpoint = endpoint_app.delete_endpoint(endpoint_id)
```

## 辅助函数

### `mock_endpoint_param()`
**功能**: 生成模拟的端点参数，用于测试

**返回**: `dict` - 包含随机生成的端点参数

**参数说明**:
- 自动生成当前时间戳和未来30天的时间戳
- 使用 `mock.common` 模块生成随机端点路径和描述
- 创建模拟的 AccountLite 和 RoleLite 对象
- 默认状态为启用（2）
- 默认作用域为全局（"*"）

**示例**:
```python
from endpoint.endpoint import mock_endpoint_param
param = mock_endpoint_param()
```

### `main(server_url, namespace)`
**功能**: 主函数，演示完整的端点操作流程

**参数**:
- `server_url`: `str` - CAS 服务器 URL
- `namespace`: `str` - 命名空间标识符

**流程**:
1. 创建会话并登录 CAS
2. 生成模拟参数并创建端点
3. 验证创建结果
4. 尝试创建重复端点（应失败）
5. 过滤查询端点
6. 查询单个端点
7. 更新端点（修改描述、作用域、状态、时间）
8. 验证更新结果
9. 删除端点
10. 返回操作结果

## 错误处理机制

`Endpoint` 类实现了完善的错误处理：

1. **HTTP 请求错误**: 检查响应是否为 `None` 或包含 `error` 字段
2. **响应数据验证**: 检查 `value` 或 `values` 字段是否存在
3. **详细日志记录**: 使用 Python `logging` 模块记录不同级别的日志
   - `logger.error()`: 记录错误详情，包括错误代码和消息
   - `logger.info()`: 记录成功操作
4. **错误返回类型**: 所有方法在失败时返回 `None`

## 端点数据结构

### 核心字段
| 字段名 | 类型 | 描述 | 示例 |
|--------|------|------|------|
| `id` | `int` | 端点唯一标识符 | `12345` |
| `name` | `str` | 端点名称 | `"users"` |
| `description` | `str` | 端点描述 | `"用户管理端点"` |
| `account` | `dict` | 关联账户信息（AccountLite） | `{'id': 1, 'account': 'admin', 'status': 2}` |
| `role` | `dict` | 关联角色信息（RoleLite） | `{'id': 1, 'name': 'administrator', 'status': 2}` |
| `scope` | `str` | 作用域定义 | `"*"`, `"n1,n2"`, `""` |
| `status` | `int` | 状态（1=禁用，2=启用） | `2` |
| `startTime` | `int` | 开始时间（UTC 毫秒时间戳） | `1672531200000` |
| `expireTime` | `int` | 过期时间（UTC 毫秒时间戳） | `1675123200000` |

### AccountLite 对象结构
| 字段名 | 类型 | 描述 |
|--------|------|------|
| `id` | `int` | 账户ID |
| `account` | `str` | 账户名称 |
| `status` | `int` | 账户状态 |

### RoleLite 对象结构
| 字段名 | 类型 | 描述 |
|--------|------|------|
| `id` | `int` | 角色ID |
| `name` | `str` | 角色名称 |
| `status` | `int` | 角色状态 |

### 作用域说明
- `"*"`: 全局作用域，可访问所有命名空间
- `"n1,n2,n3"`: 多作用域，可访问指定的命名空间列表
- `""`: 空作用域，仅限自身访问

### 状态说明
- `1`: 禁用状态，端点不可用
- `2`: 启用状态，端点可用

## 依赖关系

### 核心依赖
- `session.MagicSession`: HTTP 客户端会话管理
- `cas.Cas`: CAS 认证客户端
- `mock.common`: 模拟数据生成
- `logging`: Python 标准日志模块
- `time`: 时间处理模块

### 导入语句
```python
import logging
from session import session
from cas import cas
from mock import common
```

## 使用示例

### 基本用法
```python
from session import session
from cas import cas
from endpoint.endpoint import Endpoint

# 创建会话并登录
server_url = 'https://autotest.local.vpc/api/v1'
work_session = session.MagicSession(server_url, '')
cas_session = cas.Cas(work_session)
if not cas_session.login('administrator', 'administrator'):
    print("CAS登录失败")
    exit(1)

work_session.bind_token(cas_session.get_session_token())

# 创建 Endpoint 客户端
endpoint_app = Endpoint(work_session)

# 创建端点
from endpoint.endpoint import mock_endpoint_param
param = mock_endpoint_param()
new_endpoint = endpoint_app.create_endpoint(param)
if new_endpoint:
    print(f"创建成功: {new_endpoint['endpoint']} (ID: {new_endpoint['id']})")
    
    # 查询端点
    queried_endpoint = endpoint_app.query_endpoint(new_endpoint['id'])
    print(f"查询结果: {queried_endpoint['description']}")
    
    # 更新端点
    update_param = new_endpoint.copy()
    update_param['description'] = '更新后的描述'
    update_param['scope'] = 'n1,n2'
    update_param['status'] = 1
    updated_endpoint = endpoint_app.update_endpoint(update_param)
    
    # 过滤端点
    filter_param = {'endpoint': new_endpoint['endpoint']}
    filtered_endpoints = endpoint_app.filter_endpoint(filter_param)
    print(f"过滤结果: {len(filtered_endpoints)} 个端点")
    
    # 删除端点
    deleted_endpoint = endpoint_app.delete_endpoint(new_endpoint['id'])
    print(f"删除成功: {deleted_endpoint['endpoint']}")
```

### 测试场景示例
```python
# 场景 E1: 端点时效性验证
def test_endpoint_timeliness():
    # 创建有效时间的端点 (StartTime < 当前时间 < ExpireTime)
    valid_endpoint = create_test_endpoint(
        account_id, role_id,
        start_time_offset=-3600000,  # 1小时前
        expire_time_offset=86400000  # 24小时后
    )
    
    # 创建已过期的端点 (ExpireTime < 当前时间)
    expired_endpoint_param = {
        'name': 'test',
        'description': '已过期端点',
        'account': account_lite,
        'role': role_lite,
        'scope': '*',
        'status': 2,
        'startTime': current_time_ms - 172800000,  # 2天前
        'expireTime': current_time_ms - 86400000   # 1天前
    }
    
    # 创建未开始的端点 (StartTime > 当前时间)
    future_endpoint_param = {
        'name': 'test',
        'description': '未开始端点',
        'account': account_lite,
        'role': role_lite,
        'scope': '*',
        'status': 2,
        'startTime': current_time_ms + 3600000,    # 1小时后
        'expireTime': current_time_ms + 172800000  # 2天后
    }
```

## 注意事项

1. **认证要求**: 所有操作需要有效的 CAS 会话令牌
2. **关联对象验证**: 创建端点时需要有效的 Account 和 Role 对象
3. **时间逻辑**: `startTime` 必须小于 `expireTime`，否则创建会失败
4. **端点路径唯一性**: 同一路径的端点不能重复创建
5. **作用域逻辑**: 作用域字段影响端点的访问权限
6. **错误处理**: 调用方需要检查每个方法的返回值
7. **日志配置**: 需要预先配置 Python logging 以查看日志输出

## 扩展建议

1. **添加批量操作**: 支持批量创建、更新、删除端点
2. **增加缓存机制**: 对频繁查询的端点信息添加缓存
3. **支持更多查询条件**: 扩展过滤参数支持更复杂的查询条件
4. **添加类型提示**: 为方法参数和返回值添加类型提示
5. **完善验证逻辑**: 增加输入参数验证和业务规则验证
6. **支持异步操作**: 添加异步 API 支持以提高性能
7. **添加端点权限验证**: 增加端点访问权限验证功能
8. **支持端点分组**: 添加端点分组管理功能

## 相关文件

- [`magicTest/cas/endpoint/endpoint.py`](magicTest/cas/endpoint/endpoint.py): 主实现文件
- [`magicTest/cas/endpoint/endpoint_test.py`](magicTest/cas/endpoint/endpoint_test.py): 单元测试文件
- [`magicTest/cas/endpoint/test_cases.md`](magicTest/cas/endpoint/test_cases.md): 测试用例文档
- [`magicTest/session/session.py`](magicTest/session/session.py): HTTP 会话管理
- [`magicTest/cas/cas/cas.py`](magicTest/cas/cas/cas.py): CAS 认证客户端
- [`magicTest/mock/common.py`](magicTest/mock/common.py): 模拟数据生成工具
- [`magicTest/cas/account/account.py`](magicTest/cas/account/account.py): Account 客户端（依赖）
- [`magicTest/cas/role/role.py`](magicTest/cas/role/role.py): Role 客户端（依赖）