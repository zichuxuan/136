from sqlalchemy import Column, Integer, String, Boolean

from app.core.database import Base


class ProductionProcess(Base):
    __tablename__ = "production_process"

    id = Column(Integer, primary_key=True, autoincrement=True)
    startup_process = Column(Integer, nullable=True, comment="启动流程")
    end_the_process = Column(Integer, nullable=True, comment="结束流程")
    process_name = Column(String(255), nullable=True, comment="工艺名称")
    process_description = Column(String(500), nullable=True, comment="工艺描述")
    enable_or_not = Column(Boolean, nullable=True, comment="是否启用:1启用，0禁用")
    if_delete = Column(Boolean, nullable=True, comment="是否删除：1删除，0不删除")
    if_run = Column(Boolean, nullable=True, comment="是否运行：1运行中，0未启动")
