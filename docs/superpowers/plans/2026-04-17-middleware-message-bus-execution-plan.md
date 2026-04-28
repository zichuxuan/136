# 中间件层与消息总线执行方案 & 开发计划（工控机边缘部署）

## 0. 范围与目标
本计划仅覆盖工控机侧（边缘中间件层 + 消息总线 + 数据与缓存层）：
*   **消息总线**：Mosquitto MQTT Broker
*   **边缘中间件**：FastAPI 网关（含 MQTT 客户端、Modbus TCP 驱动、Redis 缓存、MySQL 持久化）
*   **数据层**：MySQL 8.0（历史/业务数据），Redis（实时快照/缓冲）
*   **部署形态**：工控机 Ubuntu 22.04 引入 **Docker Compose** 容器化一键部署
*   **客户端**：PyQt6 HMI 运行在局域网另一台主机上，通过 LAN 访问 MQTT + HTTP API

成功标准（Definition of Done）：
*   HMI 主机可通过 MQTT 收到实时遥测（低延迟、可持续订阅）。
*   HMI 主机可通过 MQTT 下发控制指令，网关可将指令可靠映射为 Modbus 写入并返回执行结果（可选 topic）。
*   HMI 主机可通过 HTTP API 查询设备清单、实时快照（来自 Redis）与历史数据（来自 MySQL）。
*   工控机断网/重启后服务可自恢复：systemd 自启；MQTT 遗嘱状态正确；缓存与落库任务可继续运行。

## 1. 网络与安全执行方案
采用“账号密码 + ACL + 局域网放行”：
*   **MQTT**：1883/TCP，启用用户名/密码认证 + ACL
*   **HTTP API**：8000/TCP，应用层 Token/JWT（最小实现可先用静态 Token）
*   **防火墙**：仅允许局域网网段访问 1883/8000；MySQL(3306)/Redis(6379) 仅监听 127.0.0.1

建议的端口策略：
*   Mosquitto `listener 1883 0.0.0.0`
*   FastAPI `--host 0.0.0.0 --port 8000`
*   MySQL/Redis 默认仅本机

## 2. 消息总线与 Docker 基础设施执行方案
### 2.1 编写 `docker-compose.yml`
作为环境交付的核心，定义所有中间件组件并做好资源隔离：
*   **网络隔离**：创建内部网络 `iot-net`。
*   **Mosquitto**：暴露 1883 端口，挂载 `./config/mosquitto.conf` 和日志目录。限制 `logging: max-size: "10m"`。
*   **MySQL 8.0**：仅在内部网络暴露，挂载数据卷 `./data/mysql`。必须添加启动参数 `--innodb-buffer-pool-size=1G` 防止吃满内存。
*   **Redis**：仅在内部网络暴露，通过 `redis.conf` 限制 `maxmemory 1gb`。
*   **FastAPI 网关**：通过 `Dockerfile` 构建基于 `python:3.10-slim` 的镜像，依赖内部 `mysql` 和 `redis` 服务启动。暴露 8000 端口。

### 2.2 Broker 配置关键项
*   关闭匿名：`allow_anonymous false`
*   账号体系：`mosquitto_passwd` 维护 `gateway` 与 `hmi` 两类账号，密码文件挂载进容器。
*   ACL：按角色授权 Topic 读写。
*   持久化：挂载 `./data/mosquitto` 到容器内，防止断电丢消息。

### 2.3 Topic 规范（最终版）
以设备为中心的统一命名空间：
*   **遥测上行（网关 -> HMI）**：`telemetry/plc/{device_id}`
*   **控制下行（HMI -> 网关）**：`command/plc/{device_id}`
*   **指令结果回执（网关 -> HMI，可选）**：`event/plc/{device_id}/command_result`
*   **网关健康状态**：`gateway/status`

消息建议字段（JSON）：
*   telemetry：`device_id`, `ts_ms`, `seq`, `payload`（payload 内为点位数据）
*   command：`cmd_id`, `device_id`, `ts_ms`, `action`, `params`
*   command_result：`cmd_id`, `device_id`, `ts_ms`, `ok`, `error`, `duration_ms`

QoS 建议：
*   telemetry：QoS 0（高频、允许丢包）
*   command：QoS 1（尽量送达）
*   command_result：QoS 1（便于 UI 展示执行反馈）
*   gateway/status：QoS 1 + retain（保留最后状态）

## 3. 边缘网关（FastAPI）执行方案
### 3.1 进程模型
单机边缘节点上推荐：
*   FastAPI 单实例（1 进程）+ asyncio 常驻后台任务
*   如 PLC 数量增长且轮询与 API 互相影响，再升级为多进程或拆分轮询进程

### 3.2 网关模块拆分（建议目录）
*   `app/core/`：配置、日志、生命周期、鉴权
*   `app/api/`：REST API（设备注册、快照、历史）
*   `app/mqtt/`：MQTT 客户端（订阅 command、发布 telemetry/status/result）
*   `app/plc/`：Modbus TCP 驱动与点位映射
*   `app/cache/`：Redis 快照与缓冲队列
*   `app/persistence/`：MySQL 落库（批量写入、保留策略）
*   `app/services/`：轮询调度、指令执行编排、数据流转

### 3.3 数据流执行细节
**轮询主链路（高频）**：
1. Modbus 轮询读取 PLC 点位
2. 生成统一 telemetry payload（结构化 JSON）
3. 写入 Redis 快照（覆盖式更新）
4. 发布 MQTT telemetry（按策略：全量定时 + 变化触发）

**控制指令链路（低频但要求可靠）**：
1. MQTT 订阅 `command/plc/{device_id}`（QoS1）
2. 校验 cmd（schema 校验、权限校验、幂等检查）
3. 转换为 Modbus 写入（必要时串行化写操作）
4. 发布 `command_result`（QoS1）
5. 可选：写入 MySQL 指令审计表

