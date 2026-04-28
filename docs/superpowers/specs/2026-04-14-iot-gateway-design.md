# 物联网边缘网关与智能终端架构设计（Modbus TCP + MQTT + REST API + MySQL + Redis）

## 1. 背景与目标

本系统面向局域网场景：PLC、边缘中间程序（网关）、PyQt6 智能终端部署在不同设备上，通过网络互联。

**目标：**
- 终端为厚客户端（Thick Client），承载核心业务逻辑，但不直接访问 PLC 与数据库
- 中间程序负责：PLC 通信（Modbus TCP）、数据标准化、数据持久化（MySQL）、高频状态缓存（Redis）、对外服务（REST API）、实时推送与指令通道（MQTT）
- 系统具备高可维护性/可读性：职责单一、接口契约清晰、配置集中、异常统一、可观测性可扩展

**非目标：**
- 不在中间程序实现业务规则（如配方计算、工艺逻辑等），仅实现数据访问与硬件抽象
- 不引入云端依赖（该版本专注于局域网）

## 2. 部署拓扑

```text
┌──────────────────────────────┐          ┌──────────────────────┐
│ PyQt6 智能终端（厚客户端）     │          │ MQTT Broker          │
│ - 业务逻辑 / MVVM             │  MQTT    │ Mosquitto / EMQX     │
│ - httpx 调用 REST API         ├─────────►│ :1883                │
│ - paho-mqtt 收/发实时消息     │◄─────────┤                      │
└───────────────┬──────────────┘          └──────────────────────┘
                │ HTTP/JSON
                ▼
┌───────────────────────────────────────────────────────────────┐
│ 中间程序（Edge Gateway / Data Service）                         │
│ - FastAPI: REST API (:8000)                                     │
│ - Modbus TCP: 读写 PLC                                          │
│ - Redis: 最新状态快照 + 高频写入缓冲                             │
│ - MySQL: 持久化（历史数据/业务数据/设备注册/日志）               │
└───────────────┬───────────────────────────┬───────────────────┘
                │ Modbus TCP                  │
                ▼                            ▼
            ┌────────┐                  ┌─────────┐
            │ PLC    │                  │ MySQL    │
            │ :502   │                  │ :3306    │
            └────────┘                  └─────────┘
                                           ▲
                                           │
                                       ┌─────────┐
                                       │ Redis   │
                                       │ :6379   │
                                       └─────────┘
```

## 3. 总体架构与职责边界

### 3.1 终端（PyQt6）

**职责：**
- UI 展示、交互、业务流程编排
- 通过 REST API 获取历史/配置/业务数据，提交业务数据
- 通过 MQTT 接收实时状态推送、发送控制指令

**约束：**
- 不出现 Modbus 寄存器地址/功能码等底层细节
- UI 线程不执行网络 IO；网络 IO 位于 ViewModel/后台线程，通过 Signal/Slot 更新界面

### 3.2 中间程序（FastAPI + PLC + DB）

**职责：**
- PLC 通信：读取/写入（Modbus TCP）
- 数据模型：把寄存器映射为业务字段（温度/压力/状态等）
- 数据持久化：写入 MySQL（历史数据、业务数据、设备注册信息、日志等）
- 状态缓存与缓冲：Redis 缓存设备最新状态快照；可作为高频写入缓冲队列
- 对外服务：
  - REST API：业务与历史查询、设备注册、配置管理等
  - MQTT：遥测推送、指令下发与执行结果事件

**约束：**
- 不实现业务规则，只做“数据与硬件抽象层 + 数据访问层”
- 所有对外输入输出均通过 Schema 约束（Pydantic），统一错误模型

## 4. 数据流设计

### 4.1 实时数据流（MQTT）

**场景：** PLC 高频采集 → 终端实时展示

**流程：**
1. 网关按设备配置轮询 PLC，得到标准化 Telemetry 数据
2. 网关将设备最新状态写入 Redis（状态快照）
3. 网关按“数据变化”或“固定周期”发布 MQTT Telemetry
4. 终端订阅并展示；必要时落地为本地业务状态

