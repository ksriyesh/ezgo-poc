from sqlalchemy import Column, String, Boolean, SmallInteger, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from sqlalchemy.dialects.postgresql import TEXT
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base


class ServiceArea(Base, UUIDMixin, TimestampMixin):
    """
    Top-level operating region (e.g., "Ottawa").
    Stores the authoritative geometry boundary and H3 configuration.
    """
    __tablename__ = "service_areas"
    
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(TEXT, nullable=True)
    
    # PostGIS MULTIPOLYGON geometry (SRID 4326)
    boundary = Column(
        Geometry("MULTIPOLYGON", srid=4326, spatial_index=True),
        nullable=False
    )
    
    # H3 cell for labeling (optional)
    label_cell = Column(String(20), nullable=True, comment="H3 cell ID for representative hex")
    
    # Default H3 resolution (0-15)
    default_res = Column(SmallInteger, nullable=False, default=9, comment="Default H3 resolution")
    
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    
    # Constraints
    __table_args__ = (
        CheckConstraint("default_res >= 0 AND default_res <= 15", name="check_default_res_range"),
        # Spatial index is created automatically by GeoAlchemy2
        Index("idx_service_areas_boundary", "boundary", postgresql_using="gist"),
        Index("idx_service_areas_is_active", "is_active", postgresql_where=(is_active == True)),
    )
    
    def __repr__(self):
        return f"<ServiceArea(id={self.id}, name='{self.name}', is_active={self.is_active})>"

