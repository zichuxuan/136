# IPC 边缘侧技术栈部署说明文档

## 概述

本文档详细说明了在工控机（IPC）上部署 IoT 边缘侧技术栈的完整过程，包括：

- **Docker & Docker Compose** 安装与配置
- **Mosquitto** MQTT 消息总线
- **MySQL 8.0** 关系型数据库
- **Redis 7** 缓存/实时数据存储
- **FastAPI** 网关服务

实现"跨主机 HMI 访问 HTTP 与 MQTT"的最小闭环，支持 PLC 遥测数据采集、历史数据持久化和指令下发。

## 环境要求

- **操作系统**: Ubuntu 22.04 x86_64
- **网络**: 局域网连接（HMI 通过 LAN 访问工控机）
- **端口**: 1883 (MQTT), 8000 (HTTP API)

---

## 一、Docker 和 Docker Compose 安装

### 1.1 安装步骤

```bash
# 1. 更新 apt 并安装依赖
sudo apt update
sudo apt install -y ca-certificates curl gnupg lsb-release

# 2. 添加 Docker 官方 GPG 密钥
sudo mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 3. 设置 Docker 仓库
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 4. 安装 Docker 引擎和 Compose 插件
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 5. 验证安装
docker --version
docker compose version
```

### 1.2 Docker 镜像源配置

由于国内访问 Docker Hub 可能受限，配置了镜像加速：

```bash
# 创建/编辑 daemon.json
sudo mkdir -p /etc/docker
echo '{"registry-mirrors":["https://hub-mirror.c.163.com","https://mirror.baidubce.com","https://docker.m.daocloud.io"]}' | sudo tee /etc/docker/daemon.json

# 重启 Docker
sudo systemctl restart docker
```

---

## 二、防火墙配置

放行必要的端口，限制访问来源：

```bash
# 允许局域网访问 MQTT 和 HTTP API
sudo ufw allow from 192.168.0.0/16 to any port 1883 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 8000 proto tcp

# 拒绝外部访问数据库和缓存端口
sudo ufw deny 3306/tcp
sudo ufw deny 6379/tcp

# 查看状态
sudo ufw status verbose
```

> **注意**: 如果防火墙未启用，规则会在启用后生效。

---

## 三、文件结构

```
/home/ok/智能产线/
├── docker-compose.yml          # Docker 服务编排
├── deploy/
│   ├── mosquitto/
│   │   ├── mosquitto.conf      # Mosquitto 配置文件
│   │   ├── aclfile             # MQTT 访问控制列表
│   │   └── passwordfile        # MQTT 用户密码（自动生成，不提交仓库）
│   └── redis/
│       └── redis.conf          # Redis 配置文件
├── middleware/
│   ├── Dockerfile              # FastAPI 网关容器镜像
│   ├── requirements.txt        # Python 依赖
│   ├── init.sql                # MySQL 初始化脚本（建表）
│   ├── pytest.ini              # Pytest 配置
│   ├── app/
│   │   ├── main.py             # FastAPI 应用入口
│   │   ├── core/
│   │   │   ├── config.py       # 环境变量配置（Pydantic Settings）
│   │   │   ├── database.py     # SQLAlchemy Base 定义
│   │   │   ├── db.py           # 异步数据库会话管理
│   │   │   ├── redis.py        # Redis 客户端
│   │   │   └── mqtt_client.py  # MQTT 客户端（aiomqtt）
│   │   ├── api/
│   │   │   ├── router.py       # API 路由聚合
│   │   │   ├── health.py       # 健康检查接口
│   │   │   ├── devices.py      # 设备管理 API
│   │   │   ├── workflows.py    # 工作流 API
│   │   │   ├── telemetry.py    # 遥测数据查询 API
│   │   │   └── commands.py     # 指令控制 API
│   │   ├── models/
│   │   │   ├── device.py       # 设备模型（DeviceModel, Device）
│   │   │   └── workflow.py     # 工作流模型
│   │   └── services/
│   │       ├── telemetry_service.py  # 遥测数据处理服务
│   │       └── command_service.py    # 指令处理服务
│   └── tests/
│       └── test_health.py      # 健康检查测试
└── data/                       # 数据持久化目录
    ├── mysql/                  # MySQL 数据文件
    ├── redis/                  # Redis 数据文件
    └── mosquitto/              # Mosquitto 持久化数据
```

---

## 四、Docker Compose 配置

