"""API endpoints for Zone-Depot Assignments"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app import crud, schemas

router = APIRouter()


@router.post("/", response_model=schemas.ZoneDepotAssignment, status_code=status.HTTP_201_CREATED)
def create_assignment(
    *,
    db: Session = Depends(get_db),
    assignment_in: schemas.ZoneDepotAssignmentCreate
) -> schemas.ZoneDepotAssignment:
    """Assign a zone to a depot"""
    # Verify zone exists
    zone = crud.service_zone.get(db=db, id=assignment_in.zone_id)
    if not zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service zone not found"
        )
    
    # Verify depot exists
    depot = crud.depot.get(db=db, id=assignment_in.depot_id)
    if not depot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    # Check if assignment already exists
    existing = crud.zone_depot_assignment.get(
        db=db,
        zone_id=assignment_in.zone_id,
        depot_id=assignment_in.depot_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment already exists"
        )
    
    assignment = crud.zone_depot_assignment.create(db=db, obj_in=assignment_in)
    return assignment


@router.get("/zones/{zone_id}/depot", response_model=schemas.ZoneDepotAssignment)
def get_zone_depot(
    *,
    db: Session = Depends(get_db),
    zone_id: UUID
) -> schemas.ZoneDepotAssignment:
    """Get the primary depot for a zone"""
    assignments = crud.zone_depot_assignment.get_by_zone(db=db, zone_id=zone_id)
    
    # Find primary assignment
    primary = next((a for a in assignments if a.is_primary), None)
    
    if not primary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No depot assigned to this zone"
        )
    
    return primary


@router.delete("/{zone_id}/{depot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    *,
    db: Session = Depends(get_db),
    zone_id: UUID,
    depot_id: UUID
):
    """Remove a zone-depot assignment"""
    success = crud.zone_depot_assignment.delete(
        db=db,
        zone_id=zone_id,
        depot_id=depot_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found"
        )
    return None









