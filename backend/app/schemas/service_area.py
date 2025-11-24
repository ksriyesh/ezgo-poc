from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, List
from datetime import datetime
from uuid import UUID


class H3CoverageByResolution(BaseModel):
    """H3 coverage at a specific resolution."""
    resolution: int
    cells: List[str]
    cell_count: int
    compacted_cells: Optional[List[str]] = None


class ServiceAreaBase(BaseModel):
    """Base schema for ServiceArea."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    label_cell: Optional[str] = Field(None, max_length=20, description="H3 cell ID for labeling")
    default_res: int = Field(default=9, ge=0, le=15, description="Default H3 resolution (0-15)")
    is_active: bool = Field(default=True)


class ServiceAreaCreate(ServiceAreaBase):
    """Schema for creating a ServiceArea."""
    # Boundary will be provided as GeoJSON or WKT string
    boundary: str = Field(..., description="MULTIPOLYGON geometry as GeoJSON or WKT")


class ServiceAreaUpdate(BaseModel):
    """Schema for updating a ServiceArea."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    boundary: Optional[str] = Field(None, description="MULTIPOLYGON geometry as GeoJSON or WKT")
    label_cell: Optional[str] = Field(None, max_length=20)
    default_res: Optional[int] = Field(None, ge=0, le=15)
    is_active: Optional[bool] = None


class ServiceArea(ServiceAreaBase):
    """Schema for ServiceArea response."""
    id: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class ServiceAreaWithH3(ServiceArea):
    """Schema for ServiceArea response with H3 coverage."""
    h3_coverage: Dict[int, H3CoverageByResolution] = Field(
        default_factory=dict,
        description="H3 coverage by resolution"
    )

