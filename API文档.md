# IPC 边缘网关 API 文档

## 📋 概述

**项目名称**: IPC 边缘网关 (IPC Gateway)\
**技术栈**: FastAPI + SQLAlchemy + Redis + MySQL + MQTT\
**服务端口**: `8000`\
**API 基础路径**: `http://192.168.1.136:8000`\
**认证方式**: 通过 `API_TOKEN` 请求头（当前值：`changeme`）

***

## 🔧 健康检查

### `GET /healthz`

检查服务 health 状态（包括 Redis 连接）

**响应示例**:

```json
{
  "status": "ok",
  "redis": "connected"
}
```

***

## 📡 设备型号管理 (Device Model)

### `GET /api/v1/device-models`

获取所有设备型号列表（已过滤逻辑删除）

### `POST /api/v1/device-models`

创建新的设备型号

**请求体**:

```json
{
  "model_name": "PLC-S7-1200",
  "model_code": "SIEMENS-001",
  "description": "西门子 S7-1200 系列",
  "specifications": {"ports": 14}
}
```

### `GET /api/v1/device-models/{model_id}`

获取指定设备型号详情

### `PATCH /api/v1/device-models/{model_id}`

更新设备型号信息

### `DELETE /api/v1/device-models/{model_id}`

逻辑删除设备型号

***

## 📡 设备实例管理 (Device Instance)

### `GET /api/v1/devices` 🔴 (前端补充设计了新查询参数)

分页获取所有活跃设备列表（已过滤逻辑删除）

**查询参数**:

- `page`: 页码 (默认 1，最小 1)
- `size`: 每页数量 (默认 15，最小 1，最大 200)
- `keyword`: 🔴 (新增) 关键字，按设备名称 (`device_name`) 或设备编号 (`device_code`) 模糊过滤 (可选)
- `device_category`: 🔴 (新增) 设备类别，按类别模糊筛选 (可选)

**响应结构**:

```json
{
  "items": [
    {
      "id": 1,
      "device_model_id": 1,
      "device_model_name": "输送设备",
      "device_code": "DEV-001",
      "device_name": "产线1号控制器",
      "device_category": "输送设备",
      "production_line": "Line-A",
      "location": "A-01",
      "device_status": 2,
      "device_data": {"is_variable_frequency": true, "frequency": 45},
      "communication_protocol": "modbus-tcp",
      "created_at": "2026-04-22T10:00:00",
      "updated_at": "2026-04-22T10:00:00"
    }
  ],
  "total": 36,
  "page": 1,
  "size": 15
}
```

### `POST /api/v1/devices`

注册新设备实例

**请求体**:

```json
{
  "device_model_id": 1,
  "device_code": "DEV-001",
  "device_name": "产线1号控制器",
  "production_line": "Line-A",
  "communication_protocol": "modbus-tcp"
}
```

**说明**:

- `device_code` 必须唯一（仅在未删除数据中校验）
- `device_model_id` 必须指向存在且未删除的设备型号
- 响应会包含 `device_model_name`

### `GET /api/v1/devices/{device_id}`

获取指定设备实例详情

### `PATCH /api/v1/devices/{device_id}`

更新设备实例信息

**说明**:

- 当更新 `device_code` 时，会进行唯一性冲突校验
- 响应会包含 `device_model_name`

### `DELETE /api/v1/devices/{device_id}`

逻辑删除设备实例

***

## 🎛️ 设备行为事件管理 (Device Action)

> 远程控制界面的“行为事件”对应 `device_action` 表数据，按 `device_instance_id` 维护。

### `GET /api/v1/device-actions`

按设备查询行为事件列表

**查询参数**:

- `device_instance_id`: 设备实例 ID（必填，最小 1）

### `POST /api/v1/device-actions`

新增行为事件

**请求体**:

```json
{
  "device_instance_id": 1,
  "action_name": "获取状态",
  "action_command_params": {
    "point_address": 0,
    "function_code": "0x03",
    "offset": 2,
    "data": 2,
    "description": "获取设备当前状态"
  }
}
```

### `GET /api/v1/device-actions/{action_id}`

获取行为事件详情

### `PATCH /api/v1/device-actions/{action_id}`

更新行为事件（局部更新）

### `DELETE /api/v1/device-actions/{action_id}`

逻辑删除行为事件

***

## 📊 遥测数据 (Telemetry)

### `GET /api/v1/telemetry/latest/{device_id}`

获取指定设备的最新遥测数据（来自 Redis 缓存）

### `GET /api/v1/telemetry/history/{device_id}`

获取指定设备的历史遥测记录（来自 MySQL）

**查询参数**:

- `start_time`: 开始时间 (ISO格式)
- `end_time`: 结束时间 (ISO格式)
- `limit`: 返回数量限制 (默认 100)

***

## 🔔 事件管理 (Events)

### `GET /api/v1/telemetry/events/{device_id}/latest`

获取设备的最新事件

### `GET /api/v1/telemetry/events/{device_id}/history`

获取设备的事件历史记录

***

## ⚙️ 工作流管理 (Workflow)

### `GET /api/v1/workflows`

获取所有活跃工作流列表

**查询参数**:

- `page`: 页码 (默认 1)
- `size`: 每页数量 (默认 10)

### `POST /api/v1/workflows`

创建新工作流

**请求体**:

