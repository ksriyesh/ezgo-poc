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
    
    logger.info(f"🚀 Starting route optimization for depot: {request.depot_id}")
    print(f"\n{'='*80}")
    print(f"[DEBUG] 🚀 NEW ROUTE OPTIMIZATION REQUEST")
    print(f"{'='*80}")
    print(f"Request data: {request.model_dump()}")
    print(f"Depot ID: {request.depot_id}")
    print(f"Use Clustering: {request.use_clustering}")
    print(f"Min Cluster Size: {request.min_cluster_size}")
    print(f"Num Vehicles: {request.num_vehicles}")
    print(f"Order IDs: {request.order_ids[:3] if request.order_ids else 'ALL'}")
    print(f"{'='*80}\n")
    
    # 1. Get depot
    depot = crud.depot.get(db=db, id=request.depot_id)
    if not depot:
        logger.error(f"❌ Depot not found: {request.depot_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Depot not found"
        )
    
    print(f"🏭 [DEBUG] Depot Details:")
    print(f"   Name: {depot.name}")
    print(f"   ID: {depot.id}")
    print(f"   Drivers: {depot.available_drivers}")
    print(f"   Location: ({depot.latitude}, {depot.longitude})")
    print()
    logger.info(f"✅ Depot found: {depot.name} (ID: {depot.id}, drivers: {depot.available_drivers})")
    
    # 2. Get orders
    if request.order_ids:
        # Fetch specific orders
        logger.info(f"📦 Fetching {len(request.order_ids)} specific orders...")
        orders = [crud.order.get(db=db, id=oid) for oid in request.order_ids]
        orders = [o for o in orders if o is not None]
    else:
        # Fetch all orders for depot
        logger.info(f"📦 Fetching ALL orders for depot {depot.name}")
        orders = crud.order.get_by_depot(
            db=db,
            depot_id=request.depot_id,
            delivery_date=None,  # Get all orders
            limit=1000
        )
    
    logger.info(f"📊 Found {len(orders)} orders to optimize")
    print(f"\n[DEBUG] Orders fetched: {len(orders)}")
    if orders:
        print(f"[DEBUG] First 3 orders:")
        for i, order in enumerate(orders[:3]):
            print(f"  {i+1}. {order.order_number} - {order.customer_name} - Status: {order.status}")
    print()
    
    # DEBUG: Print orders info
    print(f"📦 DEBUG: Found {len(orders)} orders")
    if orders:
        print(f"   First order: {orders[0].order_number}, Location: ({orders[0].latitude}, {orders[0].longitude})")
        print(f"   Last order: {orders[-1].order_number}, Location: ({orders[-1].latitude}, {orders[-1].longitude})")
    print()
    
    if not orders:
        logger.warning("⚠️  No orders found for optimization")
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
    
    # 3. Prepare coordinates
    # NOTE: Depots have coordinates swapped in DB (latitude column has longitude values and vice versa)
    # Orders are stored correctly in DB (not swapped)
    # Standard format: (latitude, longitude) throughout codebase
    depot_coords = (depot.longitude, depot.latitude)  # Swap: DB lat column = actual lng, DB lng column = actual lat
    order_coords = [(order.latitude, order.longitude) for order in orders]  # Orders are NOT swapped in DB, use as-is
    order_ids_list = [order.id for order in orders]
    
    # DEBUG: Print swapped coordinates
    print(f"🔍 [DEBUG] Coordinate swap check:")
    print(f"   DB depot.latitude={depot.latitude}, depot.longitude={depot.longitude}")
    print(f"   Swapped depot_coords={depot_coords} (should be lat, lng)")
    if orders:
        print(f"   DB order[0].latitude={orders[0].latitude}, order[0].longitude={orders[0].longitude}")
        print(f"   order_coords[0]={order_coords[0]} (should be lat, lng - orders NOT swapped in DB)")
    
    # Validate depot coordinates (basic check)
    # depot_coords is (lat, lng) after swap, so [0] is lat, [1] is lng
    if not (-90 <= depot_coords[0] <= 90 and -180 <= depot_coords[1] <= 180):
        logger.error(f"❌ Invalid depot coordinates: {depot_coords}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid depot coordinates: {depot_coords}"
        )
    
    # 4. Optional: Run clustering
    cluster_labels = None
    original_cluster_labels = None
    cluster_metadata = {}
    
    # Always cluster first (recommended approach for better routes)
    # Skip only if dataset is too small (need at least 5 orders for meaningful clusters)
    if request.use_clustering and len(orders) >= request.min_cluster_size:
        # Use smaller cluster size to create more, manageable clusters
        # OR-Tools performs best with clusters of 20-30 locations max
        effective_min_cluster_size = min(request.min_cluster_size, max(3, len(orders) // 30))
        logger.info(f"🔬 Running HDBSCAN clustering (min_cluster_size={effective_min_cluster_size}, target ~20-30 per cluster)...")

        try:
            clustering_result = ClusteringService.cluster_orders(
                order_coords,
                min_cluster_size=effective_min_cluster_size,
                adaptive_clustering=True,
                merge_small_clusters=True,  # Merge nearby small clusters
                max_cluster_size_for_merge=5,  # Clusters with <5 orders can be merged
                max_merge_distance_km=1.0  # Merge if within 1km
            )
            cluster_labels = clustering_result["labels"]  # Labels with outliers assigned to nearest clusters
            original_cluster_labels = clustering_result.get("original_labels", cluster_labels)  # Original labels with -1 for outliers
            cluster_metadata = {
                "n_clusters": int(clustering_result["n_clusters"]),
                "outlier_count": int(clustering_result["outlier_count"]),
                "centroids": {int(k): list(v) for k, v in clustering_result["centroids"].items()},
                "original_labels": original_cluster_labels.tolist()  # Include original labels for visualization
            }

            # Check cluster sizes
            unique_labels, counts = np.unique(cluster_labels, return_counts=True)
            max_cluster_size = counts.max()
            avg_cluster_size = counts.mean()

            logger.info(f"✅ Clustering complete: {cluster_metadata['n_clusters']} clusters, {cluster_metadata['outlier_count']} outliers")
            logger.info(f"   📊 Cluster sizes: max={max_cluster_size}, avg={avg_cluster_size:.1f}")
            logger.info(f"   🎯 Target: Keep clusters under 30 locations for OR-Tools efficiency")

            # For large clusters, assign multiple drivers based on delivery capacity
            # Instead of splitting geographically, assign multiple drivers per cluster
            driver_capacity = 15  # orders per driver per day (reduced to use more drivers)

            # Count how many drivers needed per cluster
            cluster_driver_counts = {}
            total_drivers_needed = 0

            for label in unique_labels:
                cluster_size = counts[list(unique_labels).index(label)]
                drivers_needed = max(1, int(np.ceil(cluster_size / driver_capacity)))
                cluster_driver_counts[label] = drivers_needed
                total_drivers_needed += drivers_needed

            logger.info(f"   🚗 Driver assignment: {total_drivers_needed} drivers needed total")
            for label in unique_labels:
                cluster_size = counts[list(unique_labels).index(label)]
                drivers = cluster_driver_counts[label]
                logger.info(f"      Cluster {label}: {cluster_size} orders → {drivers} driver{'s' if drivers > 1 else ''}")

            cluster_metadata["cluster_driver_counts"] = {int(k): int(v) for k, v in cluster_driver_counts.items()}
            cluster_metadata["total_drivers_needed"] = int(total_drivers_needed)

            # Outliers are already assigned to nearest cluster by ClusteringService
            # Update cluster assignments in database
            crud.order.update_cluster_assignments(
                db=db,
                order_ids=order_ids_list,
                cluster_labels=cluster_labels.tolist()
            )

            logger.info(f"   🚗 Each cluster will get 1 dedicated driver")
        except Exception as e:
            logger.error(f"❌ Clustering error: {e}")
            cluster_labels = None
    else:
        logger.info(f"⏭️  Skipping clustering (use_clustering={request.use_clustering}, orders={len(orders)}, min needed=30)")
    
    # 5. Get distance matrix from Mapbox (with validation and filtering)
    print(f"DEBUG: STARTING DISTANCE MATRIX SECTION - orders={len(orders)}")
    logger.info(f"🗺️  Fetching distance matrix from Mapbox ({len(orders) + 1} locations)...")
    print(f"DEBUG: About to initialize MapboxService...")
    
    mapbox_service = MapboxService()
    print(f"DEBUG: MapboxService created successfully - type: {type(mapbox_service)}")
    logger.info(f"   MapboxService initialized successfully")
    
    # Try to get distance matrix, if it fails, identify and remove problematic orders
    max_retries = 2
    valid_orders = orders.copy()
    valid_order_coords = order_coords.copy()
    excluded_orders = []
    
    for attempt in range(max_retries):
        try:
            # For small order sets, use regular matrix
            if len(valid_orders) <= 24:
                logger.info(f"   Using standard matrix API (≤24 locations)")
                all_coords = [depot_coords] + valid_order_coords
                distance_matrix = mapbox_service.get_distance_matrix(all_coords, profile="driving")
            else:
                logger.info(f"   Using chunked matrix API (>24 locations)")
                logger.info(f"   Calling get_distance_matrix_chunked with {len(valid_order_coords)} orders...")
                # Use chunked method for larger sets
                distance_matrix = mapbox_service.get_distance_matrix_chunked(
                    depot_coords,
                    valid_order_coords,
                    profile="driving"
                )
                logger.info(f"   get_distance_matrix_chunked returned: {distance_matrix is not None}")
            
            if distance_matrix is None:
                raise ValueError("Failed to get distance matrix from Mapbox")
            
            # Check for NaN values before optimization
            nan_count = np.isnan(distance_matrix).sum() if distance_matrix is not None else "N/A"
            logger.info(f"✅ Distance matrix retrieved: {distance_matrix.shape}, NaN values: {nan_count}")
            
            # Success! Update the orders list
            orders = valid_orders
            order_coords = valid_order_coords
            break
            
        except Exception as e:
            if attempt < max_retries - 1 and len(valid_orders) > 1:
                # Try to identify problematic order by testing depot connectivity
                logger.warning(f"⚠️  Mapbox routing failed (attempt {attempt + 1}/{max_retries}): {e}")
                logger.info(f"🔍 Testing individual order connectivity to identify issues...")
                
                new_valid_orders = []
                new_valid_coords = []
                
                for i, (order, coord) in enumerate(zip(valid_orders, valid_order_coords)):
                    # Test if this order can be routed to/from depot
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
                            logger.warning(f"   ❌ Excluding order {order.order_number}: No valid route from depot")
                    except Exception as test_error:
                        excluded_orders.append(order)
                        logger.warning(f"   ❌ Excluding order {order.order_number}: {test_error}")
                
                if len(new_valid_orders) < len(valid_orders):
                    logger.info(f"   ✅ Identified {len(excluded_orders)} problematic orders, retrying with {len(new_valid_orders)} valid orders")
                    valid_orders = new_valid_orders
                    valid_order_coords = new_valid_coords
                    
                    # Check if we have any valid orders left
                    if len(valid_orders) == 0:
                        logger.error(f"❌ All orders excluded due to routing issues")
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
                            metadata={"error": "All selected orders are unroutable from this depot", "excluded_orders": len(excluded_orders)}
                        )
                else:
                    logger.error(f"❌ Could not identify problematic orders")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Error getting distance matrix: {str(e)}"
                    )
            else:
                logger.error(f"❌ Distance matrix error after {attempt + 1} attempts: {e}")
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
                        metadata={"error": "No orders could be routed", "excluded_orders": len(excluded_orders)}
                    )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Error getting distance matrix: {str(e)}"
                )
    
    if excluded_orders:
        logger.warning(f"⚠️  Excluded {len(excluded_orders)} orders due to routing issues:")
        for order in excluded_orders[:5]:
            logger.warning(f"   - {order.order_number}: {order.customer_name} at ({order.latitude}, {order.longitude})")
        if len(excluded_orders) > 5:
            logger.warning(f"   ... and {len(excluded_orders) - 5} more")
        
        # Update order_ids_list to match filtered orders
        order_ids_list = [order.id for order in orders]
        logger.info(f"   ✅ Continuing with {len(orders)} valid orders")
        
        # Re-run clustering if we had it and still have enough orders
        if cluster_labels is not None and len(orders) >= 5:
            logger.info(f"   🔄 Re-running clustering with {len(orders)} valid orders...")
            effective_min_cluster_size = min(request.min_cluster_size, max(3, len(orders) // 30))
            try:
                clustering_result = ClusteringService.cluster_orders(
                    order_coords,
                    min_cluster_size=effective_min_cluster_size
                )
                cluster_labels = clustering_result["labels"]
                unique_labels = clustering_result["unique_labels"]
                cluster_metadata = clustering_result["metadata"]
                
                # Recalculate cluster stats
                counts = [np.sum(cluster_labels == label) for label in unique_labels]
                max_cluster_size = max(counts) if counts else 0
                avg_cluster_size = np.mean(counts) if counts else 0
                
                logger.info(f"   ✅ Re-clustering complete: {cluster_metadata['n_clusters']} clusters")
                logger.info(f"      📊 Cluster sizes: max={max_cluster_size}, avg={avg_cluster_size:.1f}")
            except Exception as e:
                logger.warning(f"   ⚠️  Re-clustering failed, continuing without clustering: {e}")
                cluster_labels = None
                cluster_metadata = {}
    
    # 6. Determine number of vehicles based on clustering results
    # IMPORTANT: Always cap at depot's available drivers!
    if cluster_labels is not None and cluster_metadata.get("total_drivers_needed"):
        # Use total drivers needed (accounts for multiple drivers per large cluster)
        calculated_vehicles = cluster_metadata["total_drivers_needed"]
        num_vehicles = min(calculated_vehicles, depot.available_drivers)
        if calculated_vehicles > depot.available_drivers:
            logger.warning(f"⚠️  Clustering suggests {calculated_vehicles} drivers but depot only has {depot.available_drivers} available")
            logger.info(f"   🚗 Capping at {num_vehicles} vehicles (depot limit)")
        else:
            logger.info(f"🚗 Using {num_vehicles} vehicles (based on driver capacity per cluster)")
        logger.info(f"   Strategy: Multiple drivers per cluster based on 30 orders/driver capacity")
    elif cluster_labels is not None and cluster_metadata.get("n_clusters", 0) > 0:
        # Fallback: use number of clusters (1 driver per cluster), but cap at depot limit
        calculated_vehicles = cluster_metadata["n_clusters"]
        num_vehicles = min(calculated_vehicles, depot.available_drivers)
        if calculated_vehicles > depot.available_drivers:
            logger.warning(f"⚠️  Clustering created {calculated_vehicles} clusters but depot only has {depot.available_drivers} drivers")
            logger.info(f"   🚗 Capping at {num_vehicles} vehicles (depot limit)")
        else:
            logger.info(f"🚗 Using {num_vehicles} vehicles (based on {num_vehicles} natural clusters)")
        logger.info(f"   Strategy: 1 driver per cluster, max 50 orders/driver")
    else:
        # Fallback: use requested or depot default
        num_vehicles = request.num_vehicles if request.num_vehicles else min(depot.available_drivers, max(1, len(orders) // 50))
        logger.info(f"🚗 Using {num_vehicles} vehicles (no clustering, {len(orders)} orders / 50 per driver)")
    
    if num_vehicles <= 0:
        logger.error(f"❌ Invalid number of vehicles: {num_vehicles}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Number of vehicles must be greater than 0"
        )
    
    # 7. Run OR-Tools Integrated VRP with cluster penalties
    logger.info(f"🧮 Running OR-Tools Integrated VRP solver...")
    logger.info(f"   Using {num_vehicles} vehicles with cluster penalty soft constraints")
    if cluster_labels is not None:
        logger.info(f"   Cluster penalties will discourage cross-cluster routing")
    
    try:
        optimization_result = RouteOptimizationService.optimize_routes(
            depot_coords,
            order_coords,
            distance_matrix,
            num_vehicles,
            order_ids=[str(oid) for oid in order_ids_list],
            cluster_labels=cluster_labels
        )
        
        logger.info(f"✅ Optimization complete: {len(optimization_result['routes'])} routes, status: {optimization_result['solver_status']}")
        logger.info(f"   Total distance: {optimization_result['total_distance']/1000:.2f} km")
        logger.info(f"   Total time: {optimization_result['total_time']/60:.1f} minutes")
        
        # Log cluster purity for each route
        if cluster_labels is not None and optimization_result['routes']:
            logger.info(f"   📊 Cluster Purity Analysis:")
            for route in optimization_result['routes']:
                if route['stops']:
                    stop_clusters = [cluster_labels[stop['order_index']] for stop in route['stops']]
                    unique_clusters = set(stop_clusters)
                    dominant_cluster = max(set(stop_clusters), key=stop_clusters.count)
                    purity = (stop_clusters.count(dominant_cluster) / len(stop_clusters)) * 100
                    logger.info(f"      Route {route['vehicle_id']}: {len(route['stops'])} stops, Cluster {dominant_cluster} ({purity:.0f}% purity), Clusters: {unique_clusters}")
        
    except Exception as e:
        logger.error(f"❌ Optimization error: {e}", exc_info=True)
        print(f"\n[DEBUG ERROR] Exception occurred: {type(e).__name__}")
        print(f"[DEBUG ERROR] Message: {str(e)}")
        import traceback
        print(f"[DEBUG ERROR] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error optimizing routes: {str(e)}"
        )
    
    # 8. Format response
    print(f"DEBUG: Building {len(optimization_result['routes'])} routes")
    optimized_routes = []

    for i, route in enumerate(optimization_result["routes"]):
        print(f"DEBUG: Processing route {i}, vehicle_id type: {type(route['vehicle_id'])}, num_orders: {route.get('num_orders', len(route['stops']))}")
        # Build route stops
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
        
        # Determine predominant cluster if clustering was used
        cluster_id = None
        if cluster_labels is not None:
            stop_clusters = [int(cluster_labels[stop["order_index"]]) for stop in route["stops"]]
            if stop_clusters:
                cluster_id = int(np.bincount(stop_clusters).argmax())
        
        print(f"DEBUG: Creating OptimizedRoute for route {i}")
        optimized_route = schemas.OptimizedRoute(
            vehicle_id=int(route["vehicle_id"]),  # Convert numpy to Python int
            stops=stops,
            num_stops=len(stops),  # Count actual stops
            total_distance_km=float(route["total_distance"]) / 1000.0,  # Convert to km
            estimated_duration_minutes=float(route["total_time"]) / 60.0,  # Convert to minutes
            cluster_id=int(cluster_id) if cluster_id is not None else None  # Convert numpy to Python int
        )
        optimized_routes.append(optimized_route)
        print(f"DEBUG: Successfully created route {i}")
    
    # Handle unassigned orders - convert numpy types to Python types
    unassigned_order_ids = []
    for idx in optimization_result.get("unassigned", []):
        # Convert numpy int64 to Python int
        idx_int = int(idx)
        if 0 <= idx_int < len(order_ids_list):
            unassigned_order_ids.append(order_ids_list[idx_int])
    
    # Build result - ensure all numpy types are converted to Python types
    print(f"DEBUG: About to create RouteOptimizationResult")
    print(f"DEBUG: optimization_result keys: {list(optimization_result.keys())}")
    for k, v in optimization_result.items():
        if hasattr(v, 'dtype'):  # Check if it's a numpy type
            print(f"DEBUG: numpy type found in optimization_result[{k}]: {type(v)}")
        elif isinstance(v, list) and v and hasattr(v[0], 'dtype'):
            print(f"DEBUG: numpy list found in optimization_result[{k}]: {type(v[0])}")

    # Consider it successful if routes were created, even if solver status is PARTIAL_SUCCESS
    # PARTIAL_SUCCESS means some orders couldn't be assigned, but routes were still created
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
        ) if cluster_labels is not None else None,  # num_clusters = total groups (clusters + outliers)
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
                str(order.id): int(original_cluster_labels[i]) if original_cluster_labels is not None and cluster_labels is not None else None
                for i, order in enumerate(orders)
            } if cluster_labels is not None and original_cluster_labels is not None else None,
            "total_groups": (
                int(cluster_metadata.get("n_clusters", 0)) + 
                int(cluster_metadata.get("outlier_count", 0))
            ) if cluster_labels is not None else None
        }
    )
    
    logger.info(f"🎉 Route optimization complete!")
    logger.info(f"   📊 Summary: {result.total_routes} routes, {result.total_orders} orders assigned, {len(unassigned_order_ids)} unassigned")
    logger.info(f"   🚗 Distance: {result.total_distance_km:.2f} km, Duration: {result.total_duration_minutes:.1f} min")
    
    # DEBUG: Print final result
    print("\n" + "="*80)
    print(f"✅ DEBUG: Route Optimization Result for Depot: {depot.name} ({depot.id})")
    print("="*80)
    print(f"Success: {result.success}")
    print(f"Total Routes: {result.total_routes}")
    print(f"Total Orders: {result.total_orders}")
    print(f"Total Distance: {result.total_distance_km:.2f} km")
    print(f"Total Duration: {result.total_duration_minutes:.1f} minutes")
    print(f"Unassigned Orders: {len(unassigned_order_ids)}")
    print(f"Used Clustering: {result.used_clustering}")
    print(f"Num Clusters: {result.num_clusters}")
    print(f"Solver Status: {result.solver_status}")
    if result.routes:
        print(f"\n📋 Routes:")
        for i, route in enumerate(result.routes):
            print(f"  Route {i+1} (Vehicle {route.vehicle_id}): {route.num_stops} stops, {route.total_distance_km:.2f} km, {route.estimated_duration_minutes:.1f} min")
            print(f"    First stop: {route.stops[0].customer_name if route.stops else 'N/A'}")
            print(f"    Last stop: {route.stops[-1].customer_name if route.stops else 'N/A'}")
    else:
        print(f"\n⚠️ NO ROUTES CREATED!")
    print("="*80 + "\n")
    
    return result


@router.get("/test-connection", response_model=dict)
def test_services_connection(
    db: Session = Depends(get_db)
) -> dict:
    """Test connection to external services"""
    status_dict = {
        "mapbox": False,
        "hdbscan": False,
        "ortools": False,
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
    
    # Test HDBSCAN
    try:
        from app.services.clustering_service import HDBSCAN_AVAILABLE
        status_dict["hdbscan"] = HDBSCAN_AVAILABLE
    except Exception as e:
        status_dict["hdbscan"] = f"Error: {str(e)}"
    
    # Test OR-Tools
    try:
        from app.services.route_optimization_service import ORTOOLS_AVAILABLE
        status_dict["ortools"] = ORTOOLS_AVAILABLE
    except Exception as e:
        status_dict["ortools"] = f"Error: {str(e)}"
    
    # Test Database
    try:
        depot_count = len(crud.depot.get_multi(db=db, skip=0, limit=1))
        status_dict["database"] = True
    except Exception as e:
        status_dict["database"] = f"Error: {str(e)}"
    
    return {
        "status": "ok" if all(v is True for v in status_dict.values() if isinstance(v, bool)) else "degraded",
        "services": status_dict
    }


