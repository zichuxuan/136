from fastapi import APIRouter

from app.api.commands import router as commands_router
from app.api.devices import router as devices_router
from app.api.health import router as health_router
from app.api.production_processes import router as production_processes_router
from app.api.telemetry import router as telemetry_router
from app.api.workflows import router as workflows_router

router = APIRouter()
router.include_router(health_router)
router.include_router(devices_router)
router.include_router(production_processes_router)
router.include_router(workflows_router)
router.include_router(telemetry_router)
router.include_router(commands_router)
