from sqlalchemy import Column, String, SmallInteger, CheckConstraint, Index, Enum as SQLEnum, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from app.models.h3_cover import OwnerKind, H3Method
from app.models.base import TimestampMixin
from app.core.database import Base


class H3Compact(Base, TimestampMixin):
    """
    Space-efficient snapshots—arrays of compacted H3 cells for an area + resolution.
    Great for shipping masks to other services; uncompact when you need fine granularity.
    """
    __tablename__ = "h3_compacts"
    
    owner_kind = Column(
        SQLEnum(OwnerKind, name="owner_kind_enum", create_type=False, create_constraint=False),
        nullable=False,
        primary_key=True
    )
    owner_id = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    resolution = Column(SmallInteger, nullable=False, primary_key=True)
    method = Column(
        SQLEnum(H3Method, name="h3_method_enum", create_type=False, create_constraint=False),
        nullable=False,
        primary_key=True
    )
    
    # Array of compacted H3 cell IDs
    cells_compact = Column(ARRAY(String(20)), nullable=False, comment="Array of compacted H3 cell IDs")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("resolution >= 0 AND resolution <= 15", name="check_resolution_range"),
    )
    
    def __repr__(self):
        return f"<H3Compact(owner_kind={self.owner_kind}, owner_id={self.owner_id}, resolution={self.resolution})>"

