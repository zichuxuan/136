from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class DeviceModel(Base):
    __tablename__ = "device_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False, comment="型号名称")
    model_code = Column(String(50), unique=True, nullable=False, comment="型号编码")
    description = Column(Text, comment="型号描述")
    specifications = Column(JSON, comment="规格参数")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DeviceInstance(Base):
    __tablename__ = "device_instance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_model_id = Column(Integer, nullable=True, comment="设备型号id（可为空，不强制外键）")
    device_code = Column(String(50), unique=True, nullable=False, comment="设备编号")
    device_name = Column(String(100), nullable=False, comment="设备名称")
    device_category = Column(String(50), comment="设备类别")
    production_line = Column(String(100), comment="所属产线")
    location = Column(String(200), comment="所在位置")
    device_status = Column(Integer, default=0, comment="设备状态：0-离线，1-在线，2-运行中，3-故障")
    device_data = Column(JSON, comment="设备数据(JSON格式)：运行时长、最大容量等")
    communication_protocol = Column(String(50), comment="设备通讯协议")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class DeviceAction(Base):
    __tablename__ = "device_action"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_instance_id = Column(Integer, ForeignKey("device_instance.id"), nullable=False, comment="设备实例id")
    action_name = Column(String(100), nullable=False, comment="动作名称")
    action_command_params = Column(JSON, comment="动作指令参数(JSON格式)")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    instance = relationship("DeviceInstance")


class DeviceLog(Base):
    __tablename__ = "device_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_instance_id = Column(Integer, ForeignKey("device_instance.id"), nullable=False, comment="设备实例id")
    log_level = Column(String(20), nullable=False, comment="日志级别：INFO, WARN, ERROR, DEBUG")
    event_type = Column(String(50), nullable=False, comment="事件类型")
    log_summary = Column(String(200), comment="日志摘要")
    detailed_info = Column(Text, comment="详细信息")
    log_generated_time = Column(DateTime, nullable=False, comment="日志生成时间")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())

    instance = relationship("DeviceInstance")
