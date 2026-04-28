# IoT Gateway & PyQt6 HMI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在局域网环境下实现一个“边缘网关（FastAPI）+ 智能终端（PyQt6）”系统：网关通过 Modbus TCP 采集/控制 PLC，通过 MQTT 推送实时状态并接收指令，通过 REST API 提供业务/历史/设备注册接口；网关使用 MySQL 持久化，Redis 缓存当前状态与（可选）高频写入缓冲；终端采用 MVVM，使用 httpx + paho-mqtt 与网关交互。

**Architecture:** 两个工程：`middleware/` 与 `terminal/`。网关侧分层（api/core/services/plc/mqtt/cache/models/schemas），终端侧 MVVM（views/viewmodels/network）。设备注册作为系统的“唯一事实来源”，网关按设备清单启停轮询与推送。

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, pymodbus, paho-mqtt, SQLAlchemy 2, aiomysql, redis-py, MySQL 8, Redis, Mosquitto/EMQX, PyQt6, httpx

---

## Task 1: 基础设施与项目骨架

**Files:**
- Create: `docker-compose.yml`
- Create: `middleware/requirements.txt`
- Create: `terminal/requirements.txt`
- Create: `middleware/main.py`
- Create: `terminal/main.py`

- [ ] **Step 1: 编写 docker-compose**

```yaml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: iot_db
    ports:
      - "3306:3306"
  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
  mosquitto:
    image: eclipse-mosquitto:latest
    ports:
      - "1883:1883"
    command: mosquitto -c /mosquitto-no-auth.conf
```

- [ ] **Step 2: 写入 requirements.txt（按实际版本约束可再收紧）**

`middleware/requirements.txt`
```text
fastapi>=0.100.0
uvicorn>=0.23.0
pymodbus>=3.4.0
paho-mqtt>=1.6.1
SQLAlchemy>=2.0.0
aiomysql>=0.2.0
redis>=5.0.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
```

`terminal/requirements.txt`
```text
PyQt6>=6.5.0
paho-mqtt>=1.6.1
httpx>=0.24.0
pydantic>=2.0.0
```

- [ ] **Step 3: 创建目录结构**

Run:
```bash
mkdir -p middleware/app/api/v1 middleware/app/core middleware/app/models middleware/app/schemas middleware/app/services middleware/app/plc middleware/app/cache middleware/app/mqtt
mkdir -p terminal/app/views terminal/app/viewmodels terminal/app/models terminal/app/network terminal/app/utils
```

---

## Task 2: 网关配置与 Redis 缓存层

**Files:**
- Create: `middleware/app/core/config.py`
- Create: `middleware/app/cache/redis_client.py`

- [ ] **Step 1: 配置**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "IoT Gateway"
    MYSQL_URL: str = "mysql+aiomysql://root:rootpassword@localhost:3306/iot_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 2: Redis 状态快照**

```python
import json
import redis.asyncio as redis
from middleware.app.core.config import settings

class RedisCache:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def update_plc_state(self, device_id: str, state_data: dict):
        await self.redis.set(f"plc:state:{device_id}", json.dumps(state_data))

    async def get_plc_state(self, device_id: str) -> dict:
        raw = await self.redis.get(f"plc:state:{device_id}")
        return json.loads(raw) if raw else {}

    async def set_online(self, device_id: str, online: bool):
        await self.redis.set(f"device:online:{device_id}", "1" if online else "0")

    async def set_last_seen_ms(self, device_id: str, ts_ms: int):
        await self.redis.set(f"device:last_seen:{device_id}", str(ts_ms))

redis_cache = RedisCache()
```

---

## Task 3: 数据库基础与设备注册（MySQL）

**Files:**
- Create: `middleware/app/core/database.py`
- Create: `middleware/app/models/device.py`
- Create: `middleware/app/schemas/device.py`
- Create: `middleware/app/models/history.py`
- Create: `middleware/app/schemas/history.py`

- [ ] **Step 1: 数据库连接**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from middleware.app.core.config import settings

engine = create_async_engine(settings.MYSQL_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] **Step 2: 设备注册表（最小字段集）**

```python
from sqlalchemy import Column, String, Integer, Boolean, DateTime
from sqlalchemy.sql import func
from middleware.app.core.database import Base

class Device(Base):
    __tablename__ = "devices"

    device_id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    protocol = Column(String(32), nullable=False, default="modbus_tcp")
    modbus_host = Column(String(128), nullable=False)
    modbus_port = Column(Integer, nullable=False, default=502)
    unit_id = Column(Integer, nullable=False, default=1)
    mapping_version = Column(String(32), nullable=False, default="v1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

- [ ] **Step 3: 设备 Schema**

```python
from pydantic import BaseModel
from typing import Optional

class DeviceCreate(BaseModel):
    device_id: str
    name: str
    modbus_host: str
    modbus_port: int = 502
    unit_id: int = 1
    mapping_version: str = "v1"
    enabled: bool = True

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    modbus_host: Optional[str] = None
    modbus_port: Optional[int] = None
    unit_id: Optional[int] = None
    mapping_version: Optional[str] = None
    enabled: Optional[bool] = None

class DeviceResponse(BaseModel):
    device_id: str
    name: str
    enabled: bool
    protocol: str
    modbus_host: str
    modbus_port: int
    unit_id: int
    mapping_version: str

    class Config:
        from_attributes = True
```

- [ ] **Step 4: 历史数据表（示例，按你的点位扩展）**

```python
from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.sql import func
from middleware.app.core.database import Base

