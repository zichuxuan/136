# 设备日志表设计 (Device Log Table Design)

## 1. 背景与目标 (Why)
为了更好地进行系统故障排查、事件审计以及设备状态追踪，系统需要一个综合性的设备日志表。
主要应用场景包括：记录操作指令下发、设备状态变更（上线/离线/报警）、遥测数据快照等。
考虑到日志产生频率为中低频，系统将采用普通的 MySQL 关系型数据表进行存储，以便于与现有架构集成并方便查询和维护。

## 2. 变更内容 (What Changes)
- **数据库表**: 设计并创建 `device_logs` 表，用于存储设备的各类综合性日志。
- **ORM 模型**: 在后端 SQLAlchemy 层新增 `DeviceLog` 模型，并建立与 `Device` 实例的一对多关联。
- **数据 Schema**: 在后端 Pydantic 层新增 `DeviceLog` 相关的基础、创建和响应模型，用于 API 接口数据校验与序列化。
- **初始化脚本**: 更新 `middleware/init.sql`，追加 `device_logs` 的 DDL 语句。

## 3. 数据库表结构设计 (Schema Design)

**表名:** `device_logs`

| 字段名 | 类型 | 约束 | 描述 |
|---|---|---|---|
| `id` | INT | PK, AUTO_INCREMENT | 主键，日志唯一标识符 |
| `device_id` | INT | FK (devices.id), NOT NULL | 外键，关联的设备实例 ID |
| `level` | VARCHAR(50) | NOT NULL | 日志级别 (如: INFO, WARN, ERROR, DEBUG) |
| `event_type` | VARCHAR(50) | NOT NULL | 事件类型 (如: COMMAND, STATUS_CHANGE, TELEMETRY, ALARM) |
| `message` | VARCHAR(255) | NOT NULL | 日志简短摘要/描述 |
| `details` | JSON | NULL | 详细信息 (如: 完整的指令报文、错误堆栈、遥测快照等) |
| `created_at` | DATETIME | DEFAULT CURRENT_TIMESTAMP | 日志产生时间 |

## 4. 影响范围 (Impact)
- **Affected Code**: 
  - `middleware/app/models/device.py` (追加 `DeviceLog` 模型，并在 `Device` 模型中增加 `logs` 关联属性)
  - `middleware/app/schemas/device.py` (追加 `DeviceLogBase`, `DeviceLogCreate`, `DeviceLog` Schema)
  - `middleware/init.sql` (追加 `device_logs` 表定义)