**历史落库链路（低频批量）**：
*   Redis 作为缓冲：使用 List/Stream（推荐 Stream，具备 consumer group）
*   定时任务批量写 MySQL（每 N 秒或累计 M 条）
*   失败重试：写入失败时不 ACK（Stream）或回退到重试队列

### 3.4 Redis Key 规范
*   最新快照（Hash 或 String JSON）：
    *   `plc:snapshot:{device_id}` -> JSON
*   在线状态：
    *   `plc:online:{device_id}` -> `0/1`
    *   `plc:last_seen_ms:{device_id}` -> ts
*   历史缓冲（推荐 Stream）：
    *   `plc:history_stream:{device_id}`（条目为 telemetry 或压缩后的点位子集）

### 3.5 MySQL Schema（最小集合）
*   `devices`：设备注册（唯一事实来源）
*   `plc_history`：历史遥测（可分区/按月归档）
*   `command_audit`（可选）：指令审计与追溯

### 3.6 Docker 服务化（交付标准）
交付核心为 `docker-compose.yml` 及配套环境目录。
*   一键启动：`docker-compose up -d`
*   重启策略：所有服务配置 `restart: always`。
健康检查建议：
*   在 `docker-compose.yml` 为 FastAPI 容器配置 `healthcheck`，定时 `curl http://localhost:8000/healthz`，确保服务卡死时被 Docker 引擎自动重启。

## 4. 详细开发计划（里程碑 + 任务拆解）
### Milestone A：基础设施与可连通性
交付物：
*   Mosquitto 启用账号密码 + ACL，HMI 主机可连通订阅/发布（用 mosquitto_sub/pub 验证）
*   FastAPI 空壳服务（/healthz）可被 HMI 主机访问

任务清单：
*   A1 Mosquitto 安装、基础配置、账号创建、ACL 配置
*   A2 UFW/防火墙策略：仅 LAN 放行 1883/8000
*   A3 FastAPI 项目骨架（lifespan、配置、日志、healthz）
验收：
*   HMI 主机：可 `mosquitto_sub -h <ipc-ip> -u hmi ...`
*   HMI 主机：可 `curl http://<ipc-ip>:8000/healthz`

### Milestone B：设备注册与数据面最小闭环
交付物：
*   `devices` 表 + 设备注册 API（增/改/查）
*   Redis 快照读写 + `/api/v1/telemetry/snapshot`（或 `/devices/{id}/state`）

任务清单：
*   B1 MySQL 连接、迁移/建表策略（最小实现可启动时建表）
*   B2 设备注册 API 与数据校验
*   B3 Redis 客户端与快照 Key 规范
验收：
*   通过 API 注册设备后，网关能读取设备清单并写入快照（先用模拟数据）

### Milestone C：Modbus 轮询引擎
交付物：
*   可按设备清单对多台 PLC 启停轮询
*   轮询结果写入 Redis 快照

任务清单：
*   C1 Async Modbus driver（连接管理、重连、超时）
*   C2 点位映射（mapping_version -> 寄存器定义）
*   C3 轮询调度（设备级任务、频率配置、背压）
验收：
*   断开 PLC 网络时：不会拖垮 API；会记录 offline 并触发重连

### Milestone D：MQTT 遥测发布
交付物：
*   网关将 Redis 快照变化/定时全量发布到 `telemetry/plc/{device_id}`
*   HMI 可持续订阅并展示

任务清单：
*   D1 MQTT 客户端（连接、重连、LWT、retain 规则）
*   D2 发布策略：变化触发 + 周期全量（防止漏帧）
验收：
*   在网络抖动下，HMI 仍能恢复订阅并继续收到消息

### Milestone E：MQTT 指令下发与执行回执
交付物：
*   HMI 发布 `command/plc/{device_id}`（QoS1），网关执行 Modbus 写入
*   网关发布 `event/.../command_result` 返回执行结果

任务清单：
*   E1 指令 schema 与幂等（cmd_id 去重窗口）
*   E2 写操作串行化与安全校验（白名单 action）
*   E3 回执 topic 与错误码规范
验收：
*   同一 cmd_id 重复投递不会重复写入

### Milestone F：历史落库与查询
交付物：
*   Redis 缓冲 + 定时批量落库 MySQL
*   历史查询 API（分页/时间范围）

任务清单：
*   F1 Stream/List 缓冲实现
*   F2 批量写入与失败重试
*   F3 API 查询与索引优化（device_id + ts）
验收：
*   断电重启后：历史链路可继续写入；数据不乱序或可容忍

## 5. 风险与应对
*   **J1900 性能瓶颈**：轮询频率过高导致 CPU 飙升
    *   应对：分设备频率配置；仅变化发布；必要时降低点位数量或采用批量读
*   **SSD 写放大**：频繁写 MySQL 导致 SSD 损耗
    *   应对：Redis 缓冲 + 批量落库；历史表分区/归档；开启合理的 binlog 策略
*   **网络抖动**：HMI 与工控机间 MQTT/HTTP 断连
    *   应对：MQTT 重连 + retain + 周期全量；HTTP 客户端重试与超时
*   **安全边界**：局域网仍可能存在非授权主机
    *   应对：ACL、Token、UFW 仅放行指定 IP 或网段；审计日志

## 6. 回滚策略
*   配置回滚：mosquitto.conf、aclfile、gateway .env 全部版本化备份
*   数据回滚：MySQL schema 变更采用可逆迁移；历史表新增字段不破坏旧读
*   服务回滚：systemd unit 使用固定版本路径（如 `/opt/iot-gateway/releases/<ver>`），切换软链回滚

