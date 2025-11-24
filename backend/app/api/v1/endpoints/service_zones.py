from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app import crud, schemas

router = APIRouter()


@router.post("/", response_model=schemas.ServiceZone, status_code=status.HTTP_201_CREATED)
def create_service_zone(
    *,
    db: Session = Depends(get_db),
    service_zone_in: schemas.ServiceZoneCreate
) -> schemas.ServiceZone:
    """Create a new service zone."""
    # Verify service area exists
    service_area = crud.service_area.get(db=db, id=service_zone_in.service_area_id)
    if not service_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service area not found"
        )
    
    service_zone = crud.service_zone.create(db=db, obj_in=service_zone_in)
    return service_zone


@router.get("/", response_model=List[schemas.ServiceZoneWithH3])
def read_service_zones(
    skip: int = 0,
    limit: int = 100,
    service_area_id: Optional[UUID] = None,
    active_only: bool = False,
    include_h3: bool = Query(True, description="Include H3 coverage in response"),
    resolutions: Optional[str] = Query(None, description="Comma-separated H3 resolutions"),
    db: Session = Depends(get_db)
) -> List[schemas.ServiceZoneWithH3]:
    """Get all service zones with optional H3 coverage."""
    
    # Parse resolutions
    res_list = None
    if resolutions:
        try:
            res_list = [int(r.strip()) for r in resolutions.split(',')]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid resolutions format. Use comma-separated integers."
            )
    
    if include_h3:
        # Get with H3 coverage
        results = crud.service_zone.get_multi_with_h3_coverage(
            db=db, skip=skip, limit=limit, service_area_id=service_area_id, resolutions=res_list
        )
        return [
            schemas.ServiceZoneWithH3(
                **schemas.ServiceZone.model_validate(zone).model_dump(),
                h3_coverage=h3_coverage
            )
            for zone, h3_coverage in results
        ]
    else:
        # Get without H3 coverage
        if service_area_id:
            if active_only:
                service_zones = crud.service_zone.get_active_by_service_area(
                    db=db, service_area_id=service_area_id, skip=skip, limit=limit
                )
            else:
                service_zones = crud.service_zone.get_by_service_area(
                    db=db, service_area_id=service_area_id, skip=skip, limit=limit
                )
        else:
            service_zones = crud.service_zone.get_multi(db=db, skip=skip, limit=limit)
        return [
            schemas.ServiceZoneWithH3(**schemas.ServiceZone.model_validate(zone).model_dump())
            for zone in service_zones
        ]


@router.get("/{id}", response_model=schemas.ServiceZoneWithH3)
def read_service_zone(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    include_h3: bool = Query(True, description="Include H3 coverage in response"),
    resolutions: Optional[str] = Query(None, description="Comma-separated H3 resolutions")
) -> schemas.ServiceZoneWithH3:
    """Get a specific service zone by ID with optional H3 coverage."""
    
    # Parse resolutions
    res_list = None
    if resolutions:
        try:
            res_list = [int(r.strip()) for r in resolutions.split(',')]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid resolutions format. Use comma-separated integers."
            )
    
    if include_h3:
        service_zone, h3_coverage = crud.service_zone.get_with_h3_coverage(
            db=db, id=id, resolutions=res_list
        )
        if not service_zone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service zone not found"
            )
        return schemas.ServiceZoneWithH3(
            **schemas.ServiceZone.model_validate(service_zone).model_dump(),
            h3_coverage=h3_coverage
        )
    else:
        service_zone = crud.service_zone.get(db=db, id=id)
        if not service_zone:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service zone not found"
            )
        return schemas.ServiceZoneWithH3(**schemas.ServiceZone.model_validate(service_zone).model_dump())


@router.put("/{id}", response_model=schemas.ServiceZone)
def update_service_zone(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    service_zone_in: schemas.ServiceZoneUpdate
) -> schemas.ServiceZone:
    """Update a service zone."""
    service_zone = crud.service_zone.get(db=db, id=id)
    if not service_zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service zone not found"
        )
    
    # Verify service area exists if being updated
    if service_zone_in.service_area_id:
        service_area = crud.service_area.get(db=db, id=service_zone_in.service_area_id)
        if not service_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service area not found"
            )
    
    service_zone = crud.service_zone.update(db=db, db_obj=service_zone, obj_in=service_zone_in)
    return service_zone


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_zone(
    *,
    db: Session = Depends(get_db),
    id: UUID
):
    """Delete a service zone."""
    service_zone = crud.service_zone.get(db=db, id=id)
    if not service_zone:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service zone not found"
        )
    crud.service_zone.remove(db=db, id=id)
    return None

