# IPC 边缘侧（消息总线 + 网关 + 数据层）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在工控机上完成 Mosquitto + MySQL + Redis + FastAPI 网关的一键部署，并跑通“跨主机 HMI 访问 HTTP 与 MQTT”的最小闭环。

**Architecture:** 工控机用 Docker Compose 运行 Mosquitto/MySQL/Redis/FastAPI。HMI 主机通过 LAN 访问工控机的 `:1883`（MQTT）与 `:8000`（HTTP）。FastAPI 使用 SQLAlchemy（对接现有 `middleware/app/models`）持久化设备/工作流数据，Redis 保存实时快照。

**Tech Stack:** Ubuntu 22.04, Docker Engine, Docker Compose, Mosquitto, MySQL 8.0, Redis, Python 3.10 (container), FastAPI, Uvicorn, SQLAlchemy 2.x, aiomysql, redis-py asyncio, pydantic v2, pytest

---

## 文件结构（本计划将落地的目录）

**Repo Root**
*   `docker-compose.yml`：服务编排
*   `deploy/`：Mosquitto/Redis 配置与初始化文件
*   `middleware/`：FastAPI 网关工程（已有 models/schemas，将补齐运行代码）

**新增/修改文件一览**
*   Create: `docker-compose.yml`
*   Create: `deploy/mosquitto/mosquitto.conf`
*   Create: `deploy/mosquitto/aclfile`
*   Create: `deploy/mosquitto/passwordfile`（本地生成，不提交仓库）
*   Create: `deploy/redis/redis.conf`
*   Create: `middleware/Dockerfile`
*   Create: `middleware/requirements.txt`
*   Create: `middleware/app/main.py`
*   Create: `middleware/app/core/config.py`
*   Modify: `middleware/app/core/database.py`
*   Create: `middleware/app/core/db.py`
*   Create: `middleware/app/core/redis.py`
*   Create: `middleware/app/api/router.py`
*   Create: `middleware/app/api/health.py`
*   Create: `middleware/app/api/devices.py`
*   Create: `middleware/app/api/workflows.py`
*   Create: `middleware/tests/test_health.py`
*   Create: `middleware/pytest.ini`

---

### Task 1: 工控机基础环境准备（Docker + 端口策略）

**Files:**
*   No repo changes

- [ ] **Step 1: 安装 Docker Engine 与 Compose 插件**

Run (on IPC):
```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo ${VERSION_CODENAME}) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version
docker compose version
```

- [ ] **Step 2: 放行 LAN 访问端口（仅 1883/8000）**

Run (示例为 UFW；如您使用其他防火墙替换即可):
```bash
sudo ufw allow from 192.168.0.0/16 to any port 1883 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 8000 proto tcp
sudo ufw deny 3306/tcp
sudo ufw deny 6379/tcp
sudo ufw status verbose
```

Expected:
*   仅局域网网段可以访问 1883/8000
*   3306/6379 不对外开放

---

### Task 2: 落地 Docker Compose（Mosquitto/MySQL/Redis/Gateway）

**Files:**
*   Create: `docker-compose.yml`
*   Create: `deploy/mosquitto/mosquitto.conf`
*   Create: `deploy/mosquitto/aclfile`
*   Create: `deploy/redis/redis.conf`

- [ ] **Step 1: 创建 Mosquitto 配置**

Create `deploy/mosquitto/mosquitto.conf`:
```conf
persistence true
persistence_location /mosquitto/data/
log_dest stdout

allow_anonymous false
password_file /mosquitto/config/passwordfile
acl_file /mosquitto/config/aclfile

listener 1883 0.0.0.0
```

- [ ] **Step 2: 创建 Mosquitto ACL**

Create `deploy/mosquitto/aclfile`:
```conf
user gateway
topic readwrite telemetry/plc/#
topic readwrite event/plc/#
topic readwrite gateway/status
topic read command/plc/#

user hmi
topic read telemetry/plc/#
topic read event/plc/#
topic read gateway/status
topic write command/plc/#
```

- [ ] **Step 3: 创建 Redis 配置**

Create `deploy/redis/redis.conf`:
```conf
bind 0.0.0.0
protected-mode yes
port 6379
timeout 0
tcp-keepalive 300

maxmemory 1gb
maxmemory-policy allkeys-lru
```

- [ ] **Step 4: 创建 docker-compose.yml**

