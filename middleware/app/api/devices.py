from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime
from uuid import uuid4

from app.core.db import get_db
from app.models.device import DeviceAction, DeviceInstance, DeviceModel
from app.schemas.device import (
    DeviceModelCreate, DeviceModelUpdate, DeviceModelResponse,
    DeviceInstanceCreate, DeviceInstanceUpdate, DeviceInstanceResponse, DeviceInstanceListResponse,
    DeviceActionCreate, DeviceActionUpdate, DeviceActionResponse
)

router = APIRouter(prefix="/api/v1", tags=["devices"])


async def _generate_device_code(db: AsyncSession) -> str:
    """Generate a unique device_code for device creation."""
    for _ in range(5):
        candidate = f"DEV{uuid4().hex[:8].upper()}"
        stmt = select(DeviceInstance).where(
            DeviceInstance.device_code == candidate,
            DeviceInstance.is_deleted == False
        )
        result = await db.execute(stmt)
        if not result.scalar_one_or_none():
            return candidate
    raise HTTPException(status_code=500, detail="Failed to generate unique device code")

# --- Device Model CRUD ---

@router.get(
    "/device-models",
    response_model=List[DeviceModelResponse],
    summary="获取设备型号列表",
    description="获取未删除的设备型号列表，按 id 升序返回。"
)
async def list_device_models(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DeviceModel)
        .where(DeviceModel.is_deleted == False)
        .order_by(DeviceModel.id.asc())
    )
    return result.scalars().all()

