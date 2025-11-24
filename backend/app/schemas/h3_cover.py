from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from app.models.h3_cover import OwnerKind, H3Method


class H3CoverBase(BaseModel):
    """Base schema for H3Cover."""
    owner_kind: OwnerKind
    owner_id: UUID
    resolution: int = Field(..., ge=0, le=15, description="H3 resolution (0-15)")
    method: H3Method
    cell: str = Field(..., max_length=20, description="H3 cell ID")


class H3CoverCreate(H3CoverBase):
    """Schema for creating an H3Cover."""
    pass


class H3Cover(H3CoverBase):
    """Schema for H3Cover response."""
    created_at: datetime
    
    class Config:
        from_attributes = True