Create `docker-compose.yml`:
```yaml
services:
  mysql:
    image: mysql:8.0
    command:
      - --default-authentication-plugin=mysql_native_password
      - --character-set-server=utf8mb4
      - --collation-server=utf8mb4_unicode_ci
      - --innodb-buffer-pool-size=1G
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: iot_db
    volumes:
      - ./middleware/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
      - ./data/mysql:/var/lib/mysql
    networks:
      - iot-net
    restart: always
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: "3"

  redis:
    image: redis:7-alpine
    command: ["redis-server", "/usr/local/etc/redis/redis.conf"]
    volumes:
      - ./deploy/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
      - ./data/redis:/data
    networks:
      - iot-net
    restart: always
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: "3"

  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    volumes:
      - ./deploy/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./deploy/mosquitto/aclfile:/mosquitto/config/aclfile:ro
      - ./deploy/mosquitto/passwordfile:/mosquitto/config/passwordfile:ro
      - ./data/mosquitto:/mosquitto/data
    networks:
      - iot-net
    restart: always
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: "3"

  gateway:
    build:
      context: ./middleware
    ports:
      - "8000:8000"
    environment:
      MYSQL_URL: mysql+aiomysql://root:rootpassword@mysql:3306/iot_db
      REDIS_URL: redis://redis:6379/0
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
      MQTT_USERNAME: gateway
      MQTT_PASSWORD: gatewaypassword
      API_TOKEN: changeme
    depends_on:
      - mysql
      - redis
      - mosquitto
    networks:
      - iot-net
    restart: always
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz').read()\""]
      interval: 10s
      timeout: 3s
      retries: 6
    logging:
      driver: json-file
      options:
        max-size: 20m
        max-file: "3"

networks:
  iot-net:
    driver: bridge
```

- [ ] **Step 5: 在工控机生成 Mosquitto 密码文件（不提交仓库）**

Run:
```bash
mkdir -p deploy/mosquitto
docker run --rm -v "$(pwd)/deploy/mosquitto:/out" eclipse-mosquitto:2 \
  sh -lc "mosquitto_passwd -b -c /out/passwordfile gateway gatewaypassword && mosquitto_passwd -b /out/passwordfile hmi hmipassword"
```

- [ ] **Step 6: 启动基础设施并验证**

Run:
```bash
docker compose up -d --build
docker compose ps
```

Expected:
*   `mosquitto/mysql/redis/gateway` 均为 `Up`

---

### Task 3: 网关容器镜像与依赖（FastAPI 可启动）

**Files:**
*   Create: `middleware/Dockerfile`
*   Create: `middleware/requirements.txt`
*   Create: `middleware/app/main.py`
*   Create: `middleware/app/core/config.py`
*   Create: `middleware/app/api/router.py`
*   Create: `middleware/app/api/health.py`

- [ ] **Step 1: 写 requirements.txt**

Create `middleware/requirements.txt`:
```text
fastapi==0.115.0
uvicorn==0.30.6
SQLAlchemy==2.0.36
aiomysql==0.2.0
redis==5.0.8
pydantic==2.9.2
pydantic-settings==2.5.2
pytest==8.3.3
httpx==0.27.2
```

- [ ] **Step 2: 写 Dockerfile**

Create `middleware/Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["uvicorn", "middleware.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: 写配置读取（Pydantic Settings）**

Create `middleware/app/core/config.py`:
```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MYSQL_URL: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    API_TOKEN: str


settings = Settings()
```

- [ ] **Step 4: 创建 API Router 与健康检查**

Create `middleware/app/api/router.py`:
```python
from fastapi import APIRouter

from middleware.app.api.health import router as health_router

router = APIRouter()
router.include_router(health_router)
```

Create `middleware/app/api/health.py`:
```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"ok": True}
```

- [ ] **Step 5: 创建 FastAPI 入口**

Create `middleware/app/main.py`:
```python
from fastapi import FastAPI

from middleware.app.api.router import router

app = FastAPI(title="IPC Gateway")
app.include_router(router)
```

- [ ] **Step 6: 验证 gateway 服务可对外访问**

Run:
```bash
docker compose up -d --build gateway
curl -sS http://127.0.0.1:8000/healthz
```

Expected:
```json
{"ok":true}
```

---

### Task 4: MySQL 访问层（复用现有 Models）

**Files:**
*   Modify: `middleware/app/core/database.py`
*   Create: `middleware/app/core/db.py`
*   Modify: `middleware/app/main.py`

- [ ] **Step 1: 扩展 Base 定义文件**

Modify `middleware/app/core/database.py`:
```python
from sqlalchemy.orm import declarative_base

Base = declarative_base()
```

- [ ] **Step 2: 增加异步 Engine 与 Session 依赖注入**

Create `middleware/app/core/db.py`:
```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from middleware.app.core.config import settings

