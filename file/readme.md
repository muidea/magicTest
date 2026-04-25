# 文件服务客户端

基于 `magicFile/pkg/client/client.go` 实现的 Python 客户端，提供完整的文件操作接口。

本地验证默认目标服务是 `https://autotest.local.vpc`，如需切换环境，可通过 `MAGICTEST_FILE_BASE_URL` / `MAGICTEST_FILE_NAMESPACE` 覆盖。

日常执行优先使用根入口 [magicTest/run_tests.py](/home/rangh/codespace/magicTest/run_tests.py)：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset file-smoke
```

本目录下的 `python3 -m unittest ...` 入口保留给单套件调试。

## 客户端接口

Python 客户端 [`file/file/file.py`](file/file/file.py) 实现了与 Go 客户端完全相同的接口：

### Client 类方法

| 方法                                                           | 描述                   | 对应 Go 方法      |
| -------------------------------------------------------------- | ---------------------- | ----------------- |
| `bind_source(source: str)`                                     | 绑定文件来源           | `BindSource`      |
| `unbind_source()`                                              | 解绑文件来源           | `UnbindSource`    |
| `bind_scope(scope: str)`                                       | 绑定文件范围           | `BindScope`       |
| `unbind_scope()`                                               | 解绑文件范围           | `UnbindScope`     |
| `assign_namespace(namespace: str)`                             | 分配命名空间           | `AssignNamespace` |
| `upload_file(file_path: str)`                                  | 上传文件               | `UploadFile`      |
| `upload_stream(dst_path: str, dst_name: str, byte_val: bytes)` | 上传文件流             | `UploadStream`    |
| `download_file(file_token: str, file_path: str)`               | 下载文件               | `DownloadFile`    |
| `view_file(file_token: str)`                                   | 查看文件信息           | `ViewFile`        |
| `update_file(file_id: int, param: dict)`                       | 更新文件信息           | `UpdateFile`      |
| `delete_file(file_id: int)`                                    | 删除文件               | `DeleteFile`      |
| `query_file(file_id: int)`                                     | 查询文件信息           | `QueryFile`       |
| `commit_file(file_id: int, ttl: int)`                          | 提交文件（设置有效期） | `CommitFile`      |
| `filter_file(params: dict)`                                    | 返回兼容文件列表       | `ExplorerFile`    |
| `explorer_file(params: dict)`                                  | 返回完整浏览结果       | `ExplorerFile`    |

### 向后兼容的 File 类

为保持向后兼容，提供了 `File` 包装类，封装了 `Client` 的所有方法。
其中构造参数里的 `path` 会作为默认 `filePath` 参与上传和浏览请求；显式传入请求参数时，以显式参数为准。
顶层 [file.py](file.py) 现在仅保留为兼容 smoke 入口，实际实现统一复用 [file/file/file.py](file/file/file.py)。

## API 参数说明

### 上传文件

1. **file**: [body(必选)] 文件对象
2. **key-name**: [query(必选)] file对应的field名
3. **fileSource**: [query(必选)] 文件的来源，上传者
4. **filePath**: [query(可选)] 文件的存储路径，如何指定路径，则存储在指定的路径下，否则按系统默认规则进行存储
5. **fileScope**: [query(可选)] 文件的所述范围，未传默认为share

### 下载文件

1. **fileToken**: [query(必选)] 文件token
2. **fileScope**: [query(可选)] 文件的所属范围。未传入时只能下载 share 文件；私有文件要求其值与记录中的 scope 一致

### 查看文件

1. **fileToken**: [query(必选)] 文件token
2. **fileSource**: [query(必选)] 文件的来源，需通过 `bind_source()` 提前设置

### 过滤文件清单

1. **fileSource**: [query(可选)] 文件的来源。浏览私有目录时会作为附加过滤条件
2. **fileScope**: [query(可选)] 文件的所属范围。浏览私有目录时会作为附加过滤条件
3. **filePath**: [query(可选)] 浏览路径。未传入时返回 `/static` 根目录结构；`filter_file()` 仅返回其中的 `files`

**响应格式**:

`Client.explorer_file()` 返回下面这类完整响应；`Client.filter_file()` 和兼容包装类 `File.filter_file()` 只返回其中的 `files` 列表。

```json
{
  "error": null,
  "value": {
    "currentPath": "/static",
    "dirs": [...],
    "files": [...],
    "totalDirs": 2,
    "totalFiles": 0
  }
}
```

### 查询文件

1. **id**: [path(必选)] 文件ID（通过URL路径传递）
2. **fileSource**: [query(必选)] 文件的来源，需通过 `bind_source()` 提前设置

### 更新文件 & 删除文件

1. **id**: [path(必选)] 文件ID（通过URL路径传递）
2. **fileSource**: [query(必选)] 文件的来源，只有源始者才能更新或删除文件
3. **其他参数**: [body(可选)] 通过JSON Body传递更新字段（如name, description, ttl, tags等），其中 `ttl` 单位为天

### 提交文件

1. **id**: [path(必选)] 文件ID（通过URL路径传递）
2. **fileSource**: [query(必选)] 文件的来源
3. **TTL**: [body(可选)] 有效期（单位：天），0表示保留服务默认有效期

## 使用示例

### 初始化客户端

```python
from session import session
from cas import cas
from file.file.file import Client

