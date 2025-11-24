from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from geoalchemy2.shape import to_shape
from shapely.geometry import mapping
from app.api.dependencies import get_db
from app import crud, schemas

router = APIRouter()


@router.post("/", response_model=schemas.ServiceArea, status_code=status.HTTP_201_CREATED)
def create_service_area(
    *,
    db: Session = Depends(get_db),
    service_area_in: schemas.ServiceAreaCreate
) -> schemas.ServiceArea:
    """Create a new service area."""
    # Check if name already exists
    existing = crud.service_area.get_by_name(db, name=service_area_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Service area with this name already exists"
        )
    
    service_area = crud.service_area.create(db=db, obj_in=service_area_in)
    return service_area


@router.get("/", response_model=List[schemas.ServiceAreaWithH3])
def read_service_areas(
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
    include_h3: bool = Query(True, description="Include H3 coverage in response"),
    resolutions: Optional[str] = Query(None, description="Comma-separated H3 resolutions (e.g., '8,9,10')"),
    db: Session = Depends(get_db)
) -> List[schemas.ServiceAreaWithH3]:
    """Get all service areas with optional H3 coverage."""
    
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
        results = crud.service_area.get_multi_with_h3_coverage(
            db=db, skip=skip, limit=limit, resolutions=res_list
        )
        return [
            schemas.ServiceAreaWithH3(
                **schemas.ServiceArea.model_validate(area).model_dump(),
                h3_coverage=h3_coverage
            )
            for area, h3_coverage in results
        ]
    else:
        # Get without H3 coverage
        if active_only:
            service_areas = crud.service_area.get_active(db=db, skip=skip, limit=limit)
        else:
            service_areas = crud.service_area.get_multi(db=db, skip=skip, limit=limit)
        return [
            schemas.ServiceAreaWithH3(**schemas.ServiceArea.model_validate(area).model_dump())
            for area in service_areas
        ]


@router.get("/{id}", response_model=schemas.ServiceAreaWithH3)
def read_service_area(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    include_h3: bool = Query(True, description="Include H3 coverage in response"),
    resolutions: Optional[str] = Query(None, description="Comma-separated H3 resolutions")
) -> schemas.ServiceAreaWithH3:
    """Get a specific service area by ID with optional H3 coverage."""
    
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
        service_area, h3_coverage = crud.service_area.get_with_h3_coverage(
            db=db, id=id, resolutions=res_list
        )
        if not service_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service area not found"
            )
        return schemas.ServiceAreaWithH3(
            **schemas.ServiceArea.model_validate(service_area).model_dump(),
            h3_coverage=h3_coverage
        )
    else:
        service_area = crud.service_area.get(db=db, id=id)
        if not service_area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service area not found"
            )
        return schemas.ServiceAreaWithH3(**schemas.ServiceArea.model_validate(service_area).model_dump())


@router.put("/{id}", response_model=schemas.ServiceArea)
def update_service_area(
    *,
    db: Session = Depends(get_db),
    id: UUID,
    service_area_in: schemas.ServiceAreaUpdate
) -> schemas.ServiceArea:
    """Update a service area."""
    service_area = crud.service_area.get(db=db, id=id)
    if not service_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service area not found"
        )
    
    # Check name uniqueness if name is being updated
    if service_area_in.name and service_area_in.name != service_area.name:
        existing = crud.service_area.get_by_name(db, name=service_area_in.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Service area with this name already exists"
            )
    
    service_area = crud.service_area.update(db=db, db_obj=service_area, obj_in=service_area_in)
    return service_area


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_area(
    *,
    db: Session = Depends(get_db),
    id: UUID
):
    """Delete a service area."""
    service_area = crud.service_area.get(db=db, id=id)
    if not service_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Service area not found"
        )
    crud.service_area.remove(db=db, id=id)
    return None

