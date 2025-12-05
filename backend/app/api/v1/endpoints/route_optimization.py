"""API endpoints for Route Optimization"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app import crud, schemas
from app.services.mapbox_service import MapboxService
from app.services.clustering_service import ClusteringService
from app.services.route_optimization_service import RouteOptimizationService
import numpy as np
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/optimize", response_model=schemas.RouteOptimizationResult)
def optimize_routes(
    *,
    db: Session = Depends(get_db),
    request: schemas.RouteOptimizationRequest
) -> schemas.RouteOptimizationResult:
    """
    Optimize delivery routes for a depot using OR-Tools VRP solver.
    
    Process:
    1. Fetch orders for depot/date (or use provided order_ids)
    2. Optional: Run HDBSCAN clustering to pre-group orders
    3. Get distance matrix from Mapbox Matrix API
    4. Run OR-Tools VRP solver
    5. Return optimized routes (not persisted to database)
    """
    logger.info(f"Starting route optimization for depot: {request.depot_id}")
    
    # 1. Get depot
    depot = crud.depot.get(db=db, id=request.depot_id)
    if not depot:
        logger.error(f"Depot not found: {request.depot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    logger.info(f"Depot found: {depot.name} (drivers: {depot.available_drivers})")
    
    # 2. Get orders
    if request.order_ids:
        logger.info(f"Fetching {len(request.order_ids)} specific orders")
        orders = [crud.order.get(db=db, id=oid) for oid in request.order_ids]
        orders = [o for o in orders if o is not None]
    else:
        logger.info(f"Fetching all orders for depot {depot.name}")
        orders = crud.order.get_by_depot(
            db=db,
            depot_id=request.depot_id,
            delivery_date=None,
            limit=1000
        )
    
    logger.info(f"Found {len(orders)} orders to optimize")
    
    if not orders:
        logger.warning("No orders found for optimization")
        return schemas.RouteOptimizationResult(
            success=True,
            routes=[],
            total_routes=0,
            total_orders=0,
            total_distance_km=0.0,
            total_duration_minutes=0.0,
            unassigned_orders=[],
            solver_status="NO_ORDERS",
            metadata={"message": "No orders found for optimization"}
        )
    
    # 3. Prepare coordinates (standard format: latitude, longitude)
    depot_coords = (depot.latitude, depot.longitude)
    order_coords = [(order.latitude, order.longitude) for order in orders]
    order_ids_list = [order.id for order in orders]
    
    # Validate depot coordinates
    if not (-90 <= depot_coords[0] <= 90 and -180 <= depot_coords[1] <= 180):
        logger.error(f"Invalid depot coordinates: {depot_coords}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid depot coordinates: {depot_coords}"
        )
    
    # 4. Optional: Run clustering
    cluster_labels = None
    original_cluster_labels = None
    cluster_metadata = {}
    
    if request.use_clustering and len(orders) >= request.min_cluster_size:
        effective_min_cluster_size = min(request.min_cluster_size, max(3, len(orders) // 30))
        logger.info(f"Running HDBSCAN clustering (min_cluster_size={effective_min_cluster_size})")

        try:
            clustering_result = ClusteringService.cluster_orders(
                order_coords,
                min_cluster_size=effective_min_cluster_size,
                adaptive_clustering=True,
                merge_small_clusters=True,
                max_cluster_size_for_merge=5,
                max_merge_distance_km=1.0
            )
            cluster_labels = clustering_result["labels"]
            original_cluster_labels = clustering_result.get("original_labels", cluster_labels)
            cluster_metadata = {
                "n_clusters": int(clustering_result["n_clusters"]),
                "outlier_count": int(clustering_result["outlier_count"]),
                "centroids": {int(k): list(v) for k, v in clustering_result["centroids"].items()},
                "original_labels": original_cluster_labels.tolist()
            }

            unique_labels, counts = np.unique(cluster_labels, return_counts=True)
            logger.info(f"Clustering complete: {cluster_metadata['n_clusters']} clusters, {cluster_metadata['outlier_count']} outliers")

            # Calculate drivers needed per cluster
            driver_capacity = 15
            cluster_driver_counts = {}
            total_drivers_needed = 0

            for label in unique_labels:
                cluster_size = counts[list(unique_labels).index(label)]
                drivers_needed = max(1, int(np.ceil(cluster_size / driver_capacity)))
                cluster_driver_counts[label] = drivers_needed
                total_drivers_needed += drivers_needed

            cluster_metadata["cluster_driver_counts"] = {int(k): int(v) for k, v in cluster_driver_counts.items()}
            cluster_metadata["total_drivers_needed"] = int(total_drivers_needed)

            # Update cluster assignments in database
            crud.order.update_cluster_assignments(
                db=db,
                order_ids=order_ids_list,
                cluster_labels=cluster_labels.tolist()
            )
        except Exception as e:
            logger.error(f"Clustering error: {e}")
            cluster_labels = None
    else:
        logger.info(f"Skipping clustering (use_clustering={request.use_clustering}, orders={len(orders)})")
    
    # 5. Get distance matrix from Mapbox
    logger.info(f"Fetching distance matrix from Mapbox ({len(orders) + 1} locations)")
    mapbox_service = MapboxService()
    
    max_retries = 2
    valid_orders = orders.copy()
    valid_order_coords = order_coords.copy()
    excluded_orders = []
    
    for attempt in range(max_retries):
        try:
            if len(valid_orders) <= 24:
                all_coords = [depot_coords] + valid_order_coords
                distance_matrix = mapbox_service.get_distance_matrix(all_coords, profile="driving")
            else:
                distance_matrix = mapbox_service.get_distance_matrix_chunked(
                    depot_coords,
                    valid_order_coords,
                    profile="driving"
                )
            
            if distance_matrix is None:
                raise ValueError("Failed to get distance matrix from Mapbox")
            
            logger.info(f"Distance matrix retrieved: {distance_matrix.shape}")
            orders = valid_orders
            order_coords = valid_order_coords
            break
            
        except Exception as e:
            if attempt < max_retries - 1 and len(valid_orders) > 1:
                logger.warning(f"Mapbox routing failed (attempt {attempt + 1}/{max_retries}): {e}")
                
                new_valid_orders = []
                new_valid_coords = []
                
                for order, coord in zip(valid_orders, valid_order_coords):
                    try:
                        test_matrix = mapbox_service.get_distance_matrix(
                            [depot_coords, coord],
                            profile="driving"
                        )
                        if test_matrix is not None:
                            new_valid_orders.append(order)
                            new_valid_coords.append(coord)
                        else:
                            excluded_orders.append(order)
                            logger.warning(f"Excluding order {order.order_number}: No valid route")
                    except Exception:
                        excluded_orders.append(order)
                
                if len(new_valid_orders) < len(valid_orders):
                    valid_orders = new_valid_orders
                    valid_order_coords = new_valid_coords
                    
                    if len(valid_orders) == 0:
                        return schemas.RouteOptimizationResult(
                            success=False,
                            routes=[],
                            total_routes=0,
                            total_orders=0,
                            total_distance_km=0.0,
                            total_duration_minutes=0.0,
                            unassigned_orders=[o.id for o in excluded_orders],
                            solver_status="NO_VALID_ORDERS",
                            used_clustering=False,
                            num_clusters=0,
                            metadata={"error": "All orders are unroutable from this depot"}
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error getting distance matrix: {str(e)}"
                    )
            else:
                logger.error(f"Distance matrix error: {e}")
                if len(valid_orders) == 0:
                    return schemas.RouteOptimizationResult(
                        success=False,
                        routes=[],
                        total_routes=0,
                        total_orders=0,
                        total_distance_km=0.0,
                        total_duration_minutes=0.0,
                        unassigned_orders=[],
                        solver_status="NO_VALID_ORDERS",
                        used_clustering=False,
                        num_clusters=0,
                        metadata={"error": "No orders could be routed"}
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error getting distance matrix: {str(e)}"
                )
    
    if excluded_orders:
        logger.warning(f"Excluded {len(excluded_orders)} orders due to routing issues")
        order_ids_list = [order.id for order in orders]
        
        # Re-run clustering if needed
        if cluster_labels is not None and len(orders) >= 5:
            effective_min_cluster_size = min(request.min_cluster_size, max(3, len(orders) // 30))
            try:
                clustering_result = ClusteringService.cluster_orders(
                    order_coords,
                    min_cluster_size=effective_min_cluster_size
                )
                cluster_labels = clustering_result["labels"]
                cluster_metadata = {
                    "n_clusters": int(clustering_result["n_clusters"]),
                    "outlier_count": int(clustering_result["outlier_count"]),
                    "centroids": {int(k): list(v) for k, v in clustering_result["centroids"].items()}
                }
            except Exception as e:
                logger.warning(f"Re-clustering failed: {e}")
                cluster_labels = None
                cluster_metadata = {}
    
    # 6. Determine number of vehicles
    if cluster_labels is not None and cluster_metadata.get("total_drivers_needed"):
        calculated_vehicles = cluster_metadata["total_drivers_needed"]
        num_vehicles = min(calculated_vehicles, depot.available_drivers)
    elif cluster_labels is not None and cluster_metadata.get("n_clusters", 0) > 0:
        calculated_vehicles = cluster_metadata["n_clusters"]
        num_vehicles = min(calculated_vehicles, depot.available_drivers)
    else:
        num_vehicles = request.num_vehicles if request.num_vehicles else min(depot.available_drivers, max(1, len(orders) // 50))
    
    logger.info(f"Using {num_vehicles} vehicles")
    
    if num_vehicles <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of vehicles must be greater than 0"
        )
    
    # 7. Run OR-Tools VRP solver
    logger.info(f"Running OR-Tools VRP solver with {num_vehicles} vehicles")
    
    try:
        optimization_result = RouteOptimizationService.optimize_routes(
            depot_coords,
            order_coords,
            distance_matrix,
            num_vehicles,
            order_ids=[str(oid) for oid in order_ids_list],
            cluster_labels=cluster_labels
        )
        
        logger.info(f"Optimization complete: {len(optimization_result['routes'])} routes, status: {optimization_result['solver_status']}")
        
    except Exception as e:
        logger.error(f"Optimization error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error optimizing routes: {str(e)}"
        )
    
    # 8. Format response
    optimized_routes = []

    for route in optimization_result["routes"]:
        stops = []
        for stop in route["stops"]:
            order_idx = stop["order_index"]
            order = orders[order_idx]
            
            stops.append(schemas.RouteStop(
                order_id=order.id,
                order_number=order.order_number,
                customer_name=order.customer_name,
                address=order.delivery_address,
                latitude=order.latitude,
                longitude=order.longitude,
                sequence=stop["sequence"]
            ))
        
        cluster_id = None
        if cluster_labels is not None:
            stop_clusters = [int(cluster_labels[stop["order_index"]]) for stop in route["stops"]]
            if stop_clusters:
                cluster_id = int(np.bincount(stop_clusters).argmax())
        
        optimized_route = schemas.OptimizedRoute(
            vehicle_id=int(route["vehicle_id"]),
            stops=stops,
            num_stops=len(stops),
            total_distance_km=float(route["total_distance"]) / 1000.0,
            estimated_duration_minutes=float(route["total_time"]) / 60.0,
            cluster_id=int(cluster_id) if cluster_id is not None else None
        )
        optimized_routes.append(optimized_route)
    
    # Handle unassigned orders
    unassigned_order_ids = []
    for idx in optimization_result.get("unassigned", []):
        idx_int = int(idx)
        if 0 <= idx_int < len(order_ids_list):
            unassigned_order_ids.append(order_ids_list[idx_int])
    
    is_successful = (
        optimization_result["solver_status"] in ["SUCCESS", "ROUTING_SUCCESS", "PARTIAL_SUCCESS"]
        and len(optimized_routes) > 0
    )
    
    result = schemas.RouteOptimizationResult(
        success=is_successful,
        routes=optimized_routes,
        total_routes=len(optimized_routes),
        total_orders=len(orders) - len(unassigned_order_ids),
        total_distance_km=float(optimization_result["total_distance"]) / 1000.0,
        total_duration_minutes=float(optimization_result["total_time"]) / 60.0,
        unassigned_orders=unassigned_order_ids,
        solver_status=optimization_result["solver_status"],
        used_clustering=cluster_labels is not None,
        num_clusters=(
            int(cluster_metadata.get("n_clusters", 0)) + 
            int(cluster_metadata.get("outlier_count", 0))
        ) if cluster_labels is not None else None,
        outlier_count=int(cluster_metadata.get("outlier_count")) if cluster_metadata.get("outlier_count") is not None else None,
        metadata={
            "depot_id": str(request.depot_id),
            "depot_name": depot.name,
            "depot_location": {"lat": float(depot.latitude), "lng": float(depot.longitude)},
            "num_vehicles_requested": int(num_vehicles),
            "num_vehicles_used": int(optimization_result.get("num_vehicles_used", 0)),
            "clustering": cluster_metadata if cluster_labels is not None else None,
            "cluster_assignments": {
                str(order.id): int(cluster_labels[i]) if cluster_labels is not None else None
                for i, order in enumerate(orders)
            } if cluster_labels is not None else None,
            "original_cluster_assignments": {
                str(order.id): int(original_cluster_labels[i]) if original_cluster_labels is not None else None
                for i, order in enumerate(orders)
            } if cluster_labels is not None and original_cluster_labels is not None else None,
            "total_groups": (
                int(cluster_metadata.get("n_clusters", 0)) + 
                int(cluster_metadata.get("outlier_count", 0))
            ) if cluster_labels is not None else None
        }
    )
    
    logger.info(f"Route optimization complete: {result.total_routes} routes, {result.total_orders} orders")
    
    return result


@router.get("/test-connection", response_model=dict)
def test_services_connection(
    db: Session = Depends(get_db)
) -> dict:
    """Test connection to external services"""
    from app.services.clustering_service import HDBSCAN_AVAILABLE
    
    status_dict = {
        "mapbox": False,
        "hdbscan": HDBSCAN_AVAILABLE,
        "ortools": True,  # OR-Tools is a required dependency
        "database": False
    }
    
    # Test Mapbox
    try:
        mapbox_service = MapboxService()
        test_coords = [(45.4215, -75.6972), (45.4200, -75.6900)]
        matrix = mapbox_service.get_distance_matrix(test_coords)
        status_dict["mapbox"] = matrix is not None
    except Exception as e:
        status_dict["mapbox"] = f"Error: {str(e)}"
    
    # Test Database
    try:
        crud.depot.get_multi(db=db, skip=0, limit=1)
        status_dict["database"] = True
    except Exception as e:
        status_dict["database"] = f"Error: {str(e)}"
    
    return {
        "status": "ok" if all(v is True for v in status_dict.values() if isinstance(v, bool)) else "degraded",
        "services": status_dict
    }
