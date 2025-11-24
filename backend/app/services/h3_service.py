"""H3 service extensions for zone lookup and depot assignment"""
from typing import Optional
from uuid import UUID
import h3
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, func
from app.models import ServiceZone
from app.models.zone_depot_assignment import ZoneDepotAssignment
from app.core.config import settings


class H3Service:
    """Service for H3 spatial operations"""
    
    @staticmethod
    def lat_lng_to_h3(latitude: float, longitude: float, resolution: Optional[int] = None) -> str:
        """
        Convert lat/lng coordinates to H3 cell index.
        
        Args:
            latitude: Latitude
            longitude: Longitude
            resolution: H3 resolution (0-15), defaults to config setting
        
        Returns:
            H3 cell index string
        """
        res = resolution or settings.DEFAULT_H3_RESOLUTION
        return h3.geo_to_h3(latitude, longitude, res)
    
    @staticmethod
    def get_zone_from_coordinates(
        db: Session,
        latitude: float,
        longitude: float,
        resolution: Optional[int] = None
    ) -> Optional[UUID]:
        """
        Lookup which ServiceZone contains the given coordinates using H3 index.
        
        Args:
            db: Database session
            latitude: Latitude
            longitude: Longitude
            resolution: H3 resolution, defaults to config setting
        
        Returns:
            ServiceZone UUID or None if not found
        """
        try:
            # Get H3 index for the coordinates
            h3_index = H3Service.lat_lng_to_h3(latitude, longitude, resolution)
            
            # Query for zones that contain this H3 cell
            # This requires checking H3 coverage or using PostGIS ST_Contains
            from app.models.h3_cover import H3Cover, OwnerKind
            
            stmt = select(H3Cover.owner_id).where(
                and_(
                    H3Cover.owner_kind == OwnerKind.SERVICE_ZONE,
                    H3Cover.cell == h3_index
                )
            ).limit(1)
            
            result = db.execute(stmt).scalar_one_or_none()
            
            if result:
                return result
            
            # Fallback: Use PostGIS spatial query if H3 lookup fails
            # This is more expensive but handles edge cases
            point_wkt = f"POINT({longitude} {latitude})"
            
            stmt = select(ServiceZone.id).where(
                func.ST_Contains(
                    ServiceZone.boundary,
                    func.ST_GeomFromText(point_wkt, 4326)
                )
            ).limit(1)
            
            result = db.execute(stmt).scalar_one_or_none()
            
            return result
            
        except Exception as e:
            print(f"Error finding zone for coordinates ({latitude}, {longitude}): {e}")
            return None
    
    @staticmethod
    def assign_depot_from_zone(db: Session, zone_id: UUID) -> Optional[UUID]:
        """
        Get the depot ID assigned to a service zone.
        
        Args:
            db: Database session
            zone_id: ServiceZone UUID
        
        Returns:
            Depot UUID or None if no assignment found
        """
        try:
            stmt = select(ZoneDepotAssignment.depot_id).where(
                and_(
                    ZoneDepotAssignment.zone_id == zone_id,
                    ZoneDepotAssignment.is_primary == True
                )
            ).limit(1)
            
            result = db.execute(stmt).scalar_one_or_none()
            
            return result
            
        except Exception as e:
            print(f"Error finding depot for zone {zone_id}: {e}")
            return None
    
    @staticmethod
    def geocode_and_assign(
        db: Session,
        latitude: float,
        longitude: float,
        resolution: Optional[int] = None
    ) -> tuple[str, Optional[UUID], Optional[UUID]]:
        """
        Complete geocoding workflow: coordinates -> H3 -> zone -> depot.
        
        Args:
            db: Database session
            latitude: Latitude
            longitude: Longitude
            resolution: H3 resolution
        
        Returns:
            Tuple of (h3_index, zone_id, depot_id)
        """
        # Get H3 index
        h3_index = H3Service.lat_lng_to_h3(latitude, longitude, resolution)
        
        # Get zone
        zone_id = H3Service.get_zone_from_coordinates(db, latitude, longitude, resolution)
        
        # Get depot if zone found
        depot_id = None
        if zone_id:
            depot_id = H3Service.assign_depot_from_zone(db, zone_id)
        
        return (h3_index, zone_id, depot_id)

