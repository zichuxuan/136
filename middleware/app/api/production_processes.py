from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.db import get_db
from app.models.production_process import ProductionProcess
from app.schemas.production_process import (
    ProductionProcessCreate,
    ProductionProcessUpdate,
    ProductionProcessResponse,
)

router = APIRouter(prefix="/api/v1", tags=["production-processes"])


@router.get(
    "/production-processes",
    response_model=List[ProductionProcessResponse],
    summary="获取工艺列表",
    description="分页获取工艺列表（自动过滤已删除数据），支持按工艺名称关键字模糊搜索、按启用状态及运行状态过滤。",
)
async def list_production_processes(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(10, ge=1, le=200, description="每页数量，默认 10，最大 200"),
    keyword: str | None = Query(None, description="关键字，按工艺名称模糊过滤"),
    enable_or_not: bool | None = Query(None, description="是否启用: true 启用, false 禁用"),
    if_run: bool | None = Query(None, description="是否运行: true 运行中, false 未启动"),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * size

    stmt = (
        select(ProductionProcess)
        .where(or_(ProductionProcess.if_delete.is_(False), ProductionProcess.if_delete.is_(None)))
        .order_by(ProductionProcess.id.asc())
    )
    if keyword:
        stmt = stmt.where(ProductionProcess.process_name.ilike(f"%{keyword}%"))
    if enable_or_not is not None:
        stmt = stmt.where(ProductionProcess.enable_or_not == enable_or_not)
    if if_run is not None:
        stmt = stmt.where(ProductionProcess.if_run == if_run)

    result = await db.execute(stmt.offset(skip).limit(size))
    return result.scalars().all()


@router.post(
    "/production-processes",
    response_model=ProductionProcessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增工艺",
    description="新增一条工艺（production_process）记录。",
)
async def create_production_process(
    payload: ProductionProcessCreate,
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    data["if_delete"] = False
    db_obj = ProductionProcess(**data)
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.get(
    "/production-processes/{process_id}",
    response_model=ProductionProcessResponse,
    summary="获取工艺详情",
    description="按工艺 id 获取工艺详情。",
)
async def get_production_process(process_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(ProductionProcess, process_id)
    if not db_obj or db_obj.if_delete:
        raise HTTPException(status_code=404, detail="Production process not found")
    return db_obj


@router.patch(
    "/production-processes/{process_id}",
    response_model=ProductionProcessResponse,
    summary="更新工艺",
    description="按工艺 id 局部更新工艺信息。",
)
async def update_production_process(
    process_id: int, payload: ProductionProcessUpdate, db: AsyncSession = Depends(get_db)
):
    db_obj = await db.get(ProductionProcess, process_id)
    if not db_obj or db_obj.if_delete:
        raise HTTPException(status_code=404, detail="Production process not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)

    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj


@router.delete(
    "/production-processes/{process_id}",
    summary="删除工艺",
    description="按工艺 id 逻辑删除工艺记录（if_delete=1）。",
)
async def delete_production_process(process_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(ProductionProcess, process_id)
    if not db_obj or db_obj.if_delete:
        raise HTTPException(status_code=404, detail="Production process not found")

    db_obj.if_delete = True
    db.add(db_obj)
    await db.commit()
    return {"message": "Production process deleted successfully"}
