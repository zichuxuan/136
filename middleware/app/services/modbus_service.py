import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from pymodbus.client import AsyncModbusTcpClient


class ModbusService:
    _SUPPORTED_WRITE_FUNCTION_CODES = {"0x05", "0x06", "0x10"}
    _SUPPORTED_READ_FUNCTION_CODES = {"0x01", "0x02", "0x03", "0x04"}
    _MAX_RETRIES = 3
    _logger: logging.Logger | None = None

    @staticmethod
    def _get_logger() -> logging.Logger:
        if ModbusService._logger is not None:
            return ModbusService._logger

        logger = logging.getLogger("modbus_tcp")
        if not logger.handlers:
            logger.setLevel(logging.DEBUG)

            app_dir = Path(__file__).resolve().parent.parent
            log_dir = app_dir / "log"
            log_dir.mkdir(parents=True, exist_ok=True)

            fmt = logging.Formatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )

            log_file = log_dir / "modbus_tcp.log"
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

            pymodbus_logger = logging.getLogger("pymodbus")
            if not pymodbus_logger.handlers:
                pymodbus_logger.setLevel(logging.DEBUG)
                pymodbus_logger.addHandler(file_handler)
                pymodbus_logger.propagate = False

        ModbusService._logger = logger
        return logger

    @staticmethod
    def _normalize_function_code(function_code: Any) -> str:
        if isinstance(function_code, int):
            return f"0x{function_code:02x}"
        if isinstance(function_code, str):
            value = function_code.strip().lower()
            if value.startswith("0x"):
                return value
            if value.isdigit():
                return f"0x{int(value):02x}"
        raise ValueError("Invalid function_code, expected hex string like 0x06")

    @staticmethod
    def _parse_connection(params: dict[str, Any]) -> tuple[str, int, int]:
        host = params.get("host")
        if not host or not isinstance(host, str):
            raise ValueError("Missing required Modbus connection field: host")

        port = int(params.get("port", 502))
        unit_id = int(params.get("unit_id", 1))
        return host, port, unit_id

    @staticmethod
    def _parse_count(params: dict[str, Any]) -> int:
        count = params.get("count")
        if count is None:
            count = params.get("data")
        if count is None:
            raise ValueError("Missing required Modbus read field: count")
        return int(count)

    @staticmethod
    async def _single_execute(params: dict[str, Any]) -> None:
        logger = ModbusService._get_logger()
        host, port, unit_id = ModbusService._parse_connection(params)
        function_code = ModbusService._normalize_function_code(params.get("function_code"))
        offset = int(params.get("offset", 0))
        data = params.get("data")

        if function_code not in ModbusService._SUPPORTED_WRITE_FUNCTION_CODES:
            raise ValueError(
                "Unsupported function_code. Allowed values: 0x05, 0x06, 0x10"
            )

        data_preview = data
        if isinstance(data, list) and len(data) > 50:
            data_preview = data[:50]

        logger.debug(
            "execute start host=%s port=%s unit_id=%s function_code=%s offset=%s data=%s",
            host,
            port,
            unit_id,
            function_code,
            offset,
            data_preview,
        )

        client = AsyncModbusTcpClient(host=host, port=port)
        try:
            connected = await client.connect()
            if not connected:
                raise ConnectionError(f"Failed to connect Modbus TCP {host}:{port}")

            if function_code == "0x05":
                if data is None:
                    raise ValueError("0x05 requires boolean/int data")
                response = await client.write_coil(offset, bool(data), slave=unit_id)
            elif function_code == "0x06":
                if data is None:
                    raise ValueError("0x06 requires integer data")
                response = await client.write_register(offset, int(data), slave=unit_id)
            else:
                if not isinstance(data, list) or not data:
                    raise ValueError("0x10 requires non-empty integer list data")
                values = [int(v) for v in data]
                response = await client.write_registers(offset, values, slave=unit_id)

            if response.isError():
                raise RuntimeError(f"Modbus write failed: {response}")
            logger.debug("execute success response=%s", response)
        except Exception as exc:  # noqa: BLE001
            logger.exception("execute failed: %s", exc)
            raise
        finally:
            client.close()

    @staticmethod
    async def execute_write(params: dict[str, Any]) -> None:
        logger = ModbusService._get_logger()
        last_error: Exception | None = None
        for attempt in range(1, ModbusService._MAX_RETRIES + 1):
            try:
                logger.debug("attempt %s/%s", attempt, ModbusService._MAX_RETRIES)
                await ModbusService._single_execute(params)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < ModbusService._MAX_RETRIES:
                    await asyncio.sleep(0.2)
        logger.error("all retries failed: %s", last_error)
        raise RuntimeError(f"Modbus write failed after 3 retries: {last_error}")

    @staticmethod
    async def _single_read(params: dict[str, Any]) -> dict[str, Any]:
        logger = ModbusService._get_logger()
        host, port, unit_id = ModbusService._parse_connection(params)
        function_code = ModbusService._normalize_function_code(params.get("function_code"))
        offset = int(params.get("offset", 0))
        count = ModbusService._parse_count(params)
        timeout_s = params.get("timeout_s")
        timeout_s = float(timeout_s) if timeout_s is not None else None

        if function_code not in ModbusService._SUPPORTED_READ_FUNCTION_CODES:
            raise ValueError(
                "Unsupported function_code. Allowed values: 0x01, 0x02, 0x03, 0x04"
            )

        logger.debug(
            "read start host=%s port=%s unit_id=%s function_code=%s offset=%s count=%s",
            host,
            port,
            unit_id,
            function_code,
            offset,
            count,
        )

        client = AsyncModbusTcpClient(host=host, port=port)
        try:
            connected = await client.connect()
            if not connected:
                raise ConnectionError(f"Failed to connect Modbus TCP {host}:{port}")

            if function_code == "0x01":
                call = client.read_coils(offset, count, slave=unit_id)
            elif function_code == "0x02":
                call = client.read_discrete_inputs(offset, count, slave=unit_id)
            elif function_code == "0x03":
                call = client.read_holding_registers(offset, count, slave=unit_id)
            else:
                call = client.read_input_registers(offset, count, slave=unit_id)

            response = await asyncio.wait_for(call, timeout=timeout_s) if timeout_s else await call
            if response.isError():
                raise RuntimeError(f"Modbus read failed: {response}")

            if function_code in {"0x01", "0x02"}:
                values = list(getattr(response, "bits", [])[:count])
            else:
                values = list(getattr(response, "registers", [])[:count])

            result = {
                "function_code": function_code,
                "offset": offset,
                "count": count,
                "values": values,
            }
            logger.debug("read success result=%s", result)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.exception("read failed: %s", exc)
            raise
        finally:
            client.close()

    @staticmethod
    async def execute_read(params: dict[str, Any]) -> dict[str, Any]:
        logger = ModbusService._get_logger()
        last_error: Exception | None = None
        for attempt in range(1, ModbusService._MAX_RETRIES + 1):
            try:
                logger.debug("read attempt %s/%s", attempt, ModbusService._MAX_RETRIES)
                return await ModbusService._single_read(params)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < ModbusService._MAX_RETRIES:
                    await asyncio.sleep(0.2)
        logger.error("read all retries failed: %s", last_error)
        raise RuntimeError(f"Modbus read failed after 3 retries: {last_error}")
