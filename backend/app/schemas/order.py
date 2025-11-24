"""Pydantic schemas for Order"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import date, datetime
from app.models.order import OrderStatus


class OrderBase(BaseModel):
    """Base Order schema"""
    customer_name: str = Field(..., max_length=255)
    customer_contact: Optional[str] = Field(None, max_length=255)
    delivery_address: str
    scheduled_delivery_date: Optional[date] = None
    weight_kg: Optional[float] = Field(None, ge=0)
    volume_m3: Optional[float] = Field(None, ge=0)
    special_instructions: Optional[str] = None


class OrderCreate(OrderBase):
    """
    Schema for creating an Order.
    Address will be geocoded automatically.
    """
    order_number: str = Field(..., max_length=100)
    order_date: date


class OrderUpdate(BaseModel):
    """Schema for updating an Order"""
    customer_name: Optional[str] = Field(None, max_length=255)
    customer_contact: Optional[str] = Field(None, max_length=255)
    delivery_address: Optional[str] = None
    scheduled_delivery_date: Optional[date] = None
    status: Optional[OrderStatus] = None
    weight_kg: Optional[float] = Field(None, ge=0)
    volume_m3: Optional[float] = Field(None, ge=0)
    special_instructions: Optional[str] = None


class Order(OrderBase):
    """Schema for Order response"""
    id: UUID
    order_number: str
    latitude: float
    longitude: float
    h3_index: str
    zone_id: Optional[UUID]
    depot_id: Optional[UUID]
    order_date: date
    status: OrderStatus
    cluster_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OrderWithDetails(Order):
    """Order with zone and depot details"""
    zone_name: Optional[str] = None
    depot_name: Optional[str] = None


class OrderGroup(BaseModel):
    """Group of orders (e.g., by zone or cluster)"""
    group_id: str
    group_name: str
    orders: List[Order]
    count: int
    centroid: Optional[tuple[float, float]] = None


class BulkOrderCreate(BaseModel):
    """Schema for bulk order creation"""
    orders: List[OrderCreate]


class BulkOrderResponse(BaseModel):
    """Response for bulk order creation"""
    successful: List[Order]
    failed: List[dict]
    total: int
    success_count: int
    failure_count: int

