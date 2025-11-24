"""API endpoints for Depots"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app import crud, schemas
from app.models.order import OrderStatus
from datetime import date

router = APIRouter()


@router.post("/", response_model=schemas.Depot, status_code=status.HTTP_201_CREATED)
def create_depot(
    *,
    db: Session = Depends(get_db),
    depot_in: schemas.DepotCreate
) -> schemas.Depot:
    """Create a new depot"""
    depot = crud.depot.create(db=db, obj_in=depot_in)
    return depot


@router.get("/", response_model=List[schemas.Depot])
def list_depots(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = Query(False, description="Only return active depots"),
    db: Session = Depends(get_db)
) -> List[schemas.Depot]:
    """Get all depots"""
    if active_only:
        depots = crud.depot.get_active(db=db, skip=skip, limit=limit)
    else:
        depots = crud.depot.get_multi(db=db, skip=skip, limit=limit)
    return depots


@router.get("/{id}", response_model=schemas.Depot)
def get_depot(
    *,
    db: Session = Depends(get_db),
    id: UUID
) -> schemas.Depot:
    """Get a specific depot by ID"""
    depot = crud.depot.get(db=db, id=id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    return depot


@router.put("/{id}", response_model=schemas.Depot)
def update_depot(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    depot_in: schemas.DepotUpdate
) -> schemas.Depot:
    """Update a depot"""
    depot = crud.depot.get(db=db, id=id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    depot = crud.depot.update(db=db, db_obj=depot, obj_in=depot_in)
    return depot


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_depot(
    *,
    db: Session = Depends(get_db),
    id: UUID
):
    """Delete a depot"""
    depot = crud.depot.get(db=db, id=id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    crud.depot.remove(db=db, id=id)
    return None


@router.get("/{id}/orders", response_model=List[schemas.Order])
def get_depot_orders(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[OrderStatus] = Query(None, alias="status"),
    delivery_date: Optional[date] = None
) -> List[schemas.Order]:
    """Get orders for a specific depot"""
    depot = crud.depot.get(db=db, id=id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    orders = crud.order.get_by_depot(
        db=db,
        depot_id=id,
        skip=skip,
        limit=limit,
        status=status_filter,
        delivery_date=delivery_date
    )
    return orders


@router.get("/{id}/zones", response_model=List[schemas.ZoneDepotAssignment])
def get_depot_zones(
    *,
    db: Session = Depends(get_db),
    id: UUID
) -> List[schemas.ZoneDepotAssignment]:
    """Get zones assigned to a depot"""
    depot = crud.depot.get(db=db, id=id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    assignments = crud.zone_depot_assignment.get_by_depot(db=db, depot_id=id)
    return assignments









