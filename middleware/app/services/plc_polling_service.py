import asyncio
import json
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.mqtt_client import mqtt_client
from app.models.device import DeviceAction, DeviceInstance
from app.services.modbus_service import ModbusService


class PLCPollingService:
    def __init__(
        self,
        *,
        session_factory=SessionLocal,
        mqtt=mqtt_client,
        modbus=ModbusService,
        enabled: bool | None = None,
        default_interval_s: int | None = None,
        max_inflight: int | None = None,
        timeout_s: float | None = None,
        db_refresh_s: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._mqtt = mqtt
        self._modbus = modbus
        self._enabled = settings.PLC_POLL_ENABLED if enabled is None else enabled
        self._default_interval_s = (
            settings.PLC_POLL_DEFAULT_INTERVAL_S
            if default_interval_s is None
            else default_interval_s
        )
        self._timeout_s = settings.PLC_POLL_TIMEOUT_S if timeout_s is None else timeout_s
        self._db_refresh_s = settings.PLC_POLL_DB_REFRESH_S if db_refresh_s is None else db_refresh_s
        self._semaphore = asyncio.Semaphore(
            settings.PLC_POLL_MAX_INFLIGHT if max_inflight is None else max_inflight
        )

        self._task: asyncio.Task | None = None
        self._inflight: set[asyncio.Task] = set()
        self._logger = self._create_logger()
        self._failures: dict[str, int] = {}

    def _create_logger(self) -> logging.Logger:
        logger = logging.getLogger("plc_polling")
        if logger.handlers:
            return logger

        logger.setLevel(logging.DEBUG)
        app_dir = Path(__file__).resolve().parent.parent
        log_dir = app_dir / "log"
        log_dir.mkdir(parents=True, exist_ok=True)

        fmt = logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        log_file = log_dir / "plc_polling.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
        logger.propagate = False

        try:
            os.chmod(log_file, 0o666)
        except OSError:
            pass

        return logger

    async def start(self) -> None:
        if not self._enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._run())
        self._logger.info("polling started")

    async def stop(self) -> None:
        if self._task is None:
            return

        for t in list(self._inflight):
            t.cancel()
        await asyncio.gather(*list(self._inflight), return_exceptions=True)
        self._inflight.clear()

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._logger.info("polling stopped")

    def _spawn(self, coro: Any) -> None:
        t = asyncio.create_task(coro)
        self._inflight.add(t)
        t.add_done_callback(self._inflight.discard)

    async def _run(self) -> None:
        last_run: dict[int, float] = {}
        configs: list[dict[str, Any]] = []
        next_refresh = 0.0
        loop = asyncio.get_running_loop()

        while True:
            now = loop.time()
            if now >= next_refresh:
                configs = await self._load_configs()
                next_refresh = now + float(self._db_refresh_s)

            for cfg in configs:
                action_id = int(cfg["action_id"])
                interval_s = float(cfg.get("interval_s") or self._default_interval_s)
                last = last_run.get(action_id, 0.0)
                if now - last >= interval_s:
                    last_run[action_id] = now
                    self._spawn(self._poll_once(cfg))

            await asyncio.sleep(0.2)

    async def _load_configs(self) -> list[dict[str, Any]]:
        async with self._session_factory() as db:
            stmt = (
                select(
                    DeviceAction.id,
                    DeviceAction.action_command_params,
                    DeviceInstance.device_code,
                )
                .join(DeviceInstance, DeviceAction.device_instance_id == DeviceInstance.id)
                .where(DeviceAction.is_deleted == False, DeviceInstance.is_deleted == False)
            )
            result = await db.execute(stmt)
            rows = result.all()

        configs: list[dict[str, Any]] = []
        for action_id, params, device_code in rows:
            if not isinstance(params, dict):
                continue
            polling = params.get("polling") if isinstance(params.get("polling"), dict) else {}
            if polling.get("enabled") is not True:
                continue
            interval_s = polling.get("interval_s", self._default_interval_s)
            cfg = self._build_cfg(int(action_id), str(device_code), params, interval_s)
            if cfg is not None:
                configs.append(cfg)
        return configs

    def _build_cfg(
        self, action_id: int, device_code: str, params: dict[str, Any], interval_s: Any
    ) -> dict[str, Any] | None:
        modbus = params.get("modbus") if isinstance(params.get("modbus"), dict) else None
        host = None
        port = None
        unit_id = None
        reads = None

        if modbus:
            host = modbus.get("host")
            port = modbus.get("port")
            unit_id = modbus.get("unit_id")
            reads = modbus.get("reads")

        if host is None:
            host = params.get("host")
            port = params.get("port")
            unit_id = params.get("unit_id")

        if not host:
            return None

        if not isinstance(reads, list):
            function_code = params.get("function_code")
            offset = params.get("offset")
            count = params.get("count", params.get("data"))
            if function_code is None or offset is None or count is None:
                return None
            reads = [{"function_code": function_code, "offset": offset, "count": count, "key": "read"}]

        normalized_reads: list[dict[str, Any]] = []
        for r in reads:
            if not isinstance(r, dict):
                continue
            if r.get("function_code") is None or r.get("offset") is None:
                continue
            cnt = r.get("count", r.get("data"))
            if cnt is None:
                continue
            normalized_reads.append(
                {
                    "key": r.get("key") or f'{r.get("function_code")}@{r.get("offset")}',
                    "function_code": r.get("function_code"),
                    "offset": r.get("offset"),
                    "count": cnt,
                }
            )

        if not normalized_reads:
            return None

        return {
            "action_id": action_id,
            "device_code": device_code,
            "interval_s": interval_s,
            "host": host,
            "port": port,
            "unit_id": unit_id,
            "reads": normalized_reads,
        }

    async def _poll_once(self, cfg: dict[str, Any]) -> None:
        device_code = cfg["device_code"]
        async with self._semaphore:
            try:
                host = cfg["host"]
                base = {
                    "host": host,
                    "port": cfg.get("port", 502),
                    "unit_id": cfg.get("unit_id", 1),
                }
                data: dict[str, Any] = {}
                for r in cfg["reads"]:
                    params = {
                        **base,
                        "function_code": r["function_code"],
                        "offset": r["offset"],
                        "count": r["count"],
                    }
                    out = await self._modbus.execute_read(params, timeout_s=self._timeout_s)
                    data[str(r["key"])] = out["values"]

                payload = json.dumps(
                    {
                        "device_code": device_code,
                        "ts": datetime.utcnow().isoformat() + "Z",
                        "data": data,
                    }
                )
                await self._mqtt.publish(f"telemetry/plc/{device_code}", payload)
                self._failures.pop(device_code, None)
            except Exception as exc:  # noqa: BLE001
                n = self._failures.get(device_code, 0) + 1
                self._failures[device_code] = n
                if n == 1 or n % 5 == 0:
                    self._logger.error("poll failed device_code=%s error=%s", device_code, exc)
                    event = json.dumps(
                        {
                            "device_code": device_code,
                            "ts": datetime.utcnow().isoformat() + "Z",
                            "error": str(exc),
                            "stage": "poll_failed",
                        }
                    )
                    await self._mqtt.publish(f"event/plc/{device_code}", event)
