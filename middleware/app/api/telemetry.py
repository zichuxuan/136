from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.telemetry_service import TelemetryService

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])


class TelemetryData(BaseModel):
    device_id: str
    timestamp: str
    data: dict


class EventData(BaseModel):
    device_id: str
    timestamp: str
    event: dict


@router.get("/latest/{device_id}")
async def get_latest_telemetry(device_id: str):
    data = await TelemetryService.get_latest_telemetry(device_id)
    return {"device_id": device_id, "data": data}


@router.get("/events/{device_id}/latest")
async def get_latest_event(device_id: str):
    data = await TelemetryService.get_latest_event(device_id)
    return {"device_id": device_id, "data": data}


@router.get("/events/{device_id}/history")
async def get_event_history(device_id: str, limit: int = 10):
    events = await TelemetryService.get_event_history(device_id, limit)
    return {"device_id": device_id, "events": events}


@router.get("/history/{device_id}")
async def get_telemetry_history(
    device_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    query = """
        SELECT device_id, timestamp, data 
        FROM telemetry_history 
        WHERE device_id = :device_id
    """
    params = {"device_id": device_id}

    if start_time:
        query += " AND timestamp >= :start_time"
        params["start_time"] = start_time
    if end_time:
        query += " AND timestamp <= :end_time"
        params["end_time"] = end_time

    query += " ORDER BY timestamp DESC LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(query), params)
    rows = result.fetchall()

    return {
        "device_id": device_id,
        "history": [
            {"device_id": r[0], "timestamp": r[1], "data": r[2]}
            for r in rows
        ]
    }
