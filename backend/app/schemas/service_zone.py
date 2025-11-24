from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime
from uuid import UUID


class H3CoverageByResolution(BaseModel):
    """H3 coverage at a specific resolution."""
    resolution: int
    cells: List[str]
    cell_count: int
    compacted_cells: Optional[List[str]] = None


class ServiceZoneBase(BaseModel):
    """Base schema for ServiceZone."""
    code: Optional[str] = Field(None, max_length=50, description="FSA or internal code")
    name: str = Field(..., min_length=1, max_length=255)
    label_cell: Optional[str] = Field(None, max_length=20, description="H3 cell ID for labeling")
    default_res: int = Field(default=9, ge=0, le=15, description="Default H3 resolution (0-15)")
    is_active: bool = Field(default=True)


class ServiceZoneCreate(ServiceZoneBase):
    """Schema for creating a ServiceZone."""
    service_area_id: UUID
    boundary: str = Field(..., description="MULTIPOLYGON geometry as GeoJSON or WKT")


class ServiceZoneUpdate(BaseModel):
    """Schema for updating a ServiceZone."""
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    service_area_id: Optional[UUID] = None
    boundary: Optional[str] = Field(None, description="MULTIPOLYGON geometry as GeoJSON or WKT")
    label_cell: Optional[str] = Field(None, max_length=20)
    default_res: Optional[int] = Field(None, ge=0, le=15)
    is_active: Optional[bool] = None


class ServiceZone(ServiceZoneBase):
    """Schema for ServiceZone response."""
    id: UUID
    service_area_id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ServiceZoneWithH3(ServiceZone):
    """Schema for ServiceZone response with H3 coverage."""
    h3_coverage: Dict[int, H3CoverageByResolution] = Field(
        default_factory=dict,
        description="H3 coverage by resolution"
    )

