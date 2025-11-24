"""
Depot model for multi-depot routing system.
"""
from sqlalchemy import Column, String, Float, Integer, Boolean, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, TEXT
from sqlalchemy.orm import relationship
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base


class Depot(Base, UUIDMixin, TimestampMixin):
    """
    Depot (fulfillment center) model.
    Each depot has a location and serves multiple service zones.
    """
    __tablename__ = "depots"

    name = Column(String(255), unique=True, nullable=False, index=True)
    address = Column(String(500), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    h3_index = Column(String(20), nullable=True, comment="H3 cell for depot location")
    available_drivers = Column(Integer, nullable=False, default=5, comment="Available drivers for route optimization")
    contact_info = Column(TEXT, nullable=True, comment="Contact phone/email")
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Relationships
    orders = relationship("Order", back_populates="depot")
    zone_assignments = relationship("ZoneDepotAssignment", back_populates="depot")

    __table_args__ = (
        CheckConstraint('available_drivers >= 0', name='check_available_drivers_positive'),
        CheckConstraint('latitude >= -90 AND latitude <= 90', name='check_depot_latitude_range'),
        CheckConstraint('longitude >= -180 AND longitude <= 180', name='check_depot_longitude_range'),
        Index("idx_depots_location", "latitude", "longitude"),
        Index("idx_depots_h3_index", "h3_index"),
        Index("idx_depots_is_active", "is_active", postgresql_where=(is_active == True)),
    )

    def __repr__(self):
        return f"<Depot(name='{self.name}', location=({self.latitude}, {self.longitude}), drivers={self.available_drivers})>"