### 4.1 docker-compose.yml 说明

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpassword
      MYSQL_DATABASE: iot_db
    volumes:
      - ./middleware/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
      - ./data/mysql:/var/lib/mysql
    restart: always

  redis:
    image: redis:7-alpine
    volumes:
      - ./deploy/redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
      - ./data/redis:/data
    restart: always

  mosquitto:
    image: eclipse-mosquitto:2
    ports:
      - "1883:1883"
    volumes:
      - ./deploy/mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./deploy/mosquitto/aclfile:/mosquitto/config/aclfile:ro
      - ./deploy/mosquitto/passwordfile:/mosquitto/config/passwordfile:ro
      - ./data/mosquitto:/mosquitto/data
    restart: always

  gateway:
    build: ./middleware
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
    restart: always
```

### 4.2 启动服务

```bash
# 首次启动（构建镜像并启动所有服务）
docker compose up -d --build

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs --tail=50 gateway
```

---

## 五、Mosquitto 配置

### 5.1 mosquitto.conf

```conf
persistence true
persistence_location /mosquitto/data/
log_dest stdout

allow_anonymous false
password_file /mosquitto/config/passwordfile
acl_file /mosquitto/config/aclfile

listener 1883 0.0.0.0
```

### 5.2 ACL 访问控制

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

### 5.3 生成密码文件

```bash
# 方法1：使用本地 mosquitto_passwd 工具
sudo mosquitto_passwd -b -c deploy/mosquitto/passwordfile gateway gatewaypassword
sudo mosquitto_passwd -b deploy/mosquitto/passwordfile hmi hmipassword

# 方法2：使用 Docker 容器生成
docker run --rm -v "$(pwd)/deploy/mosquitto:/out" eclipse-mosquitto:2 \
  sh -lc "mosquitto_passwd -b -c /out/passwordfile gateway gatewaypassword && mosquitto_passwd -b /out/passwordfile hmi hmipassword"

# 设置文件权限（允许容器读取）
chmod 644 deploy/mosquitto/passwordfile
```

> **注意**: 停止系统 mosquitto 服务（如果已安装），避免端口冲突：
> ```bash
> sudo systemctl stop mosquitto
> sudo systemctl disable mosquitto
> ```

---

## 六、Redis 配置

### 6.1 redis.conf

```conf
bind 0.0.0.0
protected-mode no
port 6379
timeout 0
tcp-keepalive 300

maxmemory 1gb
maxmemory-policy allkeys-lru
```

> **说明**: `protected-mode no` 允许 Docker 容器间连接。在生产环境中应设置密码并启用保护模式。

---

## 七、数据库初始化

### 7.1 init.sql

MySQL 容器启动时自动执行 `middleware/init.sql`，创建以下表：

| 表名 | 用途 |
|------|------|
| `device_models` | 设备型号定义 |
| `devices` | 设备实例 |
| `workflows` | 工作流配置 |
| `telemetry_history` | 遥测历史数据（带索引优化） |

---

## 八、FastAPI 网关服务

### 8.1 依赖（requirements.txt）

```
fastapi==0.115.0
uvicorn==0.30.6
SQLAlchemy==2.0.36
aiomysql==0.2.0
redis==5.0.8
pydantic==2.9.2
pydantic-settings==2.5.2
pytest==8.3.3
httpx==0.27.2
aiomqtt==2.3.0
```

### 8.2 核心模块

#### 配置管理（core/config.py）

使用 Pydantic Settings 读取环境变量：

```python
class Settings(BaseSettings):
    MYSQL_URL: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    API_TOKEN: str
