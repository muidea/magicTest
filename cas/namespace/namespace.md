# Namespace Python 客户端

## 概述

`Namespace` 类是一个用于管理 CAS (Central Authentication Service) 命名空间的 Python 客户端。它提供了命名空间的完整 CRUD 操作（创建、读取、更新、删除）以及过滤查询功能，通过 HTTP 请求与后端 CAS API 通信。

**文件位置**: [`magicTest/cas/namespace/namespace.py`](magicTest/cas/namespace/namespace.py)

## 类定义

```python
class Namespace:
    """Namespace"""
    
    def __init__(self, work_session, defaultNamespace):
        self.session = work_session
        self.defaultNamespace = defaultNamespace
```

### 构造函数参数
- `work_session`: 一个 `MagicSession` 实例，用于处理 HTTP 请求和认证。
- `defaultNamespace`: 父命名空间标识符，用于 API 请求中的权限控制。

### 属性
- `session`: 绑定的 `MagicSession` 实例
- `defaultNamespace`: 父命名空间标识符

## 方法详细说明

### 1. `filter_namespace(param)`
**功能**: 过滤查询命名空间列表

**参数**:
- `param`: `dict` - 过滤条件参数，支持按名称、状态、作用域等字段过滤

**返回**: `list` 或 `None` - 匹配的命名空间列表，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/namespaces/` 并传递过滤参数
2. 检查响应中的错误信息
3. 成功时返回 `values` 字段中的命名空间列表
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/namespaces/`

**示例**:
```python
filter_param = {'name': 'test', 'status': 2}
namespaces = namespace_app.filter_namespace(filter_param)
```

### 2. `query_namespace(param)`
**功能**: 查询单个命名空间的详细信息

**参数**:
- `param`: `str` - 命名空间的唯一标识符（ID）

**返回**: `dict` 或 `None` - 命名空间的详细信息，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/namespaces/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的命名空间数据
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/namespaces/{id}`

**示例**:
```python
namespace_id = "1234567890abcdef"
namespace_info = namespace_app.query_namespace(namespace_id)
```

### 3. `create_namespace(param)`
**功能**: 创建新的命名空间

**参数**:
- `param`: `dict` - 命名空间创建参数，包含以下字段：
  - `name`: `str` - 命名空间名称（必填）
  - `description`: `str` - 命名空间描述
  - `status`: `int` - 状态（1=禁用，2=启用）
  - `startTime`: `int` - 开始时间（UTC 毫秒时间戳）
  - `expireTime`: `int` - 过期时间（UTC 毫秒时间戳）
  - `scope`: `str` - 作用域（如 "*" 表示全局，"n1,n2" 表示多作用域）

**返回**: `dict` 或 `None` - 创建的命名空间信息，失败返回 `None`

**内部流程**:
1. 发送 POST 请求到 `/cas/namespaces/`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的命名空间数据
4. 失败时记录详细的错误日志

**API 端点**: `POST /cas/namespaces/`

**示例**:
```python
param = {
    'name': 'test-namespace',
    'description': '测试命名空间',
    'status': 2,
    'startTime': 1672531200000,
    'expireTime': 1675123200000,
    'scope': '*'
}
new_namespace = namespace_app.create_namespace(param)
```

### 4. `update_namespace(param)`
**功能**: 更新现有命名空间

**参数**:
- `param`: `dict` - 命名空间更新参数，必须包含 `id` 字段

**返回**: `dict` 或 `None` - 更新后的命名空间信息，失败返回 `None`

**内部流程**:
1. 发送 PUT 请求到 `/cas/namespaces/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的命名空间数据
4. 失败时记录详细的错误日志

**API 端点**: `PUT /cas/namespaces/{id}`

**示例**:
```python
update_param = {
    'id': '1234567890abcdef',
    'name': 'updated-namespace',
    'description': '更新后的描述',
    'status': 1,
    'scope': 'n1,n2'
}
updated_namespace = namespace_app.update_namespace(update_param)
```

### 5. `delete_namespace(param)`
**功能**: 删除命名空间

**参数**:
- `param`: `str` - 要删除的命名空间 ID

**返回**: `dict` 或 `None` - 被删除的命名空间信息，失败返回 `None`

