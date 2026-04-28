from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Workflow(Base):
    __tablename__ = "workflow"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_name = Column(String(100), nullable=False, comment="工作流名称")
    workflow_type = Column(String(50), nullable=False, comment="工作流类型")
    workflow_params = Column(JSON, comment="工作流入参数(JSON格式)")
    workflow_detail = Column(JSON, comment="工作流详情(JSON格式)：画布上的详细信息")
    conditions = Column(JSON, comment="工况参数")
    enable_or_not = Column(Boolean, default=True, comment="是否启用：0禁用，1启用")
    info = Column(String(500), nullable=True, comment="说明")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class WorkflowExecutionLog(Base):
    __tablename__ = "workflow_execution_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflow.id"), nullable=False, comment="工作流id")
    execution_status = Column(String(20), nullable=False, comment="工作流执行状态")
    error_message = Column(Text, comment="错误信息")
    frequency = Column(String(50), comment="执行频率")
    communication_params = Column(JSON, comment="通讯参数(JSON格式)：ip,端口,寄存器地址等")
    workflow_detail = Column(JSON, comment="工作流详情(JSON格式)")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    execution_start_time = Column(DateTime, nullable=False, comment="执行开始时间")
    execution_end_time = Column(DateTime, comment="执行结束时间")
    created_at = Column(DateTime, server_default=func.now())

    workflow = relationship("Workflow")
