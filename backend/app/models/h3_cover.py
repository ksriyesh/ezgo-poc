from sqlalchemy import Column, String, SmallInteger, CheckConstraint, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
import enum
from app.models.base import TimestampMixin
from app.core.database import Base


class OwnerKind(str, enum.Enum):
    """Enum for owner type in H3 helper tables."""
    SERVICE_AREA = "service_area"
    SERVICE_ZONE = "service_zone"


class H3Method(str, enum.Enum):
    """Enum for H3 fill method."""
    CENTROID = "centroid"
    COVERAGE = "coverage"


class H3Cover(Base, TimestampMixin):
    """
    Normalized H3 "fill" of polygons—one row per H3 cell per resolution.
    Used for super-fast membership joins.
    """
    __tablename__ = "h3_covers"
    
    owner_kind = Column(
        SQLEnum(OwnerKind, name="owner_kind_enum", create_type=True),
        nullable=False,
        primary_key=True
    )
    owner_id = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    resolution = Column(SmallInteger, nullable=False, primary_key=True)
    method = Column(
        SQLEnum(H3Method, name="h3_method_enum", create_type=True),
        nullable=False,
        primary_key=True
    )
    cell = Column(String(20), nullable=False, primary_key=True, comment="H3 cell ID")
    
    # Constraints
    __table_args__ = (
        CheckConstraint("resolution >= 0 AND resolution <= 15", name="check_resolution_range"),
        Index("idx_h3_covers_cell", "cell"),
        Index("idx_h3_covers_owner", "owner_kind", "owner_id", "resolution"),
    )
    
    def __repr__(self):
        return f"<H3Cover(owner_kind={self.owner_kind}, owner_id={self.owner_id}, resolution={self.resolution}, cell={self.cell})>"

