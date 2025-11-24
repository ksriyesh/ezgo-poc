"""CRUD operations for Depot"""
from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from app.crud.base import CRUDBase
from app.models.depot import Depot
from app.models.order import Order
from app.schemas.depot import DepotCreate, DepotUpdate
from app.services.h3_service import H3Service


class CRUDDepot(CRUDBase[Depot, DepotCreate, DepotUpdate]):
    """CRUD operations for Depot"""
    
    def create(self, db: Session, *, obj_in: DepotCreate) -> Depot:
        """Create a new depot with H3 index"""
        # Calculate H3 index for depot location
        h3_index = H3Service.lat_lng_to_h3(obj_in.latitude, obj_in.longitude)
        
        db_obj = Depot(
            **obj_in.model_dump(),
            h3_index=h3_index
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_active(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[Depot]:
        """Get all active depots"""
        stmt = select(Depot).where(Depot.is_active == True).offset(skip).limit(limit)
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_by_zone(self, db: Session, zone_id: UUID) -> Optional[Depot]:
        """Get depot assigned to a zone"""
        from app.models.zone_depot_assignment import ZoneDepotAssignment
        
        stmt = select(Depot).join(
            ZoneDepotAssignment,
            Depot.id == ZoneDepotAssignment.depot_id
        ).where(
            and_(
                ZoneDepotAssignment.zone_id == zone_id,
                ZoneDepotAssignment.is_primary == True
            )
        )
        
        result = db.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_order_count(self, db: Session, depot_id: UUID) -> int:
        """Get count of orders for a depot"""
        stmt = select(func.count(Order.id)).where(Order.depot_id == depot_id)
        result = db.execute(stmt)
        return result.scalar() or 0


depot = CRUDDepot(Depot)









