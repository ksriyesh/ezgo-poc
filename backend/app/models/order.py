from sqlalchemy import Column, String, Float, Integer, Date, ForeignKey, CheckConstraint, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, TEXT
from sqlalchemy.orm import relationship
import enum
from app.models.base import UUIDMixin, TimestampMixin
from app.core.database import Base


class OrderStatus(str, enum.Enum):
    """Order status lifecycle"""
    PENDING = "pending"
    GEOCODED = "geocoded"
    ASSIGNED = "assigned"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Order(Base, UUIDMixin, TimestampMixin):
    """
    Delivery order with geocoded location, zone assignment, and depot assignment.
    """
    __tablename__ = "orders"
    
    order_number = Column(String(100), nullable=False, unique=True, index=True)
    customer_name = Column(String(255), nullable=False)
    customer_contact = Column(String(255), nullable=True, comment="Phone or email")
    
    # Address and geocoded location
    delivery_address = Column(TEXT, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    h3_index = Column(String(20), nullable=False, index=True, comment="H3 cell for order location")
    
    # Zone and depot assignment
    zone_id = Column(UUID(as_uuid=True), ForeignKey("service_zones.id", ondelete="SET NULL"), nullable=True, index=True)
    depot_id = Column(UUID(as_uuid=True), ForeignKey("depots.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Order details
    order_date = Column(Date, nullable=False, index=True)
    scheduled_delivery_date = Column(Date, nullable=True, index=True)
    status = Column(SQLEnum(OrderStatus, name="order_status_enum", values_callable=lambda x: [e.value for e in x]), nullable=False, server_default="pending", index=True)
    
    # Optional package details
    weight_kg = Column(Float, nullable=True)
    volume_m3 = Column(Float, nullable=True)
    special_instructions = Column(TEXT, nullable=True)
    
    # Clustering info (populated during route optimization)
    cluster_id = Column(Integer, nullable=True, comment="HDBSCAN cluster assignment")
    
    # Relationships
    zone = relationship("ServiceZone", backref="orders")
    depot = relationship("Depot", back_populates="orders")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="check_order_latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="check_order_longitude_range"),
        CheckConstraint("weight_kg >= 0", name="check_weight_positive"),
        CheckConstraint("volume_m3 >= 0", name="check_volume_positive"),
        Index("idx_orders_location", "latitude", "longitude"),
        Index("idx_orders_depot_date", "depot_id", "scheduled_delivery_date"),
        Index("idx_orders_status", "status"),
    )
    
    def __repr__(self):
        return f"<Order(id={self.id}, order_number='{self.order_number}', status={self.status.value})>"


