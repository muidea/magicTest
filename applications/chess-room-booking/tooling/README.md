# 棋牌室定义与模拟工具

需要 Python 3.10+；包工具另需 Go 和工作区 Runner 默认 vendor。包／样例工具只做本地检查，模拟工具的 run 明确写入专用验证实例，verify 只读。全部工具不执行真实预约命令，不自动清理，不直接创建派生目标。

## 标准模型包

```bash
python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/package_tool.py check
python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/package_tool.py build \
  --output-dir /tmp/chess-room-booking-package-next
python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/package_tool.py inspect \
  --package ~/dataspace/magicPlatform/apps/models/chess-room-booking/package/package.zip
```

官方 Runner codec 通过 Go overlay 执行 Build／Parse／ParseUnpacked、确定性、约束／页面／功能块检查和公共 ORM Schema 预检；无数据库连接、DDL 执行或正式发布证明。生成 ZIP 与未压缩包同字节，不覆盖已有输出。修改定义后同步版本、profile、pages、blocks，再输出全新目录；不要手改 ZIP。

## plan／run／verify

[simulation_tool.py](~/codespace/magicTest/applications/chess-room-booking/tooling/simulation_tool.py)只使用开放服务 ApiKey 与受管实体动作会话。默认服务为 `https://panel.local.vpc/api/v1/gateway/services/chess_room_booking_simulation`，先由平台安装最新正式包[package.zip](~/dataspace/magicPlatform/apps/models/chess-room-booking/package/package.zip)并配置独立空实例、订阅及 CAS 角色绑定。

```bash
# 离线固定回放；已有文件拒绝覆盖
python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/simulation_tool.py plan \
  --run-id replay-next --anchor-utc 2026-11-01T00:00:00Z \
  --output /tmp/simulation-next.json

# 密钥文件先以本机 0600 保存；以下路径仅为示例，不含密钥
python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/simulation_tool.py run \
  --api-key-file ~/.config/chess-room-booking/api-key \
  --state-dir ~/.local/state/chess-room-booking/replay \
  --ca-file ~/dataspace/magicPlatform/services/secret/tls/tls.crt --trust-leaf

python3 ~/codespace/magicTest/applications/chess-room-booking/tooling/simulation_tool.py verify \
  --api-key-file ~/.config/chess-room-booking/api-key \
  --state-dir ~/.local/state/chess-room-booking/replay \
  --ca-file ~/dataspace/magicPlatform/services/secret/tls/tls.crt --trust-leaf --wait-seconds 60
```

参考[当前模拟计划](~/codespace/magicTest/applications/chess-room-booking/fixtures/simulation-r5-plan.json)。新计划运行时加 `--plan`，run 和 verify 使用同一计划及 state-dir。也可用受管环境变量 `CHESS_SIM_API_KEY`；不把密钥作为命令行值。系统已信任服务证书时可省略 ca-file；明确把本机叶证书作为信任锚时增加 `--trust-leaf`，仍校验主机名，拒绝重定向。

run 首次完整查询 13 实体并要求全空，再依次录入 43 条直接输入。每次发送前原子保存 intent，只有可靠回执的精确 ID 及独立 get 字段一致后继续依赖；首次回执绑定实例／工件／代际，后续不符停止。日志目录 0700、文件 0600，flock 防并发，绑定服务 URL、计划和定义摘要。凭据与响应正文不写日志或输出。

Gateway 当前没有公开的通用服务元数据发现接口；写前只读预检能验证 13 项 query 及空数据，不能宣称已在写前核实工件、全部 get/create 或 CAS 最小角色。服务归属、能力及角色由平台正式配置和回读验收，工具从首次可靠回执绑定执行身份，不新增发现 API 或管理凭据。

写只发送一次。transport、无效回执或进程中断后结果未知且没有已确认 ID 时，停止并由平台 owner 核对原操作，禁止重发或按同名记录猜成功；不能删日志重新开始。已取得可靠 ID 但回读失败时，只读该 ID 核对后续进。没有远端来源取消／任务恢复协议，也没有自动回滚删除。

verify 独立 get 所有直接记录、完整分页并核对整个实例精确身份集合；派生按宿主 deploymentId＋source.sampleKey 的正式摘要找到对应目标，再 get 校验字段／引用／UTC 毫秒。43 直接＋18 派生＝61 条；两目标缺任一则失败。`taskReceiptsVerified=false`，数据回读不冒充平台任务 completed；后台两任务、撤权、并发和页面仍由 Live 验收确认。默认 QPS 2、每次命令最多 500 请求／单实体最多 1000 行，verify 全实例最多 1000 行，等待最多 60 秒；读取也不自动重试。

## 离线样例与反例

[fixture_tool.py](~/codespace/magicTest/applications/chess-room-booking/tooling/fixture_tool.py)的 generate／check／plan 使用当前 13 实体正式定义生成并校验 52 条业务记录基线；simulation-plan 输出 replay／seed／live-stream 可执行计划。样例含固定状态回放，不代表当前实时营业状态或已批准业务政策。[admission_contract.py](~/codespace/magicTest/applications/chess-room-booking/tooling/admission_contract.py)按已复核[规则快照](~/codespace/magicTest/applications/chess-room-booking/fixtures/admission-contract-r4.json)检查声明漂移和样例关系／时间条件，仅为离线 oracle，不是 Base 数据库执行证明。

```bash
python3 -B -m unittest discover -s ~/codespace/magicTest/applications/chess-room-booking/tooling -p 'test_*.py' -v
python3 -B ~/dataspace/magicPlatform/tools/check_documentation_layout.py
```

早期不可执行 R3 计划保留于原资料仓 Git 历史。新的可执行标识表示工具已有实现，不能解读为服务已经配置、Live 通过或可以绕过部署门槛。

[交叉验证夹具](~/codespace/magicTest/applications/chess-room-booking/tooling/testdata/write-identity.json)由 Python 测试和正式 Go 合同共同读取，校验 32 位小写十六进制部署／操作身份宽度与 64 位工件哈希。

[返回棋牌室预订](~/codespace/magicTest/applications/chess-room-booking/README.md)
