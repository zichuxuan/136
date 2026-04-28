from pydantic import BaseModel, Field
from typing import Optional


class ProductionProcessBase(BaseModel):
    startup_process: Optional[int] = Field(None, description="启动流程")
    end_the_process: Optional[int] = Field(None, description="结束流程")
    process_name: Optional[str] = Field(None, description="工艺名称")
    process_description: Optional[str] = Field(None, description="工艺描述")
    enable_or_not: Optional[bool] = Field(None, description="是否启用:1启用，0禁用")
    if_run: Optional[bool] = Field(None, description="是否运行：1运行中，0未启动")


class ProductionProcessCreate(ProductionProcessBase):
    process_name: str = Field(..., description="工艺名称")


class ProductionProcessUpdate(BaseModel):
    startup_process: Optional[int] = None
    end_the_process: Optional[int] = None
    process_name: Optional[str] = None
    process_description: Optional[str] = None
    enable_or_not: Optional[bool] = None
    if_run: Optional[bool] = None


class ProductionProcessResponse(ProductionProcessBase):
    id: int
    if_delete: Optional[bool] = Field(None, description="是否删除：1删除，0不删除")
    if_run: Optional[bool] = Field(None, description="是否运行：1运行中，0未启动")

    class Config:
        from_attributes = True
