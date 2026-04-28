import json

import pytest

from app.services.command_service import CommandService
from app.services.modbus_service import ModbusService


class DummyRedis:
    def __init__(self) -> None:
        self.kv = {}
        self.list_data = {}
        self.calls = []

    async def setex(self, key, ttl, value):
        self.calls.append(("setex", key, ttl))
        self.kv[key] = value

    async def lpush(self, key, value):
        self.calls.append(("lpush", key))
        self.list_data.setdefault(key, []).insert(0, value)

    async def ltrim(self, key, start, end):
        self.calls.append(("ltrim", key, start, end))
        self.list_data[key] = self.list_data.get(key, [])[start : end + 1]

    async def get(self, key):
        return self.kv.get(key)

    async def lrange(self, key, start, end):
        return self.list_data.get(key, [])[start : end + 1]


class DummyMQTT:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))


@pytest.mark.anyio
async def test_process_command_new_topic_success(monkeypatch):
    redis = DummyRedis()
    mqtt = DummyMQTT()
    called = {"count": 0}

    async def fake_execute_write(params):
        called["count"] += 1
        assert params["function_code"] == "0x06"

    monkeypatch.setattr("app.services.command_service.redis_client", redis)
    monkeypatch.setattr("app.services.command_service.mqtt_client", mqtt)
    monkeypatch.setattr("app.services.command_service.ModbusService.execute_write", fake_execute_write)

    payload = {
        "command_id": "cmd-1",
        "batch_id": "batch-1",
        "device_code": "DEV-001",
        "command_type": "START",
        "params": {
            "host": "127.0.0.1",
            "port": 502,
            "unit_id": 1,
            "function_code": "0x06",
            "offset": 2,
            "data": 1,
        },
        "source": {"client_id": "hmi-terminal-01"},
    }
    await CommandService.process_command(
        "iot/v1/command/device/DEV-001", json.dumps(payload).encode("utf-8")
    )

    assert called["count"] == 1
    assert "command:DEV-001" in redis.kv
    assert len(mqtt.published) == 1
    topic, body, _ = mqtt.published[0]
    assert topic == "iot/v1/command-result/device/DEV-001"
    result = json.loads(body)
    assert result["result_code"] == "EXECUTED"
    assert result["stage"] == "executed"


@pytest.mark.anyio
async def test_process_command_ignores_old_topic(monkeypatch):
    redis = DummyRedis()
    mqtt = DummyMQTT()

    async def fake_execute_write(_params):
        raise AssertionError("should not execute modbus on old topic")

    monkeypatch.setattr("app.services.command_service.redis_client", redis)
    monkeypatch.setattr("app.services.command_service.mqtt_client", mqtt)
    monkeypatch.setattr("app.services.command_service.ModbusService.execute_write", fake_execute_write)

    await CommandService.process_command("command/plc/DEV-001", b'{"command_type":"START"}')
    assert redis.calls == []
    assert mqtt.published == []


@pytest.mark.anyio
async def test_process_command_publish_failed_when_modbus_error(monkeypatch):
    redis = DummyRedis()
    mqtt = DummyMQTT()

    async def fake_execute_write(_params):
        raise RuntimeError("modbus unavailable")

    monkeypatch.setattr("app.services.command_service.redis_client", redis)
    monkeypatch.setattr("app.services.command_service.mqtt_client", mqtt)
    monkeypatch.setattr("app.services.command_service.ModbusService.execute_write", fake_execute_write)

    payload = {
        "command_id": "cmd-2",
        "device_code": "DEV-002",
        "command_type": "STOP",
        "params": {
            "host": "127.0.0.1",
            "function_code": "0x05",
            "offset": 1,
            "data": 0,
        },
    }
    await CommandService.process_command(
        "iot/v1/command/device/DEV-002", json.dumps(payload).encode("utf-8")
    )
    assert len(mqtt.published) == 1
    topic, body, _ = mqtt.published[0]
    assert topic == "iot/v1/command-result/device/DEV-002"
    result = json.loads(body)
    assert result["result_code"] == "FAILED"
    assert result["stage"] == "failed"


@pytest.mark.anyio
async def test_send_command_publish_new_topic(monkeypatch):
    mqtt = DummyMQTT()
    monkeypatch.setattr("app.services.command_service.mqtt_client", mqtt)

    ok = await CommandService.send_command(
        "DEV-003",
        "START",
        {"host": "127.0.0.1", "function_code": "0x06", "offset": 0, "data": 1},
        command_id="cmd-3",
        batch_id="batch-3",
        source={"client_id": "hmi-http"},
        ts="2026-04-28T00:00:00Z",
    )
    assert ok is True
    assert len(mqtt.published) == 1
    topic, body, _ = mqtt.published[0]
    assert topic == "iot/v1/command/device/DEV-003"
    command = json.loads(body)
    assert command["command_type"] == "START"
    assert command["command_id"] == "cmd-3"


@pytest.mark.anyio
async def test_modbus_service_retry_three_times(monkeypatch):
    attempts = {"count": 0}

    async def fake_single_execute(_params):
        attempts["count"] += 1
        raise RuntimeError("write failed")

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(ModbusService, "_single_execute", fake_single_execute)
    monkeypatch.setattr("app.services.modbus_service.asyncio.sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="after 3 retries"):
        await ModbusService.execute_write(
            {"host": "127.0.0.1", "function_code": "0x06", "offset": 1, "data": 2}
        )
    assert attempts["count"] == 3