engine = create_async_engine(settings.MYSQL_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 3: 在应用启动时校验数据库可连通**

Modify `middleware/app/main.py`:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

from middleware.app.api.router import router
from middleware.app.core.db import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute("SELECT 1")
    yield
    await engine.dispose()


app = FastAPI(title="IPC Gateway", lifespan=lifespan)
app.include_router(router)
```

- [ ] **Step 4: 验证数据库连通性**

Run:
```bash
docker compose up -d --build
docker compose logs --tail=50 gateway
curl -sS http://127.0.0.1:8000/healthz
```

Expected:
*   gateway 日志无数据库连接报错

---

### Task 5: Redis 实时快照层

**Files:**
*   Create: `middleware/app/core/redis.py`
*   Modify: `middleware/app/api/health.py`

- [ ] **Step 1: 创建 Redis 客户端**

Create `middleware/app/core/redis.py`:
```python
import redis.asyncio as redis

from middleware.app.core.config import settings

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
```

- [ ] **Step 2: healthz 增加 Redis 可用性校验**

Modify `middleware/app/api/health.py`:
```python
from fastapi import APIRouter

from middleware.app.core.redis import redis_client

router = APIRouter()


@router.get("/healthz")
async def healthz():
    pong = await redis_client.ping()
    return {"ok": True, "redis": bool(pong)}
```

- [ ] **Step 3: 验证 Redis 连通性**

Run:
```bash
docker compose up -d --build gateway
curl -sS http://127.0.0.1:8000/healthz
```

Expected:
```json
{"ok":true,"redis":true}
```

---

### Task 6: CRUD API（DeviceModel/Device/Workflow）

**Files:**
*   Create: `middleware/app/api/devices.py`
*   Create: `middleware/app/api/workflows.py`
*   Modify: `middleware/app/api/router.py`

- [ ] **Step 1: devices API（最小：列出 device_models 与 devices）**

Create `middleware/app/api/devices.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.app.core.db import get_db
from middleware.app.models.device import Device, DeviceModel

router = APIRouter(prefix="/api/v1", tags=["devices"])


@router.get("/device-models")
async def list_device_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DeviceModel).order_by(DeviceModel.id.asc()))
    items = result.scalars().all()
    return [{"id": i.id, "name": i.name, "protocol": i.protocol} for i in items]


@router.get("/devices")
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).order_by(Device.id.asc()))
    items = result.scalars().all()
    return [{"id": i.id, "device_code": i.device_code, "name": i.name} for i in items]
```

- [ ] **Step 2: workflows API（最小：列出 workflows）**

Create `middleware/app/api/workflows.py`:
```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.app.core.db import get_db
from middleware.app.models.workflow import Workflow

router = APIRouter(prefix="/api/v1", tags=["workflows"])


@router.get("/workflows")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(Workflow.id.asc()))
    items = result.scalars().all()
    return [{"id": i.id, "name": i.name, "status": i.status, "type": i.type} for i in items]
```

- [ ] **Step 3: 挂载新 router**

Modify `middleware/app/api/router.py`:
```python
from fastapi import APIRouter

from middleware.app.api.devices import router as devices_router
from middleware.app.api.health import router as health_router
from middleware.app.api.workflows import router as workflows_router

router = APIRouter()
router.include_router(health_router)
router.include_router(devices_router)
router.include_router(workflows_router)
```

- [ ] **Step 4: 验证 API**

Run:
```bash
docker compose up -d --build gateway
curl -sS http://127.0.0.1:8000/api/v1/device-models
curl -sS http://127.0.0.1:8000/api/v1/devices
curl -sS http://127.0.0.1:8000/api/v1/workflows
```

Expected:
*   返回 JSON 数组（可为空），且请求无 500

---

### Task 7: 最小化测试（避免后续改动“跑着跑着挂了”）

**Files:**
*   Create: `middleware/tests/test_health.py`
*   Create: `middleware/pytest.ini`

- [ ] **Step 1: 写测试**

Create `middleware/pytest.ini`:
```ini
[pytest]
testpaths = tests
```

Create `middleware/tests/test_health.py`:
```python
import pytest
from httpx import AsyncClient

from middleware.app.main import app


@pytest.mark.anyio
async def test_healthz_ok():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
```

- [ ] **Step 2: 在容器内运行测试**

Run:
```bash
docker compose run --rm gateway pytest -q
```

Expected:
*   测试通过

---

## 执行交付检查（HMI 主机联调）
在 HMI 主机上（局域网另一台机器）做 2 个最小验证：
1. HTTP：`curl http://<ipc-ip>:8000/healthz`
2. MQTT：订阅遥测 topic（先用 mosquitto_sub 验证连通）
```bash
mosquitto_sub -h <ipc-ip> -p 1883 -u hmi -P hmipassword -t 'gateway/status' -v
```

如果两项均可访问，说明“跨主机网络链路 + 工控机侧基础设施”已经具备，下一步再进入 Modbus 驱动与 MQTT 指令/遥测闭环开发。

