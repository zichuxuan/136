from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.command_service import CommandService

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])


class SendCommandRequest(BaseModel):
    device_code: str
    command_type: str
    params: dict = {}
    command_id: Optional[str] = None
    batch_id: Optional[str] = None
    source: Optional[dict] = None
    ts: Optional[str] = None


@router.post("/send")
async def send_command(request: SendCommandRequest):
    success = await CommandService.send_command(
        request.device_code,
        request.command_type,
        request.params,
        command_id=request.command_id,
        batch_id=request.batch_id,
        source=request.source,
        ts=request.ts,
    )
    return {
        "success": success,
        "device_code": request.device_code,
        "command_type": request.command_type
    }


@router.get("/latest/{device_id}")
async def get_latest_command(device_id: str):
    data = await CommandService.get_latest_command(device_id)
    return {"device_id": device_id, "command": data}


@router.get("/history/{device_id}")
async def get_command_history(device_id: str, limit: int = 10):
    commands = await CommandService.get_command_history(device_id, limit)
    return {"device_id": device_id, "commands": commands}


@router.get("/result/{device_id}")
async def get_command_result(device_id: str):
    result = await CommandService.get_command_result(device_id)
    return {"device_id": device_id, "result": result}
