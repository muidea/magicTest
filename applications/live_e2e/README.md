# 双应用联合 E2E 验证

[run_dual_apps_e2e.py](~/codespace/magicTest/applications/live_e2e/run_dual_apps_e2e.py) 提供面向全新部署环境的两大模拟应用联合校验与执行入口，全部模型与正式发行包从[模型应用资产目录](~/dataspace/magicPlatform/apps/models/README.md)（或 `--platform-root` / `MAGICPLATFORM_ROOT`）解析，凭据仅从本机 `0600` 密钥文件或受管环境变量读取，报告默认写入 `~/codespace/magicTest/reports/applications/` 且拒绝覆盖既有输出。

## 1. 离线发布前核对（`--dry-run`）

校验两套模型定义、正式包 `SHA256SUMS` 与生成计划一致性，不连接任何在线服务：

```bash
python3 -B ~/codespace/magicTest/applications/live_e2e/run_dual_apps_e2e.py --dry-run
```

## 2. 新环境部署后在线验证

1. 在新部署环境的 Panel 分别导入并安装设备管理官方包[设备管理正式包](~/dataspace/magicPlatform/apps/models/device-management/package/package.zip)与棋牌室预订官方包[棋牌室预订正式包](~/dataspace/magicPlatform/apps/models/chess-room-booking/package/package.zip)，按各自设计配置对应 Gateway 订阅与 CAS 角色绑定。
2. 先通过[设备管理模拟器](~/codespace/magicTest/applications/device-management/tooling/simulator.py)初始化只写 ApiKey 的运行配置，并按本机 `0600` 文件准备棋牌室 ApiKey 与 Apps Bearer token。
3. 执行联合 Live E2E：

```bash
python3 -B ~/codespace/magicTest/applications/live_e2e/run_dual_apps_e2e.py \
  --dm-config ~/.local/state/device-management/live-replay/config.json \
  --dm-command replay \
  --crb-mode replay \
  --crb-state-dir ~/.local/state/chess-room-booking/live-replay \
  --crb-api-key-file ~/.config/chess-room-booking/api-key \
  --crb-action-token-file ~/.config/chess-room-booking/action-token \
  --ca-file ~/dataspace/magicPlatform/services/secret/tls/tls.crt --trust-leaf
```

## 3. 相关说明

- [设备管理验证套件](~/codespace/magicTest/applications/device-management/README.md)
- [棋牌室预订验证套件](~/codespace/magicTest/applications/chess-room-booking/README.md)
- [测试目录与运行目录说明](~/codespace/magicTest/reports/README.md)

[返回模拟应用目录](~/codespace/magicTest/applications/README.md)
