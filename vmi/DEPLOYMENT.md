# VMI 测试部署后验证说明

本文档面向“服务已部署完成，准备使用 `magicTest/vmi` 进行验证”的场景。目标是用最少步骤完成配置核对、冒烟验证、全量回归和老化测试。

## 1. 前提条件

- 代码目录：`../magicTest/vmi`
- Python 虚拟环境：`../venv`
- 可访问目标服务：本地验证默认 `https://autotest.local.vpc`
- CAS 认证可用
- `test_config.json` 已按当前环境更新

准备：

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
```

如果环境带有代理，建议先按实际目标域名清空，例如：

```bash
export HTTPS_PROXY=
export HTTP_PROXY=
export https_proxy=
export http_proxy=
export NO_PROXY=autotest.local.vpc
export no_proxy=autotest.local.vpc
```

## 2. 核对配置

日常执行优先使用根入口 [../run_tests.py](/home/rangh/codespace/magicTest/run_tests.py)：

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset business-smoke
python3 run_tests.py --preset business-full
python3 run_tests.py --preset load-hotspot
python3 run_tests.py --preset load-aging
```

本目录下的 [run_tests.py](run_tests.py) 只保留给 `VMI` 特有的高级参数和压测调优。

先检查 [test_config.json](test_config.json)：

```bash
cd /home/rangh/codespace/magicTest/vmi
python3 run_tests.py --check-config
```

重点确认：

- `default_server_url`
- `default_tenant`
- `tenant_targets`
- `credentials.username`
- `session.refresh_interval`
- `session.timeout`
- `aging.duration_hours`

本地验证时，`default_server_url` 通常应为 `https://autotest.local.vpc`。

## 3. 部署后冒烟验证

最小验证顺序：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset business-smoke
```

判断标准：

- 配置文件能正常读取
- 核心模块导入正常
- 会话基础设施未损坏
- 多租户配置 helper 未损坏

## 4. 模块回归

部署后建议先跑模块测试，再根据变更范围扩大：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset business-full
```

如果只想先检查关键模块，可直接跑指定用例：

```bash
cd /home/rangh/codespace/magicTest/vmi
python3 -m unittest warehouse.shelf_test order.order_test -v
python3 -m unittest status.status_test partner.partner_test -v
python3 -m unittest store.store_test -v
```

## 5. 全量回归

完整验证建议直接使用根入口：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset business-full
python3 run_tests.py --preset load-aging
```

## 6. 并发与老化

并发回归：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --target vmi-concurrent
```

场景回归：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset business-full
```

老化回归：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset load-aging
```

老化测试会生成：

- `aging_test_report_*.json`
- `aging_test_summary_*.txt`

这些文件通常是运行产物，不属于长期维护文档。

## 7. 多租户验证

如果服务需要验证多租户配置：

```bash
python3 run_tests.py --multi-tenant
python3 test_multi_tenant.py
python3 test_multi_tenant_example.py
```

注意：

- 当前多租户测试主要验证配置和管理器能力
- 默认以 mock 为主，不要求真实多租户服务全部可达

## 8. 故障排查要点

### 8.1 会话失败

优先检查：

- `test_config.json` 中的账号密码
- CAS 服务是否可用
- `session.refresh_interval` 是否合理
- 服务端是否有登录和刷新 token 错误

### 8.2 大量实体创建失败

优先检查：

- `status` 等基础数据是否已初始化
- 关联实体定义是否已完成部署
- 当前环境是否残留脏数据或重复安装数据
- 服务端日志中是否出现 ORM 校验失败或关系字段错误

### 8.3 偶发超时

当前真实环境回归中，可能偶发单次 `count` 或查询超时。判断时以“整轮测试是否失败”为主，不要把单次抖动直接当作功能回归。

### 8.4 观察类告警

以下日志当前可能出现，但不一定代表回归失败：

- 允许重复 `credit report`
- 允许重复 `productInfo.sku`
- 创建或更新响应未返回完整关联字段
- 更新响应未返回 `modifyTime`

## 9. 推荐执行顺序

服务刚部署：

```bash
python3 run_tests.py --check-config
python3 run_tests.py --quick
python3 run_tests.py --module
```

基础能力改动后：

```bash
python3 run_tests.py --validation
python3 run_tests.py --multi-tenant
python3 run_tests.py --module
```

上线前：

```bash
python3 run_tests.py --all
python3 run_tests.py --aging 30
```
