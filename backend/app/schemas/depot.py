"""Pydantic schemas for Depot"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from uuid import UUID
from datetime import datetime


class DepotBase(BaseModel):
    """Base Depot schema"""
    name: str = Field(..., max_length=255)
    address: str = Field(..., max_length=500)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    available_drivers: int = Field(default=5, ge=0)
    contact_info: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class DepotCreate(DepotBase):
    """Schema for creating a Depot"""
    pass


class DepotUpdate(BaseModel):
    """Schema for updating a Depot"""
    name: Optional[str] = Field(None, max_length=255)
    address: Optional[str] = Field(None, max_length=500)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    available_drivers: Optional[int] = Field(None, ge=0)
    contact_info: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class Depot(DepotBase):
    """Schema for Depot response"""
    id: UUID
    h3_index: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DepotWithZones(Depot):
    """Depot with assigned zones"""
    zone_count: int = 0
    zones: Optional[List[dict]] = None


class DepotWithOrders(Depot):
    """Depot with order statistics"""
    total_orders: int = 0
    pending_orders: int = 0
    assigned_orders: int = 0









