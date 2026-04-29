# MQTT 订阅驱动 Modbus TCP 控制 PLC 实施计划

## Summary
- 目标：在 `middleware` 中实现“订阅新 MQTT 指令主题 -> 解析参数 -> 执行 Modbus TCP 写入 -> 发布新回执主题”的完整闭环。
- 成功标准：
  - 仅订阅 `iot/v1/command/device/+`。
  - 指令按 `params.function_code/offset/data` 直透执行 Modbus 写入。
  - PLC 连接参数由消息体提供（如 host/port/unit_id）。
  - 写入失败固定重试 3 次后返回 `failed` 回执。
  - HTTP `/api/v1/commands/send` 同步使用新字段与新主题。
  - 提供单元测试与示例消息用于验收。

## Current State Analysis
- 当前启动订阅旧主题：`telemetry/plc/+`、`event/plc/+`、`command/plc/+`（`middleware/app/main.py`）。
- 当前命令服务仅做消息解析和 Redis 记录，不执行 PLC 控制（`middleware/app/services/command_service.py`）。
- 当前回执发布到旧事件主题 `event/plc/{device_id}`，无新回执主题。
- 依赖中无 Modbus 客户端库（`middleware/requirements.txt`）。
- 文档已定义新主题与新字段：`iot/v1/command/device/{device_code}`、`command_type`、`iot/v1/command-result/device/{device_code}`（`API文档.md`）。

## Proposed Changes
### 1) `middleware/requirements.txt`
- What：
  - 增加 Modbus 依赖（`pymodbus`，选择异步客户端能力）。
- Why：
  - 提供标准 Modbus TCP 读写 API，避免自实现协议栈。
- How：
  - 追加明确版本号，保持与现有 Python 运行环境兼容。

### 2) `middleware/app/main.py`
- What：
  - 将命令订阅从 `command/plc/+` 切换为 `iot/v1/command/device/+`。
- Why：
  - 对齐 API 文档的新主题规范。
- How：
  - 保留 telemetry/event 现有订阅不变，仅替换命令订阅 topic。

### 3) 新增 `middleware/app/services/modbus_service.py`
- What：
  - 封装 Modbus TCP 执行逻辑，支持固定重试 3 次。
- Why：
  - 将协议执行与业务处理解耦，方便测试与扩展。
- How：
  - 提供统一入口（如 `execute_write(params)`）：
    - 从参数读取连接信息（`host`, `port`, `unit_id`）与写入参数（`function_code`, `offset`, `data`）。
    - 支持至少 `0x05`（写单线圈）、`0x06`（写单寄存器）、`0x10`（写多寄存器，`data` 为数组）三种常见写入。
    - 每次失败记录错误并重试，最多 3 次；最终抛出可读异常。
  - 对 `function_code` 做白名单校验，非法值直接失败。

### 4) `middleware/app/services/command_service.py`
- What：
  - 适配新主题与新字段，接入 Modbus 执行，发布新回执主题。
- Why：
  - 实现“MQTT 命令 -> PLC 控制 -> MQTT 回执”的核心链路。
- How：
  - `process_command`：
    - 仅解析 `iot/v1/command/device/{device_code}` 主题。
    - 使用 `command_type`（兼容缺省处理），并保留 `command_id/batch_id/device_code/ts/source`。
  - `_execute_command`：
    - 调用 `ModbusService` 执行写入。
    - 成功发布 `iot/v1/command-result/device/{device_code}`，`result_code=EXECUTED`。
    - 失败发布同主题，`result_code=FAILED` 且包含错误信息。
    - Redis 中保存 latest result（键可沿用现有模式，值结构升级为新回执字段）。
  - `send_command`：
    - HTTP 入参沿用 `command_type + params`，发布到 `iot/v1/command/device/{device_code}`。
    - 自动补充 `command_id`、`ts`，`batch_id/source` 可选。

### 5) `middleware/app/api/commands.py`
- What：
  - 请求模型补齐新字段并保持最小兼容。
- Why：
  - 让 HTTP 下发与 MQTT 文档格式一致。
- How：
  - 在 `SendCommandRequest` 增加可选字段：`command_id`、`batch_id`、`source`、`ts`。
  - 调整 `send_command` 调用签名，传递完整负载到服务层。

### 6) 测试（新增/修改）
- What：
  - 为命令执行链路补充单元测试。
- Why：
  - 覆盖高风险逻辑：主题解析、Modbus 调用、重试与回执。
- How：
  - 新增 `middleware/tests/test_command_service.py`：
    - 新主题解析正确，旧主题不触发执行。
    - 成功路径：调用 Modbus 一次，发布 `EXECUTED` 回执。
    - 失败路径：重试 3 次后发布 `FAILED` 回执。
    - `send_command` 发布到新主题且字段符合规范。
  - 对外部依赖（MQTT/Redis/Modbus）使用 mock，保证测试可离线运行。

## Assumptions & Decisions
- 决策：仅支持新命令主题与新回执主题，不做旧主题兼容。
- 决策：`command_type` 仅用于业务语义标识，实际控制行为由 `params` 直透决定。
- 决策：连接参数必须在命令 `params` 中提供，缺失即失败回执。
- 决策：失败重试固定 3 次，不引入指数退避。
- 假设：运行环境允许引入 `pymodbus` 且版本与 Python 3.10 兼容。

## Verification Steps
1. 安装依赖并运行测试：`pytest -q`（至少包含新增命令服务测试）。
2. 本地启动服务后发布一条合法命令到 `iot/v1/command/device/DEV-001`，确认：
   - 触发 Modbus 写入；
   - 收到 `iot/v1/command-result/device/DEV-001` 的 `EXECUTED` 回执。
3. 发布一条非法/缺参命令，确认：
   - 发生 3 次重试；
   - 收到 `FAILED` 回执并含错误原因。
4. 调用 `POST /api/v1/commands/send`，确认消息发布到新主题且字段结构符合文档。