**Topic 规范（建议）：**
- Telemetry：`device/{device_id}/telemetry`
- Event：`device/{device_id}/event/{event_type}`
- Command：`device/{device_id}/command/{command_type}`
- Command Ack（可选）：`device/{device_id}/command_ack/{command_id}`

**Telemetry Payload（示例）：**
```json
{
  "device_id": "plc01",
  "timestamp": 1710000000000,
  "data": {
    "temperature": 25.4,
    "pressure": 1.2,
    "status": "running"
  }
}
```

### 4.2 指令流（MQTT → Modbus 写入）

**流程：**
1. 终端发布 Command 到 `device/{device_id}/command/{command_type}`
2. 网关订阅并解析 command，转换为 Modbus 写寄存器/线圈操作
3. 网关执行后写入 MySQL 指令日志，并发布执行结果 Event 或 Ack

**Command Payload（示例）：**
```json
{
  "command_id": "cmd_12345",
  "params": {
    "speed": 100
  }
}
```

### 4.3 业务/历史数据流（REST API → MySQL/Redis）

**原则：**
- 大数据量查询（历史曲线、分页列表）走 HTTP
- 当前状态快照优先从 Redis 返回（低延迟、减轻 PLC 与 MySQL 压力）

**接口示例：**
- `GET /api/v1/devices`：设备清单
- `POST /api/v1/devices`：设备注册
- `PATCH /api/v1/devices/{device_id}`：更新/停用设备
- `GET /api/v1/devices/{device_id}/state`：读取 Redis 中当前状态快照
- `GET /api/v1/history/{device_id}?limit=100`：历史数据

## 5. 设备注册设计（新增）

### 5.1 为什么需要设备注册

设备注册为系统提供“唯一事实来源（Single Source of Truth）”，用于：
- 网关决定要轮询哪些设备、设备的 Modbus 连接参数、寄存器映射版本
- 终端展示设备清单与在线状态
- 多 PLC/多产线扩展时，避免写死配置与 Topic

### 5.2 设备模型（MySQL）

建议至少包含：
- `device_id`：唯一标识（用于 Topic 命名空间）
- `name`：显示名称
- `enabled`：是否启用（网关只轮询 enabled 设备）
- `protocol`：`modbus_tcp`（后续可扩展）
- `modbus_host` / `modbus_port` / `unit_id`
- `mapping_version`：寄存器映射版本（便于升级兼容）
- `created_at` / `updated_at`

### 5.3 注册流程

1. 终端通过 REST API 录入或编辑设备参数
2. 网关按周期刷新设备清单（或在设备变更时触发刷新）
3. 网关对 enabled 设备启动轮询任务；停用则停止轮询并发布 offline 事件（可选）

### 5.4 在线状态

在线状态建议分两层：
- **网关采集层在线**：网关轮询成功则更新 Redis `device:{device_id}:online=1` 并写 last_seen；轮询失败则置为 0
- **终端订阅层在线（可选）**：MQTT LWT/心跳用于终端判断 broker 链路状态

## 6. 存储设计

### 6.1 Redis

- 当前状态快照：`plc:state:{device_id}`（JSON）
- 在线标记：`device:online:{device_id}`（0/1）与 `device:last_seen:{device_id}`
- 高频写入缓冲（可选）：Redis Stream/List，网关批量写入 MySQL

### 6.2 MySQL

- 设备注册表：设备元数据、连接参数、映射版本
- 历史数据表：遥测历史（按设备与时间索引）
- 指令日志表：command_id、device_id、command_type、参数、执行结果、耗时等
- 业务数据/配置表：由终端业务决定（网关仅提供 CRUD）

## 7. 可维护性与可读性约束（工程规范）

- 分层与边界：驱动层（PLC/MQTT/DB/Redis）与服务层（用例）与 API 层解耦
- 数据契约：所有 API 入参/出参均为 Schema；MQTT payload 固定字段（device_id/timestamp/data/command_id）
- 错误模型：HTTP 返回统一 `code/message/detail/trace_id`；MQTT 通过 event topic 发布错误事件
- 配置集中：.env + pydantic-settings；不同环境（开发/现场）仅通过配置切换

