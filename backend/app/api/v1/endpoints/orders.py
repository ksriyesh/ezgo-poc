"""API endpoints for Orders"""
from typing import List, Optional
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app import crud, schemas
from app.models.order import OrderStatus
from app.services.mapbox_service import MapboxService

router = APIRouter()


@router.post("/", response_model=schemas.Order, status_code=status.HTTP_201_CREATED)
def create_order(
    *,
    db: Session = Depends(get_db),
    order_in: schemas.OrderCreate
) -> schemas.Order:
    """
    Create a new order with automatic geocoding and zone/depot assignment.
    The delivery address will be geocoded using Mapbox API.
    """
    try:
        mapbox_service = MapboxService()
        order = crud.order.create_with_geocoding(
            db=db,
            obj_in=order_in,
            mapbox_service=mapbox_service
        )
        return order
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating order: {str(e)}"
        )


@router.get("/", response_model=List[schemas.Order])
def list_orders(
    skip: int = 0,
    limit: int = 100,
    depot_id: Optional[UUID] = None,
    zone_id: Optional[UUID] = None,
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    delivery_date: Optional[date] = None,
    db: Session = Depends(get_db)
) -> List[schemas.Order]:
    """
    Get orders with optional filtering.
    Can filter by depot, zone, status, and delivery date.
    """
    if depot_id:
        orders = crud.order.get_by_depot(
            db=db,
            depot_id=depot_id,
            skip=skip,
            limit=limit,
            status=status_filter,
            delivery_date=delivery_date
        )
    elif zone_id:
        orders = crud.order.get_by_zone(
            db=db,
            zone_id=zone_id,
            skip=skip,
            limit=limit
        )
    else:
        orders = crud.order.get_multi(db=db, skip=skip, limit=limit)
    
    return orders


@router.get("/unassigned", response_model=List[schemas.Order])
def get_unassigned_orders(
    depot_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
) -> List[schemas.Order]:
    """Get orders that haven't been assigned to routes yet"""
    orders = crud.order.get_unassigned(
        db=db,
        depot_id=depot_id,
        skip=skip,
        limit=limit
    )
    return orders


@router.get("/grouped-by-zone", response_model=dict)
def get_orders_grouped_by_zone(
    depot_id: UUID,
    delivery_date: Optional[date] = None,
    db: Session = Depends(get_db)
) -> dict:
    """Get orders grouped by service zone for a depot"""
    depot = crud.depot.get(db=db, id=depot_id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    grouped = crud.order.get_grouped_by_zone(
        db=db,
        depot_id=depot_id,
        delivery_date=delivery_date
    )
    
    # Format for response
    result = {
        "depot_id": str(depot_id),
        "groups": []
    }
    
    for zone_key, orders in grouped.items():
        result["groups"].append({
            "zone_id": zone_key,
            "count": len(orders),
            "orders": [schemas.Order.model_validate(order) for order in orders]
        })
    
    return result


@router.get("/{id}", response_model=schemas.Order)
def get_order(
    *,
    db: Session = Depends(get_db),
    id: UUID
) -> schemas.Order:
    """Get a specific order by ID"""
    order = crud.order.get(db=db, id=id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    return order


@router.put("/{id}", response_model=schemas.Order)
def update_order(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    order_in: schemas.OrderUpdate
) -> schemas.Order:
    """Update an order"""
    order = crud.order.get(db=db, id=id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    
    # If address is being updated, re-geocode
    if order_in.delivery_address and order_in.delivery_address != order.delivery_address:
        try:
            mapbox_service = MapboxService()
            ottawa_center = (-75.6972, 45.4215)
            coords = mapbox_service.geocode_address(
                order_in.delivery_address,
                proximity=ottawa_center
            )
            
            if coords:
                from app.services.h3_service import H3Service
                latitude, longitude = coords
                h3_index, zone_id, depot_id = H3Service.geocode_and_assign(
                    db, latitude, longitude
                )
                
                # Update geocoded fields
                order.latitude = latitude
                order.longitude = longitude
                order.h3_index = h3_index
                order.zone_id = zone_id
                order.depot_id = depot_id
        except Exception as e:
            print(f"Warning: Failed to re-geocode address: {e}")
    
    order = crud.order.update(db=db, db_obj=order, obj_in=order_in)
    return order


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_order(
    *,
    db: Session = Depends(get_db),
    id: UUID
):
    """Delete an order"""
    order = crud.order.get(db=db, id=id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )
    crud.order.remove(db=db, id=id)
    return None









