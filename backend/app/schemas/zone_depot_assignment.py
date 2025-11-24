"""Pydantic schemas for ZoneDepotAssignment"""
from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class ZoneDepotAssignmentBase(BaseModel):
    """Base ZoneDepotAssignment schema"""
    zone_id: UUID
    depot_id: UUID
    is_primary: bool = True
    priority: int = 1


class ZoneDepotAssignmentCreate(ZoneDepotAssignmentBase):
    """Schema for creating a ZoneDepotAssignment"""
    pass


class ZoneDepotAssignment(ZoneDepotAssignmentBase):
    """Schema for ZoneDepotAssignment response"""
    
    class Config:
        from_attributes = True


class ZoneDepotAssignmentWithDetails(ZoneDepotAssignment):
    """ZoneDepotAssignment with zone and depot names"""
    zone_name: Optional[str] = None
    depot_name: Optional[str] = None

