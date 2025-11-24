from pydantic import BaseModel, Field
from typing import List
from datetime import datetime
from uuid import UUID
from app.models.h3_cover import OwnerKind, H3Method


class H3CompactBase(BaseModel):
    """Base schema for H3Compact."""
    owner_kind: OwnerKind
    owner_id: UUID
    resolution: int = Field(..., ge=0, le=15, description="H3 resolution (0-15)")
    method: H3Method
    cells_compact: List[str] = Field(..., description="Array of compacted H3 cell IDs")


class H3CompactCreate(H3CompactBase):
    """Schema for creating an H3Compact."""
    pass


class H3Compact(H3CompactBase):
    """Schema for H3Compact response."""
    created_at: datetime
    
    class Config:
        from_attributes = True

