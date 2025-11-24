from sqlalchemy import Column, Boolean, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class ZoneDepotAssignment(Base):
    """
    Assignment of service zones to depots.
    One-to-many: Each zone is assigned to exactly one depot (is_primary=True).
    """
    __tablename__ = "zone_depot_assignments"
    
    zone_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("service_zones.id", ondelete="CASCADE"), 
        primary_key=True,
        nullable=False
    )
    depot_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("depots.id", ondelete="CASCADE"), 
        primary_key=True,
        nullable=False
    )
    
    # In this POC, each zone has one primary depot
    is_primary = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=1, comment="Priority order if multiple depots")
    
    # Relationships
    zone = relationship("ServiceZone", backref="depot_assignments")
    depot = relationship("Depot", back_populates="zone_assignments")
    
    # Indexes
    __table_args__ = (
        Index("idx_zone_depot_zone_id", "zone_id"),
        Index("idx_zone_depot_depot_id", "depot_id"),
    )
    
    def __repr__(self):
        return f"<ZoneDepotAssignment(zone_id={self.zone_id}, depot_id={self.depot_id}, is_primary={self.is_primary})>"


