"""CRUD operations for Order"""
from typing import Optional, List
from uuid import UUID
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from app.crud.base import CRUDBase
from app.models.order import Order, OrderStatus
from app.schemas.order import OrderCreate, OrderUpdate
from app.services.mapbox_service import MapboxService
from app.services.h3_service import H3Service
from app.core.config import settings


class CRUDOrder(CRUDBase[Order, OrderCreate, OrderUpdate]):
    """CRUD operations for Order"""
    
    def create_with_geocoding(
        self,
        db: Session,
        *,
        obj_in: OrderCreate,
        mapbox_service: Optional[MapboxService] = None
    ) -> Order:
        """
        Create an order with automatic geocoding and zone/depot assignment.
        """
        # Initialize Mapbox service
        if mapbox_service is None:
            mapbox_service = MapboxService()
        
        # Geocode address (with Ottawa bias)
        # proximity expects (latitude, longitude) - standard format
        ottawa_center = (45.4215, -75.6972)  # (lat, lng) - standard format
        coords = mapbox_service.geocode_address(
            obj_in.delivery_address,
            proximity=ottawa_center
        )
        
        if not coords:
            raise ValueError(f"Failed to geocode address: {obj_in.delivery_address}")
        
        latitude, longitude = coords
        
        # Get H3 index, zone, and depot
        h3_index, zone_id, depot_id = H3Service.geocode_and_assign(
            db, latitude, longitude
        )
        
        # Create order
        db_obj = Order(
            **obj_in.model_dump(),
            latitude=latitude,
            longitude=longitude,
            h3_index=h3_index,
            zone_id=zone_id,
            depot_id=depot_id,
            status=OrderStatus.GEOCODED if zone_id else OrderStatus.PENDING
        )
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_depot(
        self,
        db: Session,
        depot_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100,
        status: Optional[OrderStatus] = None,
        delivery_date: Optional[date] = None
    ) -> List[Order]:
        """Get orders for a specific depot"""
        stmt = select(Order).where(Order.depot_id == depot_id)
        
        if status:
            stmt = stmt.where(Order.status == status)
        
        if delivery_date:
            stmt = stmt.where(Order.scheduled_delivery_date == delivery_date)
        
        stmt = stmt.offset(skip).limit(limit)
        
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_by_zone(
        self,
        db: Session,
        zone_id: UUID,
        *,
        skip: int = 0,
        limit: int = 100
    ) -> List[Order]:
        """Get orders for a specific zone"""
        stmt = select(Order).where(Order.zone_id == zone_id).offset(skip).limit(limit)
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_unassigned(
        self,
        db: Session,
        *,
        depot_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Order]:
        """Get orders pending route assignment"""
        stmt = select(Order).where(
            Order.status.in_([OrderStatus.PENDING, OrderStatus.GEOCODED])
        )
        
        if depot_id:
            stmt = stmt.where(Order.depot_id == depot_id)
        
        stmt = stmt.offset(skip).limit(limit)
        result = db.execute(stmt)
        return result.scalars().all()
    
    def get_grouped_by_zone(
        self,
        db: Session,
        depot_id: UUID,
        delivery_date: Optional[date] = None
    ) -> dict:
        """Get orders grouped by zone for a depot"""
        stmt = select(Order).where(Order.depot_id == depot_id)
        
        if delivery_date:
            stmt = stmt.where(Order.scheduled_delivery_date == delivery_date)
        
        result = db.execute(stmt)
        orders = result.scalars().all()
        
        # Group by zone_id
        grouped = {}
        for order in orders:
            zone_key = str(order.zone_id) if order.zone_id else "unassigned"
            if zone_key not in grouped:
                grouped[zone_key] = []
            grouped[zone_key].append(order)
        
        return grouped
    
    def update_cluster_assignments(
        self,
        db: Session,
        order_ids: List[UUID],
        cluster_labels: List[int]
    ) -> None:
        """Update cluster_id for multiple orders"""
        if len(order_ids) != len(cluster_labels):
            raise ValueError("order_ids and cluster_labels must have same length")
        
        for order_id, cluster_id in zip(order_ids, cluster_labels):
            stmt = select(Order).where(Order.id == order_id)
            result = db.execute(stmt)
            order = result.scalar_one_or_none()
            if order:
                order.cluster_id = int(cluster_id)
        
        db.commit()


order = CRUDOrder(Order)







