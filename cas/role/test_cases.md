# Role 测试用例

## 当前基线

当前 `Role` 的测试语义以 [cas.md](../cas.md) 和 [integration_test_cases.md](../integration_test_cases.md) 为准。

## 已落地场景

### R-TC-001 创建时保留显式状态

- 输入：`status = 1`
- 预期：返回结果保持禁用状态，不被自动刷成启用

### R-TC-002 创建时保留显式 privilege

- 输入：显式 `privilege` 列表
- 预期：返回结果保留 `module` / `uriPath` / `value`

### R-TC-003 更新不丢失角色身份

- 输入：更新 `description`、`status`
- 预期：`id` 不变，更新后查询结果一致

### R-TC-004 namespace 隔离

- 输入：在租户 namespace 内创建 role
- 预期：租户内可见，`panel` 默认查询不直接返回该 role

### R-TC-005 重复创建同名 role 拒绝

- 输入：同 namespace 下再次创建同名 role
- 预期：创建失败，不再走隐式 update / upsert

## 当前实现说明

- `Role` 是功能与操作权限集合。
- `privilege` 当前按显式列表透传和保存。
- 同 namespace 下 role 名称应唯一。
- 当前实现对重复创建会直接拒绝，不再走 update 语义。

## 对应测试

- [role_test.py](role_test.py)
