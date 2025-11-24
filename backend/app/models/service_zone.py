from sqlalchemy import Column, String, Boolean, SmallInteger, ForeignKey, CheckConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, TEXT
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base


class ServiceZone(Base, UUIDMixin, TimestampMixin):
    """
    Routable sub-areas inside a service area (FSAs or custom zones).
    """
    __tablename__ = "service_zones"
    
    service_area_id = Column(UUID(as_uuid=True), ForeignKey("service_areas.id", ondelete="CASCADE"), nullable=False, index=True)
    code = Column(String(50), nullable=True, comment="FSA or internal code")
    name = Column(String(255), nullable=False)
    
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
    
    # Relationships
    service_area = relationship("ServiceArea", backref="zones")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("default_res >= 0 AND default_res <= 15", name="check_default_res_range"),
        UniqueConstraint("service_area_id", "name", name="uq_service_zone_area_name"),
        Index("idx_service_zones_boundary", "boundary", postgresql_using="gist"),
        Index("idx_service_zones_service_area_id", "service_area_id"),
        Index("idx_service_zones_is_active", "is_active", postgresql_where=(is_active == True)),
    )
    
    def __repr__(self):
        return f"<ServiceZone(id={self.id}, name='{self.name}', service_area_id={self.service_area_id})>"

