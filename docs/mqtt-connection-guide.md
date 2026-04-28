# MQTT 服务器连接信息说明文档

## 概述

本文档详细说明 IPC 边缘侧技术栈中 MQTT 服务器（Eclipse Mosquitto）的连接信息、配置参数和使用方法。

---

## 服务器基本信息

| 项目 | 信息 |
|------|------|
| **服务类型** | Eclipse Mosquitto MQTT Broker |
| **版本** | 2.1.2 |
| **部署方式** | Docker 容器 |
| **容器名称** | ipc-edge-mosquitto-1 |
| **运行状态** | 运行中 |

---

## 网络连接信息

### 端口配置

| 协议 | 容器端口 | 主机端口 | 监听地址 |
|------|---------|---------|---------|
| MQTT | 1883 | 1883 | 0.0.0.0 (所有接口) |

### 连接地址

根据客户端所在位置，使用以下地址连接：

| 连接场景 | 主机地址 | 端口 | 说明 |
|---------|---------|------|------|
| 本机连接 | `localhost` 或 `127.0.0.1` | 1883 | 同一台机器上的客户端 |
| 局域网连接 | IPC 的 IP 地址 | 1883 | 局域网内其他设备 |
| Docker 容器内 | `mosquitto` 或 `172.18.0.4` | 1883 | 同一 Docker 网络内的容器 |

### Docker 网络信息

| 项目 | 值 |
|------|-----|
| **容器 IP 地址** | 172.18.0.4 |
| **网关** | 172.18.0.1 |
| **MAC 地址** | 5e:84:b8:1f:fd:91 |
| **Docker 网络** | ipc-edge_iot-net |
| **网络别名** | mosquitto, ipc-edge-mosquitto-1 |

---

## 认证配置

### 认证方式

- **允许匿名访问**: 否 (`allow_anonymous false`)
- **认证机制**: 用户名/密码认证
- **密码文件**: `/mosquitto/config/passwordfile`

### 预配置用户

| 用户名 | 用途 | 权限级别 |
|--------|------|---------|
| `gateway` | 网关服务、PLC 数据采集 | 读写遥测数据、读取指令 |
| `hmi` | HMI 人机界面 | 读取遥测数据、下发指令 |

> **注意**: 实际密码存储在 `deploy/mosquitto/passwordfile` 文件中，生产环境请修改默认密码。

---

## 主题与 ACL 访问控制

### 主题命名规范

```
telemetry/plc/{device_id}    # PLC 遥测数据上报
event/plc/{device_id}        # PLC 事件上报
gateway/status               # 网关状态
gateway/heartbeat            # 网关心跳
command/plc/{device_id}      # 下发给 PLC 的指令
```

### 用户权限矩阵

#### gateway 用户权限

| 主题 | 权限 | 说明 |
|------|------|------|
| `telemetry/plc/#` | readwrite | 发布 PLC 遥测数据 |
| `event/plc/#` | readwrite | 发布 PLC 事件 |
| `gateway/status` | readwrite | 发布网关状态 |
| `command/plc/#` | read | 接收下发给 PLC 的指令 |

#### hmi 用户权限

| 主题 | 权限 | 说明 |
|------|------|------|
| `telemetry/plc/#` | read | 订阅 PLC 遥测数据 |
| `event/plc/#` | read | 订阅 PLC 事件 |
| `gateway/status` | read | 订阅网关状态 |
| `command/plc/#` | write | 下发指令给 PLC |

---

## 配置文件说明

### mosquitto.conf 主配置

```conf
persistence true                    # 启用数据持久化
persistence_location /mosquitto/data/  # 持久化数据存储位置
log_dest stdout                     # 日志输出到标准输出

allow_anonymous false               # 禁止匿名访问
password_file /mosquitto/config/passwordfile  # 密码文件路径
acl_file /mosquitto/config/aclfile  # ACL 访问控制文件路径

listener 1883 0.0.0.0              # 监听 1883 端口，所有网络接口
```

### 文件映射关系

| 主机路径 | 容器路径 | 用途 | 权限 |
|---------|---------|------|------|
| `./deploy/mosquitto/mosquitto.conf` | `/mosquitto/config/mosquitto.conf` | 主配置文件 | 只读 |
| `./deploy/mosquitto/aclfile` | `/mosquitto/config/aclfile` | 访问控制列表 | 只读 |
| `./deploy/mosquitto/passwordfile` | `/mosquitto/config/passwordfile` | 用户密码 | 只读 |
| `./data/mosquitto` | `/mosquitto/data` | 持久化数据 | 读写 |

---

## 连接示例

### 使用 mosquitto 客户端工具

#### 订阅主题（HMI 接收数据）

```bash
# 订阅所有 PLC 遥测数据
mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t 'telemetry/plc/+' -v

# 订阅特定设备遥测
mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t 'telemetry/plc/device001' -v

# 订阅所有事件
mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t 'event/plc/+' -v

# 订阅网关状态
mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t 'gateway/status' -v
```

#### 发布消息（PLC/Gateway 上报数据）

```bash
# 发布遥测数据
mosquitto_pub -h localhost -p 1883 -u gateway -P gatewaypassword \
  -t 'telemetry/plc/device001' \
  -m '{"device_id":"device001","timestamp":"2026-04-21T10:00:00","data":{"temperature":26.5,"pressure":101.3}}'

# 发布事件
mosquitto_pub -h localhost -p 1883 -u gateway -P gatewaypassword \
  -t 'event/plc/device001' \
  -m '{"device_id":"device001","event_type":"alarm","message":"温度过高"}'

# 发布网关状态
mosquitto_pub -h localhost -p 1883 -u gateway -P gatewaypassword \
  -t 'gateway/status' \
  -m '{"status":"online","uptime":3600}'
```

