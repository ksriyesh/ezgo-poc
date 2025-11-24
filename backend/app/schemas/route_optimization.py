"""Pydantic schemas for route optimization"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from uuid import UUID


class RouteOptimizationRequest(BaseModel):
    """Request schema for route optimization"""
    depot_id: UUID
    order_ids: Optional[List[UUID]] = None
    use_clustering: bool = True  # Default True - enables cluster penalties for geographic coherence
    min_cluster_size: int = Field(default=5, ge=2)
    num_vehicles: Optional[int] = None  # If not provided, uses depot.available_drivers


class RouteStop(BaseModel):
    """Individual stop in a route"""
    order_id: UUID
    order_number: str
    customer_name: str
    address: str
    latitude: float
    longitude: float
    sequence: int
    estimated_arrival_time: Optional[str] = None


class OptimizedRoute(BaseModel):
    """Optimized route for a vehicle"""
    vehicle_id: int
    stops: List[RouteStop]
    num_stops: int
    total_distance_km: float
    estimated_duration_minutes: float
    cluster_id: Optional[int] = None


class RouteOptimizationResult(BaseModel):
    """Result of route optimization"""
    success: bool
    routes: List[OptimizedRoute]
    total_routes: int
    total_orders: int
    total_distance_km: float
    total_duration_minutes: float
    unassigned_orders: List[UUID]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    solver_status: str
    
    # Clustering info (if used)
    used_clustering: bool = False
    num_clusters: Optional[int] = None
    outlier_count: Optional[int] = None


class RouteVisualization(BaseModel):
    """Route data formatted for map visualization"""
    depot: Dict[str, Any]
    routes: List[Dict[str, Any]]
    orders: List[Dict[str, Any]]
    bounds: Dict[str, float]  # min_lat, max_lat, min_lng, max_lng








