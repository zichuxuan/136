from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class WorkflowBase(BaseModel):
    workflow_name: str = Field(..., description="工作流名称")
    workflow_type: str = Field(..., description="工作流类型")
    workflow_params: Optional[Dict[str, Any]] = Field(None, description="工作流入参数")
    workflow_detail: Optional[Dict[str, Any]] = Field(None, description="工作流详情")
    conditions: Optional[Dict[str, Any]] = Field(None, description="工况参数")
    enable_or_not: Optional[bool] = Field(True, description="是否启用")
    info: Optional[str] = Field(None, description="说明")

class WorkflowCreate(WorkflowBase):
    pass

class WorkflowUpdate(BaseModel):
    workflow_name: Optional[str] = None
    workflow_type: Optional[str] = None
    workflow_params: Optional[Dict[str, Any]] = None
    workflow_detail: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    enable_or_not: Optional[bool] = None
    info: Optional[str] = None

class WorkflowResponse(WorkflowBase):
    id: int
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    enable_or_not: Optional[bool] = None
    info: Optional[str] = None

    class Config:
        from_attributes = True
