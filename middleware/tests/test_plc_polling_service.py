import json

import pytest

from app.services.plc_polling_service import PLCPollingService


class DummyResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class DummySession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return DummyResult(self._rows)

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return False


class DummyMQTT:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))


class DummyModbus:
    def __init__(self, *, values=None, raises=None):
        self.values = values or [1, 2]
        self.raises = raises
        self.calls = []

    async def execute_read(self, params, timeout_s=None):
        self.calls.append((params, timeout_s))
        if self.raises:
            raise self.raises
        return {"values": list(self.values)}


@pytest.mark.anyio
async def test_plc_polling_publish_telemetry(monkeypatch):
    rows = [
        (
            1,
            {
                "polling": {"enabled": True, "interval_s": 2},
                "modbus": {
                    "host": "127.0.0.1",
                    "port": 502,
                    "unit_id": 1,
                    "reads": [
                        {"function_code": "0x03", "offset": 2, "count": 2, "key": "status_regs"}
                    ],
                },
            },
            "DEV-001",
        )
    ]
    mqtt = DummyMQTT()
    modbus = DummyModbus(values=[10, 11])

    svc = PLCPollingService(
        session_factory=lambda: DummySession(rows),
        mqtt=mqtt,
        modbus=modbus,
        enabled=True,
        timeout_s=0.1,
        max_inflight=1,
        db_refresh_s=999,
    )

    cfgs = await svc._load_configs()
    assert len(cfgs) == 1
    await svc._poll_once(cfgs[0])

    assert len(mqtt.published) == 1
    topic, payload, _ = mqtt.published[0]
    assert topic == "telemetry/plc/DEV-001"
    body = json.loads(payload)
    assert body["device_code"] == "DEV-001"
    assert body["data"]["status_regs"] == [10, 11]


@pytest.mark.anyio
async def test_plc_polling_publish_event_on_failure():
    rows = [
        (
            1,
            {
                "polling": {"enabled": True, "interval_s": 2},
                "modbus": {
                    "host": "127.0.0.1",
                    "port": 502,
                    "unit_id": 1,
                    "reads": [
                        {"function_code": "0x03", "offset": 2, "count": 2, "key": "status_regs"}
                    ],
                },
            },
            "DEV-002",
        )
    ]
    mqtt = DummyMQTT()
    modbus = DummyModbus(raises=RuntimeError("modbus error"))

    svc = PLCPollingService(
        session_factory=lambda: DummySession(rows),
        mqtt=mqtt,
        modbus=modbus,
        enabled=True,
        timeout_s=0.1,
        max_inflight=1,
        db_refresh_s=999,
    )

    cfgs = await svc._load_configs()
    await svc._poll_once(cfgs[0])

    assert len(mqtt.published) == 1
    topic, payload, _ = mqtt.published[0]
    assert topic == "event/plc/DEV-002"
    body = json.loads(payload)
    assert body["device_code"] == "DEV-002"
    assert body["stage"] == "poll_failed"
