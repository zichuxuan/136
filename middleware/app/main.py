from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import text

from app.api.router import router
from app.core.db import engine
from app.core.mqtt_client import mqtt_client
from app.services.telemetry_service import TelemetryService
from app.services.command_service import CommandService
from app.services.plc_polling_service import PLCPollingService


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))

    mqtt_client.subscribe("telemetry/plc/+", TelemetryService.process_telemetry)
    mqtt_client.subscribe("event/plc/+", TelemetryService.process_event)
    mqtt_client.subscribe("iot/v1/command/device/+", CommandService.process_command)

    await mqtt_client.connect()
    poller = PLCPollingService()
    await poller.start()

    yield

    await poller.stop()
    await mqtt_client.disconnect()
    await engine.dispose()


# Development mode enabled with hot-reload
app = FastAPI(title="IPC Gateway", lifespan=lifespan)
app.include_router(router)
