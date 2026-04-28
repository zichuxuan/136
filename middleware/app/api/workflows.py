from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from datetime import datetime

from app.core.db import get_db
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowResponse

router = APIRouter(prefix="/api/v1", tags=["workflows"])

@router.get("/workflows", response_model=List[WorkflowResponse])
async def list_workflows(
    page: int = 1,
    size: int = 10,
    db: AsyncSession = Depends(get_db)
):
    skip = (page - 1) * size
    result = await db.execute(
        select(Workflow)
        .where(Workflow.is_deleted == False)
        .order_by(Workflow.id.asc())
        .offset(skip)
        .limit(size)
    )
    return result.scalars().all()

@router.post("/workflows", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(workflow_in: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    db_obj = Workflow(**workflow_in.model_dump())
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(Workflow, workflow_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return db_obj

@router.patch("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: int, workflow_in: WorkflowUpdate, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(Workflow, workflow_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    update_data = workflow_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_obj, field, value)
    
    db.add(db_obj)
    await db.commit()
    await db.refresh(db_obj)
    return db_obj

@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    db_obj = await db.get(Workflow, workflow_id)
    if not db_obj or db_obj.is_deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    db_obj.is_deleted = True
    db_obj.deleted_at = datetime.now()
    db.add(db_obj)
    await db.commit()
    return {"message": "Workflow deleted successfully"}