```json
{
  "workflow_name": "数据采集流程",
  "workflow_type": "COLLECT",
  "info": "这里是流程说明",
  "enable_or_not": 1,
  "workflow_params": {"is_draft": false},
  "workflow_detail": {
    "version": 2,
    "canvas": {
      "version": 1,
      "sequence": []
    },
    "execution": {
      "nodes": [],
      "root_sequence": [],
      "meta": {"node_count": 0}
    }
  }
}
```

### `GET /api/v1/workflows/{id}`

获取工作流详情

### `PATCH /api/v1/workflows/{id}`

更新工作流

### `DELETE /api/v1/workflows/{id}`

逻辑删除工作流

***

## 🧪 工艺管理 (Production Process)

### `GET /api/v1/production-processes`

分页获取工艺列表

**查询参数**:

- `page`: 页码 (默认 1，最小 1)
- `size`: 每页数量 (默认 10，最小 1，最大 200)
- `keyword`: 关键字，按工艺名称 (`process_name`) 模糊过滤 (可选)
- `enable_or_not`: 是否启用 (可选，true 启用 / false 禁用)

### `POST /api/v1/production-processes`

新增工艺

**请求体**:

```json
{
  "startup_process": 1,
  "end_the_process": 2,
  "process_name": "装配工艺",
  "process_description": "装配工艺说明",
  "enable_or_not": true
}
```

### `GET /api/v1/production-processes/{process_id}`

获取工艺详情

### `PATCH /api/v1/production-processes/{process_id}`

更新工艺（局部更新）

### `DELETE /api/v1/production-processes/{process_id}`

删除工艺（逻辑删除，`if_delete=1`）

***

## ⌨️ 命令控制 (Commands)

### HTTP API 下发指令

#### `POST /api/v1/commands/send`

通过 HTTP 代理向设备发送控制指令（后台会转发至 MQTT）

**请求体**:

```json
{
  "device_id": "DEV-001",
  "command_type": "START",
  "params": {"speed": 100}
}
```

### MQTT 状态订阅

#### 状态主题: `iot/v1/status/device/{device_code}`

设备实时状态统一通过该主题发布。

**订阅示例**:

- 订阅全部设备状态：`iot/v1/status/device/+`
- 订阅单设备状态：`iot/v1/status/device/DEV-001`

**消息体 (JSON)**:

```json
{
  "device_code": "DEV-001",
  "ts": "2026-04-23T10:00:00Z",
  "status": {
    "device_status": 2,
    "online": true,
    "alarm": false
  },
  "telemetry": {
    "temperature": 36.5,
    "pressure": 0.8
  },
  "source": {
    "client_id": "gateway-main",
    "protocol": "modbus-tcp"
  },
  "plc": {
    "plc_code": "PLC-01"
  }
}
```

**说明**:

- 状态主题使用 `retain = true`，新订阅者可立即获取最近一次状态。
- `device_status` 与 `device_instance.device_status` 枚举保持一致。
- 设备主标识统一使用 `device_code`。

### MQTT 直接下发指令

#### 主题: `iot/v1/command/device/{device_code}`

直接通过 MQTT 消息总线下发指令（推荐用于实时控制）

**消息体 (JSON)**:

```json
{
  "command_id": "cmd-20260423-0001",
  "batch_id": "batch-20260423-01",
  "device_code": "DEV-001",
  "action_name": "启动",
  "command_type": "START",
  "params": {
    "point_address": 0,
    "function_code": "0x06",
    "offset": 2,
    "data": 1
  },
  "ts": "2026-04-23T10:00:00Z",
  "source": {
    "client_id": "hmi-terminal-01"
  }
}
```

**说明**:

- `command_type` 是统一字段名，不再使用旧字段 `type`。
- 批量下发部分设备时，对每个目标设备单独发布到各自主题。
- 同批次命令共享 `batch_id`，每条命令拥有独立 `command_id`。
- 命令主题使用 `retain = false`。

**批量下发示例**:

若要向 `DEV-001`、`DEV-003`、`DEV-008` 下发同一命令，则分别发布到：

- `iot/v1/command/device/DEV-001`
- `iot/v1/command/device/DEV-003`
- `iot/v1/command/device/DEV-008`

### 获取执行结果

#### `GET /api/v1/commands/result/{device_id}`

通过 HTTP API 获取指令执行的最终结果

#### MQTT 主题: `iot/v1/command-result/device/{device_code}`

通过 MQTT 订阅指令执行结果回执

**消息体 (JSON)**:

```json
{
  "command_id": "cmd-20260423-0001",
  "batch_id": "batch-20260423-01",
  "device_code": "DEV-001",
  "result_code": "EXECUTED",
  "result_message": "write success",
  "stage": "executed",
  "ts": "2026-04-23T10:00:02Z",
  "source": {
    "client_id": "gateway-main"
  }
}
```

**说明**:

- `stage` 推荐取值：`received`、`executing`、`executed`、`failed`。
- HMI 订阅全部命令回执：`iot/v1/command-result/device/+`
- HMI 订阅单设备回执：`iot/v1/command-result/device/DEV-001`
- 命令回执主题使用 `retain = false`。

### 历史主题兼容

以下旧主题仅保留兼容说明，后续应逐步下线：

- `telemetry/plc/{device_id}`
- `command/plc/{device_id}`
- `event/plc/{device_id}`
