# PLC 轮询读取并刷新 Redis（经 MQTT 遥测）实施计划

**Goal**
- 在现有 FastAPI 网关进程内新增后台轮询任务：按设备配置通过 Modbus TCP 读取 PLC 状态/遥测，发布到 `telemetry/plc/{device_code}`，由现有 [TelemetryService](file:///workspace/middleware/app/services/telemetry_service.py) 负责写入 Redis（最新值）与 MySQL（历史）。

**Success Criteria**
- 配置了轮询的设备在 Redis `telemetry:{device_code}` 中始终能读到最新状态（TTL 持续刷新）。
- 网关启动后无需额外服务即可开始轮询；网关退出时轮询协程可被优雅取消。
- 单设备轮询失败不会影响其他设备；失败会产生日志，且可选发布事件到 `event/plc/{device_code}`。
- `pytest` 全量通过。

---

## 1. Current State Analysis（基于仓库现状）

**现有数据链路**
- 网关入口在 [main.py](file:///workspace/middleware/app/main.py#L1-L31)，启动时订阅：
  - `telemetry/plc/+` → [TelemetryService.process_telemetry](file:///workspace/middleware/app/services/telemetry_service.py#L19-L64)
  - `event/plc/+` → [TelemetryService.process_event](file:///workspace/middleware/app/services/telemetry_service.py#L66-L113)
  - `iot/v1/command/device/+` → [CommandService.process_command](file:///workspace/middleware/app/services/command_service.py#L18-L45)
- TelemetryService 收到遥测后写：
  - Redis：`telemetry:{device_id}`（TTL 300s）
  - MySQL：`telemetry_history`

**现有 Modbus 能力**
- [ModbusService](file:///workspace/middleware/app/services/modbus_service.py) 当前仅支持写入（功能码 `0x05/0x06/0x10`），没有读寄存器/线圈能力。

**现有配置/数据模型**
- 设备动作（启动/关停/获取状态等）存于 `device_action.action_command_params` JSON 字段（表结构见 [init.sql](file:///workspace/middleware/app/init.sql#L21-L36)）。
- API 文档示例中，“获取状态”动作参数包含 `function_code: 0x03`（保持寄存器读取）等字段（见 [API文档.md](file:///workspace/API%E6%96%87%E6%A1%A3.md#L164-L176)）。
- 由于不同设备动作名不一致，轮询不能依赖 `action_name` 过滤，需要基于 `action_command_params` 的显式标记来识别“轮询源”。

---

## 2. Proposed Changes（方案与落点）

### 2.1 数据约定：用 action_command_params 标记“轮询动作”

在 `device_action.action_command_params` 增加轮询配置段（不新增表、不改列）：

```json
{
  "polling": {
    "enabled": true,
    "interval_s": 2
  },
  "modbus": {
    "host": "192.168.1.10",
    "port": 502,
    "unit_id": 1,
    "reads": [
      {
        "function_code": "0x03",
        "offset": 2,
        "count": 2,
        "key": "status_regs"
      }
    ]
  },
  "description": "轮询设备状态"
}
```

兼容性策略（避免破坏既有写入命令）：
- 写入命令仍沿用现有 `params` 结构（`host/port/unit_id/function_code/offset/data`）供 [CommandService](file:///workspace/middleware/app/services/command_service.py) 使用。
- 轮询动作优先使用 `modbus.reads[]`；若未来需要兼容旧字段，可支持当 `modbus` 缺失时回退读取 `function_code/offset/data`，并将 `data` 解释为 `count`（仅对读功能码生效）。

### 2.2 新增后台轮询服务（gateway 内置）

新增一个服务模块，职责单一：加载轮询配置 → 执行 Modbus 读 → 发布 MQTT 遥测。

**Create**
- `middleware/app/services/plc_polling_service.py`

**核心职责**
- 周期性从 MySQL 拉取 `polling.enabled=true` 的 `device_action` 记录（并拿到对应设备的 `device_code`）。
- 按 `interval_s` 调度轮询（默认 2s；也可仅支持全局间隔以简化）。
- 对每个轮询动作执行 Modbus 读取（下节新增读能力）。
- 将读取结果组装为 JSON 并发布到 `telemetry/plc/{device_code}`，复用 TelemetryService 的 Redis/MySQL 落地。

**并发与限流（适配“少量设备 + 1~5 秒”）**
- 使用 `asyncio.Semaphore` 做全局并发上限（例如 `POLL_MAX_INFLIGHT=10`）。
- 每台设备轮询任务互不影响，单设备读超时/失败只影响该设备。
- 每次读取设置严格超时（例如 1s），避免 Modbus 端异常导致轮询堆积。

**错误与降级**
- 连续失败计数（内存或 Redis）达到阈值后：
  - 仍持续重试，但降低日志频率（例如每 N 次失败输出一次）。
  - 可选：发布 `event/plc/{device_code}` 事件（由 TelemetryService.process_event 写 Redis）。

### 2.3 补齐 Modbus 读取能力

扩展现有 ModbusService，新增读 API：

**Modify**
- `middleware/app/services/modbus_service.py`

**新增能力**
- `execute_read(params) -> dict[str, Any]`（或返回更贴近 pymodbus 的结果，再由 polling service 解析）
- 支持功能码：
  - `0x01` read_coils
  - `0x02` read_discrete_inputs
  - `0x03` read_holding_registers
  - `0x04` read_input_registers
- 参数字段建议标准化：
  - `host/port/unit_id/function_code/offset/count`
- 重试策略与写入保持一致（3 次重试 + 短暂 sleep），并支持单次请求超时。

### 2.4 应用装配：把 Poller 挂到 lifespan

**Modify**
- `middleware/app/main.py`

**启动顺序建议**
- 注册 MQTT handlers（现有）
- `await mqtt_client.connect()`（现有）
- 启动 `PLCPollingService.start()`，持有 task 引用

**退出顺序建议**
- 先停止轮询 task（cancel + await）
- 再 `await mqtt_client.disconnect()`（现有）

### 2.5 配置项与 docker-compose

**Modify**
- `middleware/app/core/config.py`
- `docker-compose.yml`

建议新增环境变量（均给默认值，避免破坏现有部署）：
- `PLC_POLL_ENABLED`（默认 `true`）
- `PLC_POLL_DEFAULT_INTERVAL_S`（默认 `2`）
- `PLC_POLL_MAX_INFLIGHT`（默认 `10`）
- `PLC_POLL_TIMEOUT_S`（默认 `1`）
- `PLC_POLL_DB_REFRESH_S`（默认 `30`，用于定期重新加载 DB 配置，避免每秒打 DB）

### 2.6 测试（最小但有效）

**Create**
- `middleware/tests/test_plc_polling_service.py`

覆盖点：
- 当 DB 返回一条 `polling.enabled=true` 的 action 时，会调用 Modbus 读并通过 `mqtt_client.publish("telemetry/plc/<code>", ...)` 发布。
- 当 Modbus 读抛异常时，不会让轮询主循环崩溃，并会进入失败分支（可断言 publish event 或日志调用）。

**Modify（如需）**
- `middleware/tests/test_command_service.py`（仅当 ModbusService 扩展导致接口变化时，确保兼容写入路径）

---

## 3. Assumptions & Decisions（已确认/默认）

- 部署方式：轮询集成在 gateway 进程内（用户已确认）。
- Redis 刷新链路：轮询发布 MQTT 遥测到 `telemetry/plc/{device_code}`（用户已确认），由 TelemetryService 统一写入 Redis/MySQL。
- 轮询配置来源：使用 `device_action.action_command_params`，并通过 JSON 内 `polling.enabled` 标记哪些动作用于轮询（因 action_name 每设备不同）。
- 轮询规模：少量设备、1~5 秒级（用户已确认），因此优先选择实现简单、可维护的并发/调度方式。

---

## 4. Verification（验收与自测步骤）

**单元测试**
- 在 `middleware/` 目录运行：
  - `pytest -q`

**本地/容器联调（建议）**
- `docker compose up -d --build`
- 用 HTTP API 创建（或更新）某个设备的轮询动作，使其 `action_command_params.polling.enabled=true` 且包含正确的 Modbus 连接与 reads 配置
- 观察 MQTT 是否持续发布：
  - `mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t 'telemetry/plc/+' -v`
- 观察 Redis 是否持续刷新（示例 key）：
  - `redis-cli GET telemetry:<device_code>`
  - 期望：JSON 内 `timestamp` 持续变化，TTL 接近 300s 且不会自然过期

