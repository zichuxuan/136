import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.mqtt_client import mqtt_client
from app.models.device import DeviceAction, DeviceInstance
from app.services.modbus_service import ModbusService


@dataclass(frozen=True)
class _PollingRead:
    function_code: str
    offset: int
    count: int
    key: str


@dataclass(frozen=True)
class _PollingTarget:
    action_id: int
    device_code: str
    action_name: str
    interval_s: float
    host: str
    port: int
    unit_id: int
    reads: tuple[_PollingRead, ...]


class PLCPollingService:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._inflight: set[int] = set()

    async def start(self) -> None:
        enabled = getattr(settings, "PLC_POLL_ENABLED", True)
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return

        if self._task and not self._task.done():
            return

        max_inflight = int(getattr(settings, "PLC_POLL_MAX_INFLIGHT", 10))
        self._semaphore = asyncio.Semaphore(max_inflight)
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._semaphore = None
        self._inflight.clear()

    async def _loop(self) -> None:
        db_refresh_s = float(getattr(settings, "PLC_POLL_DB_REFRESH_S", 30))
        tick_s = 0.2
        last_refresh = 0.0
        targets: list[_PollingTarget] = []
        last_run: dict[int, float] = {}

        while True:
            now = time.monotonic()
            if (not targets) or (now - last_refresh >= db_refresh_s):
                targets = await self._load_targets()
                last_refresh = now

            for target in targets:
                previous = last_run.get(target.action_id, 0.0)
                if now - previous < target.interval_s:
                    continue
                if target.action_id in self._inflight:
                    continue
                self._inflight.add(target.action_id)
                last_run[target.action_id] = now
                asyncio.create_task(self._poll_once(target))

            await asyncio.sleep(tick_s)

    async def _poll_once(self, target: _PollingTarget) -> None:
        try:
            if not self._semaphore:
                return
            async with self._semaphore:
                payload = await self._read_target(target)
                await mqtt_client.publish(
                    f"telemetry/plc/{target.device_code}",
                    json.dumps(payload, ensure_ascii=False),
                )
        finally:
            self._inflight.discard(target.action_id)

    async def _read_target(self, target: _PollingTarget) -> dict[str, Any]:
        timeout_s = float(getattr(settings, "PLC_POLL_TIMEOUT_S", 1))
        readings: dict[str, Any] = {}
        for read in target.reads:
            result = await ModbusService.execute_read(
                {
                    "host": target.host,
                    "port": target.port,
                    "unit_id": target.unit_id,
                    "function_code": read.function_code,
                    "offset": read.offset,
                    "count": read.count,
                    "timeout_s": timeout_s,
                }
            )
            readings[read.key] = result["values"]

        return {
            "device_code": target.device_code,
            "action_id": target.action_id,
            "action_name": target.action_name,
            "readings": readings,
            "source": {"client_id": "gateway-poller", "protocol": "modbus-tcp"},
        }

    async def _load_targets(self) -> list[_PollingTarget]:
        default_interval = float(getattr(settings, "PLC_POLL_DEFAULT_INTERVAL_S", 2))
        stmt = (
            select(DeviceAction, DeviceInstance.device_code)
            .join(DeviceInstance, DeviceInstance.id == DeviceAction.device_instance_id)
            .where(DeviceAction.is_deleted == False, DeviceInstance.is_deleted == False)
        )

        async with SessionLocal() as db:
            result = await db.execute(stmt)
            rows = result.all()

        targets: list[_PollingTarget] = []
        for action, device_code in rows:
            params = action.action_command_params
            if not isinstance(params, dict):
                continue

            polling = params.get("polling")
            if not isinstance(polling, dict) or not polling.get("enabled"):
                continue

            interval_s = float(polling.get("interval_s", default_interval))

            try:
                host, port, unit_id = self._extract_connection(params)
                reads = self._extract_reads(params)
                if not reads:
                    continue
            except Exception:
                continue

            targets.append(
                _PollingTarget(
                    action_id=action.id,
                    device_code=device_code,
                    action_name=action.action_name or "",
                    interval_s=interval_s,
                    host=host,
                    port=port,
                    unit_id=unit_id,
                    reads=tuple(reads),
                )
            )
        return targets

    def _extract_connection(self, params: dict[str, Any]) -> tuple[str, int, int]:
        modbus = params.get("modbus")
        if isinstance(modbus, dict):
            host = modbus.get("host")
            if isinstance(host, str) and host.strip():
                port = int(modbus.get("port", 502))
                unit_id = int(modbus.get("unit_id", 1))
                return host, port, unit_id

        host = params.get("host")
        if not isinstance(host, str) or not host.strip():
            raise ValueError("polling action missing modbus host")
        port = int(params.get("port", 502))
        unit_id = int(params.get("unit_id", 1))
        return host, port, unit_id

    def _extract_reads(self, params: dict[str, Any]) -> list[_PollingRead]:
        modbus = params.get("modbus")
        reads_obj = modbus.get("reads") if isinstance(modbus, dict) else None

        reads: list[_PollingRead] = []
        if isinstance(reads_obj, list):
            for idx, item in enumerate(reads_obj):
                if not isinstance(item, dict):
                    continue
                function_code = item.get("function_code")
                if function_code is None:
                    continue
                offset = int(item.get("offset", 0))
                count = int(item.get("count", item.get("data", 1)))
                key = item.get("key") or f"read_{idx}"
                reads.append(_PollingRead(str(function_code), offset, count, str(key)))
            return reads

        function_code = params.get("function_code")
        if function_code is None:
            return reads
        offset = int(params.get("offset", 0))
        count = int(params.get("count", params.get("data", 1)))
        key = params.get("key") or "read_0"
        reads.append(_PollingRead(str(function_code), offset, count, str(key)))
        return reads


plc_polling_service = PLCPollingService()
