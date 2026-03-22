# platform

`magicTest/platform` 用于回归 `magicBase` 的核心平台接口。当前默认目标环境是 `https://autotest.local.vpc/api/v1`，可通过 `MAGICTEST_PLATFORM_BASE_URL` / `MAGICTEST_PLATFORM_NAMESPACE` 覆盖。

## 当前入口

- `application/application_test.py`
  - 当前第一组正式 `unittest` 用例入口
  - 覆盖 create / query / update / filter / delete 以及部分边界场景
- `block/block_test.py`
  - 当前第二个成体系的 `unittest` 用例入口
  - 覆盖 create / query / update / filter / destroy 及不存在对象场景
- `entity/entity_test.py`
  - 当前第三个成体系的 `unittest` 用例入口
  - 覆盖 create / search / query / update / filter / enable / disable / destroy 及不存在对象场景
- `value/value_test.py`
  - 当前第四个成体系的 `unittest` 用例入口
  - 覆盖 insert / query / update / filter / delete 及不存在对象场景
- `application/__main__.py`
- `block/__main__.py`
- `entity/__main__.py`
- `value/__main__.py`
  - 以上入口当前主要作为 smoke 脚本，适合人工联调，不等同于成体系回归

## 推荐命令

```bash
cd ../magicTest/platform
source ../venv/bin/activate
HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= \
NO_PROXY=autotest.local.vpc no_proxy=autotest.local.vpc \
PYTHONPATH=..:.:$PYTHONPATH \
python3 -m unittest application.application_test -v
python3 -m unittest block.block_test -v
python3 -m unittest entity.entity_test -v
python3 -m unittest value.value_test -v
```

## 当前一致性约定

- 平台 smoke 入口和 `application_test.py` 默认都指向 `MAGICTEST_PLATFORM_BASE_URL`
- 默认 namespace 统一来自 `MAGICTEST_PLATFORM_NAMESPACE`
- 若后续补 `block/entity/value` 的正式回归，优先继续沿用 `unittest` 结构，而不是再扩散独立脚本入口
- 由于目录名为 `platform`，运行 `unittest` 时不要使用 `platform.*` 模块路径，避免和 Python 标准库 `platform` 冲突

## 已知现状

- `access_log` / `operation_log` / `totalizator` 目前仍主要依赖 smoke 脚本，正式 `unittest` 仍待补齐
