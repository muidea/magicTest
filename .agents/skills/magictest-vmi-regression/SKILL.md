---
name: magictest-vmi-regression
description: 用于处理 magicTest/vmi 的全量回归、负向校验噪声清理、定义对齐和远端服务验证。涉及 unittest discover、autotest.local.vpc、VMI 断言和清理噪声时使用。
version: 1.0.0
---

# magicTest VMI Regression

这个 skill 处理 `magicTest/vmi` 的远端回归执行和测试噪声治理。

## 先读这些文件

- `session/common.py`
- `session/session.py`
- `vmi/sdk/base.py`
- `vmi/test_vmi_base.py`
- `../docs/vmi-definition-regression-playbook.md`

## 当前稳定规则

- `delete/query nonexistent` 属于常见负向场景，不应在公共层刷 `error`
- 预期中的非法 `create/update` 校验失败，应尽量降成低噪声输出
- 真实定义以 `magicOrm/test/vmi -> vmi.zip -> 数据库定义 -> 测试断言` 顺序核对

## 推荐验证

```bash
source /home/rangh/codespace/venv/bin/activate
HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= NO_PROXY=autotest.local.vpc no_proxy=autotest.local.vpc \
python3 -m unittest discover -s . -p '*_test.py' -v
```
