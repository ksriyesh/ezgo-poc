"""CRUD operations for ZoneDepotAssignment"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, delete
from app.models.zone_depot_assignment import ZoneDepotAssignment
from app.schemas.zone_depot_assignment import ZoneDepotAssignmentCreate


class CRUDZoneDepotAssignment:
    """CRUD operations for ZoneDepotAssignment"""
    
    def create(
        self,
        db: Session,
        *,
        obj_in: ZoneDepotAssignmentCreate
    ) -> ZoneDepotAssignment:
        """Create a zone-depot assignment"""
        db_obj = ZoneDepotAssignment(**obj_in.model_dump())
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get(
        self,
        db: Session,
        zone_id: UUID,
        depot_id: UUID
    ) -> Optional[ZoneDepotAssignment]:
        """Get a specific assignment"""
        stmt = select(ZoneDepotAssignment).where(
            and_(
                ZoneDepotAssignment.zone_id == zone_id,
                ZoneDepotAssignment.depot_id == depot_id
            )
        )
        result = db.execute(stmt)
        return result.scalar_one_or_none()
    
    def get_by_zone(
        self,
        db: Session,
        zone_id: UUID
    ) -> List[ZoneDepotAssignment]:
        """Get all assignments for a zone"""
        stmt = select(ZoneDepotAssignment).where(
            ZoneDepotAssignment.zone_id == zone_id
        )
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_by_depot(
        self,
        db: Session,
        depot_id: UUID
    ) -> List[ZoneDepotAssignment]:
        """Get all assignments for a depot"""
        stmt = select(ZoneDepotAssignment).where(
            ZoneDepotAssignment.depot_id == depot_id
        )
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_primary_depot_for_zone(
        self,
        db: Session,
        zone_id: UUID
    ) -> Optional[UUID]:
        """Get the primary depot ID for a zone"""
        stmt = select(ZoneDepotAssignment.depot_id).where(
            and_(
                ZoneDepotAssignment.zone_id == zone_id,
                ZoneDepotAssignment.is_primary == True
            )
        )
        result = db.execute(stmt)
        return result.scalar_one_or_none()
    
    def delete(
        self,
        db: Session,
        zone_id: UUID,
        depot_id: UUID
    ) -> bool:
        """Delete an assignment"""
        stmt = delete(ZoneDepotAssignment).where(
            and_(
                ZoneDepotAssignment.zone_id == zone_id,
                ZoneDepotAssignment.depot_id == depot_id
            )
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount > 0


zone_depot_assignment = CRUDZoneDepotAssignment()









