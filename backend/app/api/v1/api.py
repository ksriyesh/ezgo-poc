from fastapi import APIRouter
from app.api.v1.endpoints import (
    service_areas,
    service_zones,
    depots,
    orders,
    route_optimization,
    zone_depot_assignments
)

api_router = APIRouter()
api_router.include_router(service_areas.router, prefix="/service-areas", tags=["service-areas"])
api_router.include_router(service_zones.router, prefix="/service-zones", tags=["service-zones"])
api_router.include_router(depots.router, prefix="/depots", tags=["depots"])
api_router.include_router(orders.router, prefix="/orders", tags=["orders"])
api_router.include_router(route_optimization.router, prefix="/routes", tags=["route-optimization"])
api_router.include_router(zone_depot_assignments.router, prefix="/zone-depot-assignments", tags=["zone-depot-assignments"])