```

#### 数据库会话（core/db.py）

```python
engine = create_async_engine(settings.MYSQL_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with SessionLocal() as session:
        yield session
```

#### MQTT 客户端（core/mqtt_client.py）

- 异步连接 Mosquitto
- 订阅遥测、事件、指令主题
- 支持发布消息（通过队列避免重入问题）
- 主题匹配支持 `+` 和 `#` 通配符

### 8.3 业务服务

#### 遥测服务（services/telemetry_service.py）

**功能**:
1. 接收 `telemetry/plc/+` 主题数据
2. 存入 Redis（最新数据，5分钟 TTL）
3. 存入 MySQL（历史数据，持久化）

**数据结构**:
```json
{
  "device_id": "device001",
  "timestamp": "2026-04-21T01:01:09.913836",
  "data": {"temperature": 26.0, "pressure": 101.3}
}
```

#### 指令服务（services/command_service.py）

**功能**:
1. 接收 `command/plc/+` 主题数据
2. 记录指令历史和结果
3. 执行指令并发布事件反馈
4. 支持通过 HTTP API 下发指令

---

## 九、API 接口文档

### 9.1 健康检查

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/healthz` | 服务健康状态（含 Redis 检查） |

**响应示例**:
```json
{"ok": true, "redis": true}
```

### 9.2 设备管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/device-models` | 获取设备型号列表 |
| GET | `/api/v1/devices` | 获取设备列表 |
| GET | `/api/v1/workflows` | 获取工作流列表 |

### 9.3 遥测数据

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/telemetry/latest/{device_id}` | 获取设备最新遥测数据 |
| GET | `/api/v1/telemetry/history/{device_id}` | 获取设备历史遥测数据 |
| GET | `/api/v1/telemetry/events/{device_id}/latest` | 获取设备最新事件 |
| GET | `/api/v1/telemetry/events/{device_id}/history` | 获取设备事件历史 |

**查询参数**:
- `start_time` / `end_time`: 时间范围过滤
- `limit`: 返回数量限制（默认 100）

### 9.4 指令控制

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/commands/send` | 下发指令 |
| GET | `/api/v1/commands/latest/{device_id}` | 获取最新指令 |
| GET | `/api/v1/commands/history/{device_id}` | 获取指令历史 |
| GET | `/api/v1/commands/result/{device_id}` | 获取指令执行结果 |

**POST 请求体**:
```json
{
  "device_id": "device001",
  "command_type": "start",
  "params": {"speed": 100}
}
```

---

## 十、测试验证

### 10.1 HTTP API 测试

```bash
# 健康检查
curl http://<ipc-ip>:8000/healthz

# 获取设备列表
curl http://<ipc-ip>:8000/api/v1/devices

# 获取最新遥测
curl http://<ipc-ip>:8000/api/v1/telemetry/latest/device001
```

### 10.2 MQTT 测试

```bash
# 订阅遥测主题（HMI 接收数据）
mosquitto_sub -h <ipc-ip> -p 1883 -u hmi -P hmipassword -t 'telemetry/plc/+' -v

# 发布遥测数据（PLC 发送数据）
mosquitto_pub -h <ipc-ip> -p 1883 -u gateway -P gatewaypassword -t 'telemetry/plc/device001' -m '{"temperature":26.0}'

# 发布指令（HMI 下发指令）
mosquitto_pub -h <ipc-ip> -p 1883 -u hmi -P hmipassword -t 'command/plc/device001' -m '{"type":"start","params":{"speed":100}}'
```

### 10.3 运行测试套件

```bash
# 在容器内运行测试
docker compose run --rm gateway pytest -q
```

---

## 十一、常见问题排查

### 11.1 服务启动失败

```bash
# 查看服务状态
docker compose ps

# 查看特定服务日志
docker compose logs --tail=100 gateway
docker compose logs --tail=100 mosquitto
```

### 11.2 MQTT 连接问题

- 检查 `passwordfile` 是否存在且权限正确
- 检查 ACL 配置是否允许对应主题操作
- 使用 `mosquitto_sub` 测试连接

### 11.3 数据库连接问题

- 检查 MySQL 是否已启动
- 检查 init.sql 是否正确执行
- 查看网关日志确认数据库连通性

### 11.4 Redis 连接问题

- 检查 `protected-mode` 配置
- 确认 Redis 容器正常运行

---

## 十二、维护与运维

### 12.1 服务管理

```bash
# 启动所有服务
docker compose up -d

# 停止所有服务
docker compose down

# 重启特定服务
docker compose restart gateway

# 查看服务日志
docker compose logs -f gateway

# 更新服务
docker compose up -d --build gateway
```

### 12.2 数据备份

```bash
# 备份 MySQL 数据
docker compose exec mysql mysqldump -uroot -prootpassword iot_db > backup.sql

# 备份数据目录
tar czf data-backup.tar.gz data/
```

### 12.3 清理无用数据

```bash
# 清理 Redis 数据（重启容器即可）
docker compose restart redis

# 清理 Docker 无用数据
docker system prune -a
```

---

## 十三、安全建议

1. **修改默认密码**:
   - MySQL root 密码
   - MQTT 用户密码
   - API_TOKEN

2. **防火墙规则**: 仅允许特定 IP 访问 1883 和 8000 端口

3. **HTTPS**: 在生产环境中使用反向代理（如 Nginx）启用 HTTPS

4. **认证**: 为所有 API 接口添加身份验证

5. **日志监控**: 定期检查服务日志，设置告警

---

## 十四、下一步开发

- [ ] Modbus 驱动与 PLC 实际通信
- [ ] HMI 前端界面
- [ ] 实时数据可视化
- [ ] 告警和通知机制
- [ ] 数据导出功能
- [ ] 用户权限管理

---

## 版本历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-04-20 | 1.0 | 初始版本，完成最小闭环部署 |
