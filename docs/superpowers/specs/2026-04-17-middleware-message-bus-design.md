# 边缘中间件与消息总线架构设计规范 (Design Spec)

## 1. 背景与硬件上下文
*   **硬件平台**：工控机 (Intel Celeron J1900, 8GB RAM, 128GB SSD)
*   **操作系统**：Ubuntu 22.04 LTS Desktop
*   **核心目标**：设计并实现高可用、低延迟的边缘中间件（FastAPI）和消息总线（Mosquitto），支撑上层 PyQt6 终端界面与底层 PLC 设备的数据交互。

## 2. 部署架构决策
鉴于工控机硬件配置（J1900/8G/128G），为保证环境一致性与极简部署，我们采用 **Docker Compose 容器化部署**：
*   **编排管理**：通过统一的 `docker-compose.yml` 声明 FastAPI 网关、Mosquitto、Redis 与 MySQL 8.0。
*   **镜像构建**：FastAPI 提供 `Dockerfile`，使用轻量级 Python 基础镜像（如 `python:3.10-slim`）。
*   **资源管控**：在容器层面硬性限制日志大小与 MySQL 内存占用，防止拖垮宿主机。

### 2.1 跨主机访问拓扑
*   **工控机（边缘节点）**：运行 Mosquitto、FastAPI 网关、Redis、MySQL、Modbus TCP 驱动与轮询任务。
*   **局域网 HMI 主机**：运行 PyQt6 终端程序，通过局域网访问工控机的 HTTP API 与 MQTT Broker。

### 2.2 端口与访问控制
*   **MQTT**：TCP 1883（用户名/密码 + ACL）。
*   **HTTP API**：TCP 8000（应用层 Token/JWT 认证）。
*   **防火墙**：仅对局域网网段放行 1883/8000；MySQL(3306)/Redis(6379) 默认仅绑定 `127.0.0.1`，不对外开放。

## 3. 消息总线层设计 (Mosquitto)
作为整个系统的数据神经中枢，承担终端 (PyQt6) 与网关 (FastAPI) 的异步解耦通信。

### 3.1 核心配置
*   **持久化**：开启 `persistence true`，防止意外断电导致消息队列丢失。
*   **安全认证**：关闭匿名访问 (`allow_anonymous false`)，使用 `mosquitto_passwd` 创建网关专属账号与终端专属账号，并配置 ACL 控制 Topic 读写权限。

### 3.2 Topic 空间规划
遵循 `层级/业务/设备` 的 RESTful 风格订阅主题：
*   `telemetry/plc/{device_id}`：**网关 -> 终端**。发布设备高频轮询的实时遥测数据（JSON 格式）。
*   `command/plc/{device_id}`：**终端 -> 网关**。发布控制指令（如启动、停止、参数下发）。
*   `gateway/status`：网关系统健康状态。利用 MQTT 的遗嘱消息 (LWT)，网关意外掉线时自动向该 Topic 发布 `offline` 状态。

## 4. 边缘中间件层设计 (FastAPI)
中间件层是业务逻辑的核心，负责设备协议转换、数据缓存与 API 提供。

### 4.1 异步并发模型 (Asyncio)
J1900 为 4 核心低功耗 CPU，传统多线程模型切换开销大。我们全面采用 **Python Asyncio 异步协程**，在单进程/少进程下榨干 I/O 性能：
*   **Modbus 通信**：使用 `pymodbus.client.AsyncModbusTcpClient`。
*   **MQTT 通信**：使用 `aiomqtt` (基于 `paho-mqtt` 的异步封装)。
*   **数据库通信**：使用 `SQLAlchemy` (异步引擎 `asyncio`) + `aiomysql`，以及 `redis.asyncio`。

### 4.2 核心后台任务 (Background Tasks)
FastAPI 启动时（基于 `Lifespan` 事件），将拉起以下常驻异步协程：
1.  **Modbus 轮询协程 (`asyncio.gather`)**：以设定频率（如 100ms）并发读取多台 PLC 的保持寄存器/线圈。
2.  **数据流转协程**：
    *   将轮询到的最新数据序列化，**写入 Redis Hash** (键如 `plc:status:01`)，覆盖旧数据。
    *   当数据发生变化时，**推送到 Mosquitto** `telemetry/` 主题。
3.  **MQTT 监听协程**：持续订阅 `command/` 主题，解析 JSON 指令后，调用 Modbus 异步写操作。
4.  **持久化刷盘协程**：每隔一定周期（如 1 分钟），从 Redis 提取历史状态快照，批量 `INSERT` 到 MySQL 中。

### 4.3 接口设计 (RESTful APIs)
提供标准 HTTP 接口供 PyQt6 终端调用（不要求高实时性的业务）：
*   `GET /api/v1/devices`：查询所有注册设备的基础配置。
*   `GET /api/v1/telemetry/snapshot`：查询当前系统最新实时快照（直接查 Redis，耗时 < 5ms）。
*   `GET /api/v1/history`：分页查询历史运行数据（查 MySQL）。

## 5. 针对 J1900 的 Docker 与性能优化（避坑指南）
1.  **SSD 寿命与容量保护 (Wear Leveling & Log Rotation)**：
    *   128G 固态硬盘怕高频小文件碎片写入与日志撑爆。设备高频轮询状态**绝不**直接写 MySQL，而是更新到全内存的 Redis 中。
    *   **Docker 日志限制**：必须在 `docker-compose.yml` 中配置 `logging` 的 `max-size: "20m"` 和 `max-file: "3"`，防止长年运行日志占满硬盘。
2.  **内存管控**：
    *   Redis 配置 `maxmemory 1gb`，淘汰策略 `allkeys-lru`。
    *   **MySQL 限制**：在 Docker 启动参数中强制添加 `--innodb-buffer-pool-size=1G`，防止数据库吃光 8G 内存导致 Linux 触发 OOM。