# 创建会话并登录
work_session = session.MagicSession('https://autotest.local.vpc', '')
cas_session = cas.Cas(work_session)
if cas_session.login('administrator', 'administrator'):
    work_session.bind_token(cas_session.get_session_token())

    # 创建文件客户端
    client = Client('https://autotest.local.vpc', work_session)
    client.bind_source('test_source')
    client.bind_scope('test_scope')
```

### 上传文件

```python
# 上传本地文件
result = client.upload_file('/path/to/local/file.txt')
if result:
    file_token = result['token']
    print(f'上传成功，文件token: {file_token}')
```

### 上传文件流

```python
# 上传字节流
content = b"文件内容"
token = client.upload_stream('test/path', 'stream_file.txt', content)
if token:
    print(f'流上传成功，文件token: {token}')
```

### 查看和查询文件

```python
# 通过token查看文件
file_info = client.view_file(file_token)
if file_info:
    file_id = file_info['id']

    # 通过id查询文件
    queried_file = client.query_file(file_id)
```

### 更新文件

```python
update_params = {
    'description': '更新后的描述',
    'tags': ['tag1', 'tag2']
}
updated = client.update_file(file_id, update_params)
```

### 提交文件

```python
# 提交文件，设置30天有效期
committed = client.commit_file(file_id, 30)
```

### 过滤文件

```python
# 浏览文件
file_list = client.filter_file({'path': '/static/private'})
if file_list:
    for file_item in file_list:
        print(f"文件: {file_item['name']}")
```

### 删除文件

```python
deleted = client.delete_file(file_id)
```

## 测试

日常执行：

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset file-smoke
```

只有在定位单一用例问题时，才建议进入 `file/` 目录直接执行 `python3 -m unittest basic_scenario_test -v`。

### 测试覆盖的功能

- ✅ 文件上传 (`test_upload_file`)
- ✅ 公共/私有文件上传 (`test_upload_public_file`, `test_upload_private_file`)
- ✅ 公共/私有文件下载 (`test_download_public_file`, `test_download_private_file`)
- ✅ 文件流上传 (`test_upload_stream`)
- ✅ 大文件上传 (`test_upload_large_file`)
- ✅ 空文件上传 (`test_upload_empty_file`)
- ✅ 文件查看 (`test_view_file`)
- ✅ 文件查询 (`test_query_file`)
- ✅ 分层文件浏览 (`test_file_explorer_hierarchical_browsing`)
- ✅ 多 scope 文件浏览 (`test_file_explorer_with_different_scopes`)
- ✅ 文件更新 (`test_update_file`)
- ✅ 文件删除 (`test_delete_file`)
- ✅ 文件提交 (`test_commit_file`)
- ✅ 完整生命周期 (`test_complete_file_lifecycle`)
- ✅ 文件过滤 (`test_filter_file`)
- ✅ 不存在的文件查询 (`test_query_nonexistent_file`)
- ✅ 不存在的文件删除 (`test_delete_nonexistent_file`)

### 当前回归状态

- 2026-03-22 对 `https://autotest.local.vpc` 的 `python3 -m unittest file.basic_scenario_test -v` 回归中，上传、下载、查看、查询、过滤、浏览和删除相关用例通过
- 同轮剩余失败点为 `test_commit_file`、`test_update_file`、`test_complete_file_lifecycle`
- 根因已在本地 `magicFile` 代码中确认并修复：`updateFile` / `commitFile` 成功返回时未清空 `result.Error`，导致已更新的远端服务仍返回“有 value 但 error 非空”的响应

## 注意事项

1. **认证要求**：所有操作需要先通过 CAS 登录获取认证 token
2. **文件来源**：`fileSource` 是必需参数，需要通过 `bind_source()` 方法提前设置
3. **ID vs Token**：
   - 上传返回 `token`，需要通过 `view_file()` 获取 `id`
   - 使用 `token` 的操作：`view_file()`, `download_file()`
   - 使用 `id` 的操作：`query_file()`, `update_file()`, `delete_file()`, `commit_file()`
4. **响应格式**：所有 API 返回 `{"error": null, "value": ...}` 格式，错误时 `error` 不为 `null`

## 最近更新

基于 Go 客户端接口刷新实现，主要改进：

- 修复了 `fileSource` 参数传递方式（作为查询参数而非 JSON body）
- 修正了 `filter_file()` 响应处理逻辑
- 完善了 `upload_stream()` 的响应解析
- 更新了测试入口与文档说明，使其和 `basic_scenario_test.py`、`file/__main__.py` 当前默认目标一致
- 本地回归默认指向 `autotest.local.vpc`
