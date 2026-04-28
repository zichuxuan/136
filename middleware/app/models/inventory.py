from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric
from sqlalchemy.sql import func
from app.core.database import Base


class Material(Base):
    __tablename__ = "material"

    id = Column(Integer, primary_key=True, autoincrement=True)
    material_code = Column(String(50), unique=True, nullable=False, comment="物料编码")
    material_name = Column(String(100), nullable=False, comment="物料名称")
    material_type = Column(String(50), comment="物料类型")
    material_spec = Column(String(100), comment="物料规格")
    unit = Column(String(20), comment="计量单位")
    description = Column(Text, comment="物料描述")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Warehouse(Base):
    __tablename__ = "warehouse"

    id = Column(Integer, primary_key=True, autoincrement=True)
    warehouse_code = Column(String(50), unique=True, nullable=False, comment="仓库编号")
    warehouse_type = Column(String(20), nullable=False, comment="仓库类型")
    warehouse_name = Column(String(100), nullable=False, comment="仓库名称")
    warehouse_location = Column(String(200), nullable=False, comment="仓库位置")
    person_in_charge = Column(String(50), comment="负责人")
    contact_phone = Column(String(20), comment="负责人联系电话")
    warehouse_capacity = Column(Numeric(10, 2), comment="仓库容量")
    capacity_unit = Column(String(20), default="平方米", comment="容量单位")
    is_deleted = Column(Boolean, default=False, comment="逻辑删除标志")
    deleted_at = Column(DateTime, comment="删除时间")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