#### 下发指令（HMI 发送指令）

```bash
# 下发启动指令
mosquitto_pub -h localhost -p 1883 -u hmi -P hmipassword \
  -t 'command/plc/device001' \
  -m '{"command_type":"start","params":{"speed":100}}'

# 下发停止指令
mosquitto_pub -h localhost -p 1883 -u hmi -P hmipassword \
  -t 'command/plc/device001' \
  -m '{"command_type":"stop"}'
```

### Python 客户端示例

```python
import asyncio
import aiomqtt

async def mqtt_publisher():
    async with aiomqtt.Client(
        hostname="localhost",
        port=1883,
        username="gateway",
        password="gatewaypassword"
    ) as client:
        await client.publish(
            "telemetry/plc/device001",
            payload='{"temperature": 26.5}'
        )

async def mqtt_subscriber():
    async with aiomqtt.Client(
        hostname="localhost",
        port=1883,
        username="hmi",
        password="hmipassword"
    ) as client:
        await client.subscribe("telemetry/plc/+")
        async for message in client.messages:
            print(f"Received: {message.topic} - {message.payload}")

# 运行
asyncio.run(mqtt_publisher())
```

### JavaScript/Node.js 客户端示例

```javascript
const mqtt = require('mqtt');

// 连接配置
const client = mqtt.connect('mqtt://localhost:1883', {
  username: 'hmi',
  password: 'hmipassword'
});

client.on('connect', () => {
  console.log('Connected to MQTT broker');
  
  // 订阅主题
  client.subscribe('telemetry/plc/+', (err) => {
    if (!err) {
      console.log('Subscribed to telemetry/plc/+');
    }
  });
});

client.on('message', (topic, message) => {
  console.log(`Received message on ${topic}: ${message.toString()}`);
});

// 发布消息
function sendCommand(deviceId, command) {
  client.publish(
    `command/plc/${deviceId}`,
    JSON.stringify(command)
  );
}
```

---

## 服务管理命令

### Docker 容器管理

```bash
# 查看容器状态
docker ps | grep mosquitto

# 查看容器日志
docker logs -f ipc-edge-mosquitto-1

# 重启 MQTT 服务
docker restart ipc-edge-mosquitto-1

# 进入容器内部
docker exec -it ipc-edge-mosquitto-1 sh
```

### Docker Compose 管理

```bash
# 启动服务
docker compose up -d mosquitto

# 停止服务
docker compose stop mosquitto

# 重启服务
docker compose restart mosquitto

# 查看日志
docker compose logs -f mosquitto
```

---

## 密码管理

### 生成新密码

```bash
# 使用本地 mosquitto_passwd 工具
sudo mosquitto_passwd -b deploy/mosquitto/passwordfile username password

# 使用 Docker 容器生成
docker run --rm -v "$(pwd)/deploy/mosquitto:/out" eclipse-mosquitto:2 \
  sh -c "mosquitto_passwd -b /out/passwordfile username password"

# 重启服务使配置生效
docker restart ipc-edge-mosquitto-1
```

### 修改现有用户密码

```bash
# 修改 gateway 用户密码
sudo mosquitto_passwd -b deploy/mosquitto/passwordfile gateway newpassword

# 修改 hmi 用户密码
sudo mosquitto_passwd -b deploy/mosquitto/passwordfile hmi newpassword
```

---

## 故障排查

### 常见问题

#### 1. 连接被拒绝

```bash
# 检查服务是否运行
docker ps | grep mosquitto

# 检查端口监听
netstat -tlnp | grep 1883

# 检查防火墙
sudo ufw status
```

#### 2. 认证失败

```bash
# 检查密码文件是否存在
ls -la deploy/mosquitto/passwordfile

# 检查文件权限
chmod 644 deploy/mosquitto/passwordfile

# 验证密码文件格式
cat deploy/mosquitto/passwordfile
```

#### 3. 权限不足（ACL 问题）

```bash
# 检查 ACL 文件
cat deploy/mosquitto/aclfile

# 确认用户权限配置正确
```

#### 4. 客户端无法连接

```bash
# 测试本地连接
mosquitto_sub -h localhost -p 1883 -u hmi -P hmipassword -t test -d

# 测试远程连接（从其他机器）
mosquitto_sub -h <ipc-ip> -p 1883 -u hmi -P hmipassword -t test -d
```

### 日志查看

```bash
# 查看实时日志
docker logs -f ipc-edge-mosquitto-1

# 查看最近 100 行日志
docker logs --tail=100 ipc-edge-mosquitto-1
```

---

## 安全建议

1. **修改默认密码**: 生产环境必须修改 `gateway` 和 `hmi` 用户的默认密码

2. **网络隔离**: 
   - 使用防火墙限制 1883 端口的访问来源
   - 建议仅允许局域网内特定 IP 访问

3. **TLS/SSL 加密**: 生产环境建议启用 TLS 加密通信

4. **定期审计**: 
   - 定期检查 MQTT 日志
   - 监控异常连接和消息发布

5. **访问控制**:
   - 遵循最小权限原则配置 ACL
   - 定期审查用户权限

---

## 相关文档

- [IPC 边缘侧技术栈部署说明](../README-IPC-Edge-Stack.md)
- [Mosquitto 官方文档](https://mosquitto.org/documentation/)
- [MQTT 协议规范](http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/os/mqtt-v3.1.1-os.html)

---

## 版本历史

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-04-21 | 1.0 | 初始版本 |