class PLCHistory(Base):
    __tablename__ = "plc_history"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String(64), index=True)
    temperature = Column(Float)
    pressure = Column(Float)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
```

---

## Task 4: REST API（设备注册 + 当前状态 + 历史）

**Files:**
- Create: `middleware/app/api/v1/devices.py`
- Create: `middleware/app/api/v1/history.py`
- Modify: `middleware/main.py`

- [ ] **Step 1: 设备注册 API**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from middleware.app.core.database import get_db
from middleware.app.models.device import Device
from middleware.app.schemas.device import DeviceCreate, DeviceUpdate, DeviceResponse

router = APIRouter()

@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device))
    return result.scalars().all()

@router.post("/devices", response_model=DeviceResponse)
async def create_device(body: DeviceCreate, db: AsyncSession = Depends(get_db)):
    exists = await db.get(Device, body.device_id)
    if exists:
        raise HTTPException(status_code=409, detail="device_id already exists")
    obj = Device(**body.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj

@router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def update_device(device_id: str, body: DeviceUpdate, db: AsyncSession = Depends(get_db)):
    obj = await db.get(Device, device_id)
    if not obj:
        raise HTTPException(status_code=404, detail="device not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(obj, k, v)
    await db.commit()
    await db.refresh(obj)
    return obj
```

- [ ] **Step 2: 当前状态快照 API（读 Redis）**

将此接口也放在 `devices.py`：
```python
from middleware.app.cache.redis_client import redis_cache

@router.get("/devices/{device_id}/state")
async def get_device_state(device_id: str):
    return await redis_cache.get_plc_state(device_id)
```

- [ ] **Step 3: 历史查询 API**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from middleware.app.core.database import get_db
from middleware.app.models.history import PLCHistory
from middleware.app.schemas.history import PLCHistoryResponse

router = APIRouter()

@router.get("/history/{device_id}", response_model=List[PLCHistoryResponse])
async def get_history(device_id: str, limit: int = 100, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PLCHistory)
        .where(PLCHistory.device_id == device_id)
        .order_by(PLCHistory.timestamp.desc())
        .limit(limit)
    )
    return result.scalars().all()
```

- [ ] **Step 4: 挂载 FastAPI + 自动建表**

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from middleware.app.core.database import engine, Base
from middleware.app.api.v1.devices import router as devices_router
from middleware.app.api.v1.history import router as history_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title="IoT Gateway API", lifespan=lifespan)
app.include_router(devices_router, prefix="/api/v1", tags=["devices"])
app.include_router(history_router, prefix="/api/v1", tags=["history"])
```

---

## Task 5: PLC 轮询（按设备清单启停）与 Redis 更新

**Files:**
- Create: `middleware/app/plc/driver.py`
- Create: `middleware/app/services/polling.py`
- Modify: `middleware/main.py`

- [ ] **Step 1: 单设备 Modbus 驱动（按 host/port/unit_id 实例化）**

```python
from pymodbus.client import AsyncModbusTcpClient

class PLCDriver:
    def __init__(self, host: str, port: int):
        self.client = AsyncModbusTcpClient(host, port=port)

    async def connect(self):
        await self.client.connect()

    async def close(self):
        self.client.close()

    async def read_telemetry(self, unit_id: int) -> dict | None:
        result = await self.client.read_holding_registers(address=0, count=2, slave=unit_id)
        if result.isError():
            return None
        return {
            "temperature": result.registers[0] / 10.0,
            "pressure": result.registers[1] / 100.0,
        }

    async def write_speed(self, unit_id: int, speed: int) -> bool:
        result = await self.client.write_register(address=10, value=speed, slave=unit_id)
        return not result.isError()
```

- [ ] **Step 2: 轮询服务：从 MySQL 读取 enabled 设备列表，循环轮询**

实现策略建议：先做“单进程 + 顺序轮询”，可跑通后再做并发优化。

---

## Task 6: MQTT 遥测推送与指令接收（按 device_id 命名空间）

**Files:**
- Create: `middleware/app/mqtt/client.py`
- Modify: `middleware/main.py`

- [ ] **Step 1: MQTT Service**

要求：
- 订阅 `device/+/command/+`
- 发布 `device/{device_id}/telemetry`
- 指令执行后可发布 `device/{device_id}/event/command_result`（可选）

---

## Task 7: 终端网络层（HTTP + MQTT）

**Files:**
- Create: `terminal/app/network/api_client.py`
- Create: `terminal/app/network/mqtt_client.py`

- [ ] **Step 1: API Client 增加设备注册相关方法**

最少包含：
- `list_devices()`
- `create_device(payload)`
- `update_device(device_id, payload)`
- `get_device_state(device_id)`

---

## Task 8: 终端 MVVM + 设备注册 UI（最小可用）

**Files:**
- Create: `terminal/app/viewmodels/device_vm.py`
- Create: `terminal/app/views/device_page.py`
- Modify: `terminal/app/views/main_window.py`

- [ ] **Step 1: DeviceViewModel**

职责：
- 从 API 获取设备列表并展示
- 提交注册/编辑表单
- 展示在线状态与当前快照（调用 `get_device_state`）

---

## 验证清单（手动）

- 启动基础设施：`docker-compose up -d`
- 启动网关：`uvicorn middleware.main:app --reload --host 0.0.0.0 --port 8000`
- 打开 Swagger：`http://localhost:8000/docs`
- 注册设备：`POST /api/v1/devices`
- 启动终端：`python terminal/main.py`
- 终端能订阅 telemetry 并显示实时数据；能发送 set_speed 指令并在网关侧写入 PLC（现场接 PLC 后验证）