@router.post(
    "/device-models",
    response_model=DeviceModelResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建设备型号",
    description="新增设备型号，model_code 需唯一。"
)
async def create_device_model(model_in: DeviceModelCreate, db: AsyncSession = Depends(get_db)):
    # Check if code already exists
    stmt = select(DeviceModel).where(DeviceModel.model_code == model_in.model_code, DeviceModel.is_deleted == False)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Device model code already exists")
    
    db_obj = DeviceModel(**model_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.get(
    "/device-models/{model_id}",
    response_model=DeviceModelResponse,
    summary="获取设备型号详情",
    description="按型号 id 获取设备型号详情。"
)
async def get_device_model(model_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceModel, model_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device model not found")
    return db_obj

@router.patch(
    "/device-models/{model_id}",
    response_model=DeviceModelResponse,
    summary="更新设备型号",
    description="按型号 id 局部更新设备型号信息。"
)
async def update_device_model(model_id: int, model_in: DeviceModelUpdate, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceModel, model_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device model not found")
    
    update_data = model_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.delete(
    "/device-models/{model_id}",
    summary="删除设备型号",
    description="按型号 id 逻辑删除设备型号。"
)
async def delete_device_model(model_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceModel, model_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device model not found")
    
    db_obj.is_deleted = True
    db_obj.deleted_at = datetime.now()
    db.add(db_obj)
    await db.commit()
    return {"message": "Device model deleted successfully"}

# --- Device Instance CRUD ---

@router.get(
    "/devices",
    response_model=DeviceInstanceListResponse,
    summary="获取设备列表（分页）",
    description="分页查询设备实例，支持按关键字模糊搜索和设备类别筛选，返回 items、total、page、size。"
)
async def list_devices(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(15, ge=1, le=200, description="每页数量，默认 15，最大 200"),
    keyword: str | None = Query(None, description="关键字，按设备名称或设备编号模糊过滤"),
    device_category: str | None = Query(None, description="设备类别，按类别模糊筛选"),
    db: AsyncSession = Depends(get_db)
):
    skip = (page - 1) * size

    # 构建基础查询条件
    filters = [DeviceInstance.is_deleted == False]
    if keyword:
        filters.append(
            (DeviceInstance.device_name.ilike(f"%{keyword}%")) |
            (DeviceInstance.device_code.ilike(f"%{keyword}%"))
        )
    if device_category:
        filters.append(DeviceInstance.device_category.ilike(f"%{device_category}%"))

    # 查询总数
    total_stmt = select(func.count()).select_from(DeviceInstance).where(*filters)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar_one()

    # 查询数据
    result = await db.execute(
        select(DeviceInstance, DeviceModel.model_name)
        .join(
            DeviceModel,
            (DeviceModel.id == DeviceInstance.device_model_id) & (DeviceModel.is_deleted == False),
            isouter=True
        )
        .where(*filters)
        .order_by(DeviceInstance.id.asc())
        .offset(skip)
        .limit(size)
    )
    rows = result.all()
    items = []
    for device, model_name in rows:
        item = DeviceInstanceResponse.model_validate(device).model_dump()
        item["device_model_name"] = model_name
        items.append(item)
    return {"items": items, "total": total, "page": page, "size": size}

@router.post(
    "/devices",
    response_model=DeviceInstanceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建设备",
    description="新增设备实例，device_code 需唯一；若未传或传空则自动生成。"
)
async def create_device(device_in: DeviceInstanceCreate, db: AsyncSession = Depends(get_db)):
    device_code = (device_in.device_code or "").strip()
    if not device_code:
        device_code = await _generate_device_code(db)
    else:
        # Check if code already exists when client provides one.
        stmt = select(DeviceInstance).where(
            DeviceInstance.device_code == device_code,
            DeviceInstance.is_deleted == False
        )
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Device code already exists")

    payload = device_in.model_dump()
    payload["device_code"] = device_code
    db_obj = DeviceInstance(**payload)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    model_stmt = select(DeviceModel.model_name).where(
        DeviceModel.id == db_obj.device_model_id,
        DeviceModel.is_deleted == False
    )
    model_result = await db.execute(model_stmt)
    model_name = model_result.scalar_one_or_none()
    response = DeviceInstanceResponse.model_validate(db_obj).model_dump()
    response["device_model_name"] = model_name
    return response

@router.get(
    "/devices/{device_id}",
    response_model=DeviceInstanceResponse,
    summary="获取设备详情",
    description="按设备 id 获取设备详情，返回 device_model_name。"
)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DeviceInstance, DeviceModel.model_name)
        .join(
            DeviceModel,
            (DeviceModel.id == DeviceInstance.device_model_id) & (DeviceModel.is_deleted == False),
            isouter=True
        )
        .where(DeviceInstance.id == device_id, DeviceInstance.is_deleted == False)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Device instance not found")
    db_obj, model_name = row
    response = DeviceInstanceResponse.model_validate(db_obj).model_dump()
    response["device_model_name"] = model_name
    return response

@router.patch(
    "/devices/{device_id}",
    response_model=DeviceInstanceResponse,
    summary="更新设备",
    description="按设备 id 局部更新设备实例，若更新 device_code 会校验唯一性。"
)
async def update_device(device_id: int, device_in: DeviceInstanceUpdate, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceInstance, device_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device instance not found")
    
    model_name = None
    if device_in.device_model_id is not None:
        model_stmt = select(DeviceModel.model_name).where(
            DeviceModel.id == device_in.device_model_id,
            DeviceModel.is_deleted == False
        )
        model_result = await db.execute(model_stmt)
        model_name = model_result.scalar_one_or_none()

    if device_in.device_code and device_in.device_code != db_obj.device_code:
        conflict_stmt = select(DeviceInstance).where(
            DeviceInstance.device_code == device_in.device_code,
            DeviceInstance.is_deleted == False,
            DeviceInstance.id != device_id
        )
        conflict_result = await db.execute(conflict_stmt)
        if conflict_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Device code already exists")

    update_data = device_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    if model_name is None:
        model_stmt = select(DeviceModel.model_name).where(
            DeviceModel.id == db_obj.device_model_id,
            DeviceModel.is_deleted == False
        )
        model_result = await db.execute(model_stmt)
        model_name = model_result.scalar_one_or_none()
    response = DeviceInstanceResponse.model_validate(db_obj).model_dump()
    response["device_model_name"] = model_name
    return response

@router.delete(
    "/devices/{device_id}",
    summary="删除设备",
    description="按设备 id 逻辑删除设备实例。"
)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceInstance, device_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device instance not found")
    
    db_obj.is_deleted = True
    db_obj.deleted_at = datetime.now()
    db.add(db_obj)
    await db.commit()
    return {"message": "Device instance deleted successfully"}


# --- Device Action CRUD ---

@router.get(
    "/device-actions",
    response_model=List[DeviceActionResponse],
    summary="获取设备行为事件列表",
    description="按 device_instance_id 查询远程控制界面的行为事件列表。"
)
async def list_device_actions(
    device_instance_id: int = Query(..., ge=1, description="设备实例 id"),
    db: AsyncSession = Depends(get_db)
):
    device_obj = await db.get(DeviceInstance, device_instance_id)
    if not device_obj or device_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device instance not found")

    result = await db.execute(
        select(DeviceAction)
        .where(
            DeviceAction.device_instance_id == device_instance_id,
            DeviceAction.is_deleted == False
        )
        .order_by(DeviceAction.id.asc())
    )
    return result.scalars().all()


@router.post(
    "/device-actions",
    response_model=DeviceActionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增设备行为事件",
    description="为指定设备新增行为事件（动作名称与指令参数）。"
)
async def create_device_action(action_in: DeviceActionCreate, db: AsyncSession = Depends(get_db)):
    device_obj = await db.get(DeviceInstance, action_in.device_instance_id)
    if not device_obj or device_obj.is_deleted:
        raise HTTPException(status_code=400, detail="Device instance not found")

    db_obj = DeviceAction(**action_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/device-actions/{action_id}",
    response_model=DeviceActionResponse,
    summary="获取设备行为事件详情",
    description="按 action_id 查询单条行为事件。"
)
async def get_device_action(action_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceAction, action_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device action not found")
    return db_obj


@router.patch(
    "/device-actions/{action_id}",
    response_model=DeviceActionResponse,
    summary="更新设备行为事件",
    description="按 action_id 局部更新行为事件。"
)
async def update_device_action(action_id: int, action_in: DeviceActionUpdate, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceAction, action_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device action not found")

    update_data = action_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete(
    "/device-actions/{action_id}",
    summary="删除设备行为事件",
    description="按 action_id 逻辑删除行为事件。"
)
async def delete_device_action(action_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(DeviceAction, action_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Device action not found")

    db_obj.is_deleted = True
    db_obj.deleted_at = datetime.now()
    db.add(db_obj)
    await db.commit()
    return {"message": "Device action deleted successfully"}
