from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime

class DeviceModelBase(BaseModel):
    model_name: str = Field(..., description="型号名称")
    model_code: str = Field(..., description="型号编码")
    description: Optional[str] = Field(None, description="型号描述")
    specifications: Optional[Dict[str, Any]] = Field(None, description="规格参数")

class DeviceModelCreate(DeviceModelBase):
    pass

class DeviceModelUpdate(BaseModel):
    model_name: Optional[str] = None
    model_code: Optional[str] = None
    description: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None

class DeviceModelResponse(DeviceModelBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DeviceInstanceBase(BaseModel):
    device_model_id: Optional[int] = Field(None, description="设备型号id（可为空）")
    device_code: str = Field(..., description="设备编号")
    device_name: str = Field(..., description="设备名称")
    device_category: Optional[str] = None
    production_line: Optional[str] = None
    location: Optional[str] = None
    device_status: Optional[int] = 0
    device_data: Optional[Dict[str, Any]] = None
    communication_protocol: Optional[str] = None

class DeviceInstanceCreate(DeviceInstanceBase):
    device_code: Optional[str] = Field(None, description="设备编号，留空时自动生成")

class DeviceInstanceUpdate(BaseModel):
    device_model_id: Optional[int] = None
    device_code: Optional[str] = None
    device_name: Optional[str] = None
    device_category: Optional[str] = None
    production_line: Optional[str] = None
    location: Optional[str] = None
    device_status: Optional[int] = None
    device_data: Optional[Dict[str, Any]] = None
    communication_protocol: Optional[str] = None

class DeviceInstanceResponse(DeviceInstanceBase):
    id: int
    device_model_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeviceInstanceListResponse(BaseModel):
    items: List[DeviceInstanceResponse]
    total: int
    page: int
    size: int


class DeviceActionBase(BaseModel):
    device_instance_id: int = Field(..., description="设备实例id")
    action_name: str = Field(..., description="动作名称")
    action_command_params: Optional[Dict[str, Any]] = Field(None, description="动作指令参数")


class DeviceActionCreate(DeviceActionBase):
    pass


class DeviceActionUpdate(BaseModel):
    action_name: Optional[str] = None
    action_command_params: Optional[Dict[str, Any]] = None


class DeviceActionResponse(DeviceActionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