**内部流程**:
1. 发送 DELETE 请求到 `/cas/namespaces/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的命名空间数据
4. 失败时记录详细的错误日志

**API 端点**: `DELETE /cas/namespaces/{id}`

**示例**:
```python
namespace_id = "1234567890abcdef"
deleted_namespace = namespace_app.delete_namespace(namespace_id)
```

## 辅助函数

### `mock_namespace_param()`
**功能**: 生成模拟的命名空间参数，用于测试

**返回**: `dict` - 包含随机生成的命名空间参数

**参数说明**:
- 自动生成当前时间戳和未来30天的时间戳
- 使用 `mock.common` 模块生成随机名称和描述
- 默认状态为启用（2）
- 默认作用域为全局（"*"）

**示例**:
```python
from namespace.namespace import mock_namespace_param
param = mock_namespace_param()
```

### `main(server_url, namespace)`
**功能**: 主函数，演示完整的命名空间操作流程

**参数**:
- `server_url`: `str` - CAS 服务器 URL
- `namespace`: `str` - 命名空间标识符

**流程**:
1. 创建会话并登录 CAS
2. 生成模拟参数并创建命名空间
3. 验证创建结果
4. 过滤查询命名空间
5. 查询单个命名空间
6. 更新命名空间
7. 删除命名空间
8. 返回操作结果

## 错误处理机制

`Namespace` 类实现了完善的错误处理：

1. **HTTP 请求错误**: 检查响应是否为 `None` 或包含 `error` 字段
2. **响应数据验证**: 检查 `value` 或 `values` 字段是否存在
3. **详细日志记录**: 使用 Python `logging` 模块记录不同级别的日志
   - `logger.error()`: 记录错误详情，包括错误代码和消息
   - `logger.info()`: 记录成功操作
4. **错误返回类型**: 所有方法在失败时返回 `None`

## 命名空间数据结构

### 核心字段
| 字段名 | 类型 | 描述 | 示例 |
|--------|------|------|------|
| `id` | `int` | 命名空间唯一标识符 | `1234567890` |
| `name` | `str` | 命名空间名称 | `"test-namespace"` |
| `description` | `str` | 命名空间描述 | `"测试命名空间"` |
| `status` | `int` | 状态（1=禁用，2=启用） | `2` |
| `startTime` | `int` | 开始时间（UTC 毫秒时间戳） | `1672531200000` |
| `expireTime` | `int` | 过期时间（UTC 毫秒时间戳） | `1675123200000` |
| `scope` | `str` | 作用域定义 | `"*"`, `"n1,n2"`, `""` |

### 作用域说明
- `"*"`: 全局作用域，可访问所有命名空间
- `"n1,n2,n3"`: 多作用域，可访问指定的命名空间列表
- `""`: 空作用域，仅限自身访问

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
import time as dt
from session import session
from cas import cas
from mock import common
```

## 使用示例

### 基本用法
```python
from session import session
from cas import cas
from namespace.namespace import Namespace

# 创建会话并登录
server_url = 'https://panel.local.vpc/api/v1'
work_session = session.MagicSession(server_url, '')
cas_session = cas.Cas(work_session)
if not cas_session.login('administrator', 'administrator'):
    print("CAS登录失败")
    exit(1)

work_session.bind_token(cas_session.get_session_token())

# 创建 Namespace 客户端
namespace_app = Namespace(work_session, "super")

# 创建命名空间
from namespace.namespace import mock_namespace_param
param = mock_namespace_param()
new_ns = namespace_app.create_namespace(param)
if new_ns:
    print(f"创建成功: {new_ns['name']} (ID: {new_ns['id']})")
    
    # 查询命名空间
    queried_ns = namespace_app.query_namespace(new_ns['id'])
    print(f"查询结果: {queried_ns['description']}")
    
    # 更新命名空间
    update_param = new_ns.copy()
    update_param['description'] = '更新后的描述'
    updated_ns = namespace_app.update_namespace(update_param)
    
    # 删除命名空间
    deleted_ns = namespace_app.delete_namespace(new_ns['id'])
    print(f"删除成功: {deleted_ns['name']}")
```

## 注意事项

1. **认证要求**: 所有操作需要有效的 CAS 会话令牌
2. **权限控制**: 操作受父命名空间（`defaultNamespace`）权限限制
3. **时间格式**: 时间字段使用 UTC 毫秒时间戳
4. **作用域逻辑**: 作用域字段影响其他实体的访问权限
5. **错误处理**: 调用方需要检查每个方法的返回值
6. **日志配置**: 需要预先配置 Python logging 以查看日志输出

## 扩展建议

1. **添加批量操作**: 支持批量创建、更新、删除命名空间
2. **增加缓存机制**: 对频繁查询的命名空间信息添加缓存
3. **支持更多查询条件**: 扩展过滤参数支持更复杂的查询条件
4. **添加类型提示**: 为方法参数和返回值添加类型提示
5. **完善验证逻辑**: 增加输入参数验证和业务规则验证
6. **支持异步操作**: 添加异步 API 支持以提高性能

## 相关文件

- [`magicTest/cas/namespace/namespace.py`](magicTest/cas/namespace/namespace.py): 主实现文件
- [`magicTest/cas/namespace/namespace_test.py`](magicTest/cas/namespace/namespace_test.py): 单元测试文件
- [`magicTest/cas/namespace/test_cases.md`](magicTest/cas/namespace/test_cases.md): 测试用例文档
- [`magicTest/session/session.py`](magicTest/session/session.py): HTTP 会话管理
- [`magicTest/cas/cas/cas.py`](magicTest/cas/cas/cas.py): CAS 认证客户端
- [`magicTest/mock/common.py`](magicTest/mock/common.py): 模拟数据生成工具