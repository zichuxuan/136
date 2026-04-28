# Device Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为物联网网关与智能终端架构增加设备日志表（`device_logs`），用于记录操作指令下发、设备状态变更、遥测数据快照等综合性设备日志。

**Architecture:** 
- 在现有的 `Device` ORM 模型和 Schema 基础上进行扩展。
- 在 `middleware/app/models/device.py` 中增加 `DeviceLog` SQLAlchemy 模型。
- 在 `middleware/app/schemas/device.py` 中增加 `DeviceLog` 相关的 Pydantic Schema。
- 在 `middleware/init.sql` 中追加建表 DDL。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2, Pydantic 2.0+, MySQL 8

---

### Task 1: Update Database Initialization Script

**Files:**
- Modify: `middleware/init.sql`

- [ ] **Step 1: Append device_logs DDL**

Append the following table creation SQL to `middleware/init.sql`:

```sql
-- --------------------------------------------------------
-- 表结构 `device_logs` (设备日志表)
-- --------------------------------------------------------
CREATE TABLE `device_logs` (
    `id` INT NOT NULL AUTO_INCREMENT COMMENT '主键，日志唯一标识符',
    `device_id` INT NOT NULL COMMENT '外键，关联的设备实例 ID',
    `level` VARCHAR(50) NOT NULL COMMENT '日志级别 (如: INFO, WARN, ERROR, DEBUG)',
    `event_type` VARCHAR(50) NOT NULL COMMENT '事件类型 (如: COMMAND, STATUS_CHANGE, TELEMETRY, ALARM)',
    `message` VARCHAR(255) NOT NULL COMMENT '日志简短摘要/描述',
    `details` JSON DEFAULT NULL COMMENT '详细信息 (如: 完整的指令报文、错误堆栈、遥测快照等)',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '日志产生时间',
    PRIMARY KEY (`id`),
    CONSTRAINT `fk_device_logs_device_id` FOREIGN KEY (`device_id`) REFERENCES `devices` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='设备日志表';
```

- [ ] **Step 2: Commit**

```bash
git add middleware/init.sql
git commit -m "feat(db): add device_logs table definition to init.sql"
```

---

### Task 2: Implement SQLAlchemy ORM Model

**Files:**
- Modify: `middleware/app/models/device.py`

- [ ] **Step 1: Add DeviceLog Model**

Add the `DeviceLog` model at the end of `middleware/app/models/device.py` and update imports if necessary (need `DateTime` and `func` from `sqlalchemy.sql`):

```python
# Add to imports if not present
from sqlalchemy import DateTime, Text
from sqlalchemy.sql import func

# Add at the end of the file
class DeviceLog(Base):
    """
    设备日志表 (DeviceLog)
    """
    __tablename__ = "device_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, comment="设备实例id")
    level = Column(String(50), nullable=False, comment="日志级别")
    event_type = Column(String(50), nullable=False, comment="事件类型")
    message = Column(String(255), nullable=False, comment="日志简短摘要")
    details = Column(JSON, nullable=True, comment="详细信息 json")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="日志产生时间")

    device = relationship("Device", back_populates="logs")
```

- [ ] **Step 2: Update Device Model Relationship**

In the `Device` class in `middleware/app/models/device.py`, add the `logs` relationship:

```python
    actions = relationship("DeviceAction", back_populates="device", cascade="all, delete-orphan")
    logs = relationship("DeviceLog", back_populates="device", cascade="all, delete-orphan")
```

- [ ] **Step 3: Commit**

```bash
git add middleware/app/models/device.py
git commit -m "feat(models): implement DeviceLog ORM model and relationships"
```

---

### Task 3: Implement Pydantic Schemas

**Files:**
- Modify: `middleware/app/schemas/device.py`

- [ ] **Step 1: Add DeviceLog Schemas**

Add the following classes to `middleware/app/schemas/device.py` (import `datetime` if not present):

```python
# Add to imports
from datetime import datetime

# --- DeviceLog Schemas ---

class DeviceLogBase(BaseModel):
    level: str = Field(..., description="日志级别")
    event_type: str = Field(..., description="事件类型")
    message: str = Field(..., description="日志简短摘要")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息 json")

class DeviceLogCreate(DeviceLogBase):
    device_id: int = Field(..., description="设备实例id")

class DeviceLog(DeviceLogBase):
    id: int = Field(..., description="日志ID")
    device_id: int = Field(..., description="设备实例id")
    created_at: Optional[datetime] = Field(None, description="日志产生时间")

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 2: Update Device Schema**

In the `Device` schema class, add the `logs` field:

```python
class Device(DeviceBase):
    id: int = Field(..., description="设备实例ID")
    device_model_id: int = Field(..., description="设备型号id")
    actions: List[DeviceAction] = Field(default=[], description="动作列表")
    logs: List[DeviceLog] = Field(default=[], description="设备日志列表")

    model_config = ConfigDict(from_attributes=True)
```

- [ ] **Step 3: Commit**

```bash
git add middleware/app/schemas/device.py
git commit -m "feat(schemas): add DeviceLog Pydantic schemas"
```
