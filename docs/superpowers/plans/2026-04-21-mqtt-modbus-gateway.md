# MQTT-Modbus 控制指令网关端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在边缘网关端实现基于自定义 JSON 协议的 MQTT 到 Modbus TCP 的控制指令转发与应答闭环。

**Architecture:** 网关作为 MQTT 客户端订阅 `cmd/modbus/+/write` 主题，解析 JSON 负载中的 Modbus 参数，通过异步 Modbus TCP 客户端写入底层 PLC，并将执行结果封装为 JSON 发布到 `cmd/modbus/{device_id}/write_reply`。

**Tech Stack:** Python 3, `paho-mqtt` (MQTT 客户端), `pymodbus` (Modbus TCP 客户端), `asyncio` (异步处理)。

---

### Task 1: 建立基础的项目结构和配置

**Files:**
- Create: `gateway/requirements.txt`
- Create: `gateway/config.py`
- Create: `gateway/main.py`

- [ ] **Step 1: 创建依赖文件**

```text
paho-mqtt>=2.0.0
pymodbus>=3.6.0
```

- [ ] **Step 2: 创建配置文件**

```python
import os

class Config:
    MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
    MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
    PLC_HOST = os.getenv("PLC_HOST", "127.0.0.1")
    PLC_PORT = int(os.getenv("PLC_PORT", 502))
    GATEWAY_ID = os.getenv("GATEWAY_ID", "gw_01")
```

- [ ] **Step 3: 创建应用入口占位**

```python
import asyncio
from config import Config

async def main():
    print(f"Gateway {Config.GATEWAY_ID} starting...")

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Commit**

```bash
git add gateway/
git commit -m "chore: setup gateway project structure and config"
```

---

### Task 2: 实现 Modbus TCP 客户端封装

**Files:**
- Create: `gateway/modbus_client.py`
- Create: `tests/gateway/test_modbus_client.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, patch
from gateway.modbus_client import ModbusHandler

@pytest.mark.asyncio
async def test_write_coil():
    handler = ModbusHandler("127.0.0.1", 502)
    handler.client = AsyncMock()
    handler.client.write_coil.return_value = AsyncMock(isError=lambda: False)
    
    result = await handler.write_data(1, "write_coil", 40001, "bool", 1)
    assert result == True
    handler.client.write_coil.assert_called_with(40001, True, slave=1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/gateway/test_modbus_client.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'gateway.modbus_client')

- [ ] **Step 3: Write minimal implementation**

```python
from pymodbus.client import AsyncModbusTcpClient
import struct

class ModbusHandler:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.client = AsyncModbusTcpClient(self.host, port=self.port)

    async def connect(self):
        await self.client.connect()

    async def write_data(self, slave_id: int, action: str, address: int, data_type: str, value) -> bool:
        try:
            if action == "write_coil" and data_type == "bool":
                val = bool(value)
                res = await self.client.write_coil(address, val, slave=slave_id)
                return not res.isError()
            
            elif action == "write_register" and data_type in ["int16", "uint16"]:
                val = int(value)
                res = await self.client.write_register(address, val, slave=slave_id)
                return not res.isError()
                
            elif action == "write_multiple" and data_type == "float32":
                # Convert float32 to two 16-bit registers (Big Endian)
                b = struct.pack('>f', float(value))
                regs = struct.unpack('>HH', b)
                res = await self.client.write_registers(address, list(regs), slave=slave_id)
                return not res.isError()
                
            return False
        except Exception as e:
            print(f"Modbus write error: {e}")
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/gateway/test_modbus_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/modbus_client.py tests/gateway/test_modbus_client.py
git commit -m "feat: implement modbus tcp write handler"
```

---

### Task 3: 实现 MQTT 客户端与指令解析分发

**Files:**
- Create: `gateway/mqtt_client.py`
- Modify: `gateway/main.py:1-8`

- [ ] **Step 1: 实现 MQTT 处理逻辑**

```python
import json
import asyncio
import time
import paho.mqtt.client as mqtt
from gateway.modbus_client import ModbusHandler

class MQTTGateway:
    def __init__(self, broker: str, port: int, modbus_handler: ModbusHandler):
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.broker = broker
        self.port = port
        self.modbus = modbus_handler
        # 简单使用 asyncio.Queue 将回调桥接到异步循环
        self.msg_queue = asyncio.Queue()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        print(f"Connected to MQTT Broker with code {reason_code}")
        client.subscribe("cmd/modbus/+/write", qos=1)

    def on_message(self, client, userdata, msg):
        # 提取 device_id
        topic_parts = msg.topic.split('/')
        if len(topic_parts) >= 3:
            device_id = topic_parts[2]
            self.msg_queue.put_nowait((device_id, msg.payload))

    async def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()
        
    async def process_messages(self):
        while True:
            device_id, payload = await self.msg_queue.get()
            await self.handle_command(device_id, payload)
            
    async def handle_command(self, device_id: str, payload: bytes):
        try:
            data = json.loads(payload)
            msg_id = data["msg_id"]
            
            # 执行 Modbus 写入
            success = await self.modbus.write_data(
                slave_id=data["slave_id"],
                action=data["action"],
                address=data["address"],
                data_type=data["data_type"],
                value=data["value"]
            )
            
            # 构造应答
            reply = {
                "msg_id": msg_id,
                "timestamp": int(time.time() * 1000),
                "status": "success" if success else "error",
                "error_code": 0 if success else 3,
                "message": "OK" if success else "Modbus write failed"
            }
            
            reply_topic = f"cmd/modbus/{device_id}/write_reply"
            self.client.publish(reply_topic, json.dumps(reply), qos=1, retain=False)
            print(f"Replied to {reply_topic}: {reply['status']}")
            
        except Exception as e:
            print(f"Error handling command: {e}")
```

- [ ] **Step 2: 组装 Main 函数**

```python
import asyncio
from config import Config
from modbus_client import ModbusHandler
from mqtt_client import MQTTGateway

async def main():
    print(f"Gateway starting...")
    modbus = ModbusHandler(Config.PLC_HOST, Config.PLC_PORT)
    await modbus.connect()
    
    gateway = MQTTGateway(Config.MQTT_BROKER, Config.MQTT_PORT, modbus)
    await gateway.start()
    
    # 保持运行并处理消息
    await gateway.process_messages()

if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Commit**

```bash
git add gateway/mqtt_client.py gateway/main.py
git commit -m "feat: integrate mqtt client and message processing loop"
```
