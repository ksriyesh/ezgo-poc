from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, mapping
from shapely import wkt
import json
from app.crud.base import CRUDBase
from app.models.service_area import ServiceArea
from app.models.h3_cover import OwnerKind
from app.schemas.service_area import ServiceAreaCreate, ServiceAreaUpdate
from app.crud.h3_helper import get_h3_coverage


class CRUDServiceArea(CRUDBase[ServiceArea, ServiceAreaCreate, ServiceAreaUpdate]):
    """CRUD operations for ServiceArea."""
    
    def _parse_geometry(self, boundary_str: str):
        """
        Parse geometry from GeoJSON string or WKT string.
        Returns a Shapely geometry object.
        """
        try:
            # Try parsing as GeoJSON
            if boundary_str.strip().startswith('{'):
                geojson = json.loads(boundary_str)
                geom = shape(geojson)
            else:
                # Try parsing as WKT
                geom = wkt.loads(boundary_str)
            return geom
        except Exception as e:
            raise ValueError(f"Invalid geometry format: {str(e)}")
    
    def create(self, db: Session, *, obj_in: ServiceAreaCreate) -> ServiceArea:
        """Create a new service area with geometry parsing."""
        obj_in_data = obj_in.model_dump(exclude={"boundary"})
        
        # Parse and convert geometry
        geom = self._parse_geometry(obj_in.boundary)
        boundary_geom = from_shape(geom, srid=4326)
        
        db_obj = ServiceArea(**obj_in_data, boundary=boundary_geom)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self,
        db: Session,
        *,
        db_obj: ServiceArea,
        obj_in: ServiceAreaUpdate
    ) -> ServiceArea:
        """Update a service area, handling geometry if provided."""
        update_data = obj_in.model_dump(exclude_unset=True, exclude={"boundary"})
        
        # Handle geometry update if provided
        if obj_in.boundary:
            geom = self._parse_geometry(obj_in.boundary)
            update_data["boundary"] = from_shape(geom, srid=4326)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_name(self, db: Session, *, name: str) -> Optional[ServiceArea]:
        """Get a service area by name."""
        return db.query(ServiceArea).filter(ServiceArea.name == name).first()
    
    def get_active(self, db: Session, *, skip: int = 0, limit: int = 100) -> List[ServiceArea]:
        """Get all active service areas."""
        return (
            db.query(ServiceArea)
            .filter(ServiceArea.is_active == True)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_with_h3_coverage(
        self, 
        db: Session, 
        *, 
        id: UUID, 
        resolutions: List[int] = None
    ) -> tuple[Optional[ServiceArea], Dict]:
        """
        Get a service area with its H3 coverage at specified resolutions.
        Returns (service_area, h3_coverage_dict)
        """
        service_area = self.get(db=db, id=id)
        if not service_area:
            return None, {}
        
        h3_coverage = get_h3_coverage(
            db=db,
            owner_kind=OwnerKind.SERVICE_AREA,
            owner_id=id,
            resolutions=resolutions
        )
        
        return service_area, h3_coverage
    
    def get_multi_with_h3_coverage(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        resolutions: List[int] = None
    ) -> List[tuple[ServiceArea, Dict]]:
        """
        Get multiple service areas with their H3 coverage.
        Returns list of (service_area, h3_coverage_dict) tuples
        """
        service_areas = self.get_multi(db=db, skip=skip, limit=limit)
        
        results = []
        for area in service_areas:
            h3_coverage = get_h3_coverage(
                db=db,
                owner_kind=OwnerKind.SERVICE_AREA,
                owner_id=area.id,
                resolutions=resolutions
            )
            results.append((area, h3_coverage))
        
        return results


service_area = CRUDServiceArea(ServiceArea)

