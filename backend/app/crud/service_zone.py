from typing import List, Optional, Dict
from uuid import UUID
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import shape
from shapely import wkt
import json
from app.crud.base import CRUDBase
from app.models.service_zone import ServiceZone
from app.models.h3_cover import OwnerKind
from app.schemas.service_zone import ServiceZoneCreate, ServiceZoneUpdate
from app.crud.h3_helper import get_h3_coverage


class CRUDServiceZone(CRUDBase[ServiceZone, ServiceZoneCreate, ServiceZoneUpdate]):
    """CRUD operations for ServiceZone."""
    
    def _parse_geometry(self, boundary_str: str):
        """Parse geometry from GeoJSON string or WKT string."""
        try:
            if boundary_str.strip().startswith('{'):
                geojson = json.loads(boundary_str)
                geom = shape(geojson)
            else:
                geom = wkt.loads(boundary_str)
            return geom
        except Exception as e:
            raise ValueError(f"Invalid geometry format: {str(e)}")
    
    def create(self, db: Session, *, obj_in: ServiceZoneCreate) -> ServiceZone:
        """Create a new service zone with geometry parsing."""
        obj_in_data = obj_in.model_dump(exclude={"boundary"})
        
        # Parse and convert geometry
        geom = self._parse_geometry(obj_in.boundary)
        boundary_geom = from_shape(geom, srid=4326)
        
        db_obj = ServiceZone(**obj_in_data, boundary=boundary_geom)
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def update(
        self,
        db: Session,
        *,
        db_obj: ServiceZone,
        obj_in: ServiceZoneUpdate
    ) -> ServiceZone:
        """Update a service zone, handling geometry if provided."""
        update_data = obj_in.model_dump(exclude_unset=True, exclude={"boundary"})
        
        if obj_in.boundary:
            geom = self._parse_geometry(obj_in.boundary)
            update_data["boundary"] = from_shape(geom, srid=4326)
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj
    
    def get_by_service_area(
        self, db: Session, *, service_area_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[ServiceZone]:
        """Get all zones for a service area."""
        return (
            db.query(ServiceZone)
            .filter(ServiceZone.service_area_id == service_area_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
    
    def get_active_by_service_area(
        self, db: Session, *, service_area_id: UUID, skip: int = 0, limit: int = 100
    ) -> List[ServiceZone]:
        """Get all active zones for a service area."""
        return (
            db.query(ServiceZone)
            .filter(
                ServiceZone.service_area_id == service_area_id,
                ServiceZone.is_active == True
            )
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
    ) -> tuple[Optional[ServiceZone], Dict]:
        """
        Get a service zone with its H3 coverage at specified resolutions.
        Returns (service_zone, h3_coverage_dict)
        """
        service_zone = self.get(db=db, id=id)
        if not service_zone:
            return None, {}
        
        h3_coverage = get_h3_coverage(
            db=db,
            owner_kind=OwnerKind.SERVICE_ZONE,
            owner_id=id,
            resolutions=resolutions
        )
        
        return service_zone, h3_coverage
    
    def get_multi_with_h3_coverage(
        self,
        db: Session,
        *,
        skip: int = 0,
        limit: int = 100,
        service_area_id: UUID = None,
        resolutions: List[int] = None
    ) -> List[tuple[ServiceZone, Dict]]:
        """
        Get multiple service zones with their H3 coverage.
        Returns list of (service_zone, h3_coverage_dict) tuples
        """
        if service_area_id:
            service_zones = self.get_by_service_area(
                db=db, service_area_id=service_area_id, skip=skip, limit=limit
            )
        else:
            service_zones = self.get_multi(db=db, skip=skip, limit=limit)
        
        results = []
        for zone in service_zones:
            h3_coverage = get_h3_coverage(
                db=db,
                owner_kind=OwnerKind.SERVICE_ZONE,
                owner_id=zone.id,
                resolutions=resolutions
            )
            results.append((zone, h3_coverage))
        
        return results


service_zone = CRUDServiceZone(ServiceZone)

