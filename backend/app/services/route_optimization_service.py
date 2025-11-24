"""
Route Optimization Service using OR-Tools VRP Solver

Implements Integrated VRP with cluster penalty soft constraints.
This is the ONLY routing strategy - vehicles can cross cluster boundaries
when beneficial, but penalties discourage unnecessary cross-cluster routing.
"""
from typing import List, Tuple, Dict, Any, Optional
import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp


class RouteOptimizationService:
    """Service for route optimization using OR-Tools VRP solver"""
    
    # Penalty for crossing cluster boundaries (in seconds)
    CLUSTER_PENALTY = 1000  # ~16.7 min or ~11 km penalty for crossing cluster boundaries
    
    # Service time per stop (in seconds) - includes parking, walking, delivery handoff
    SERVICE_TIME_PER_STOP = 300  # 5 minutes per delivery stop
    
    @staticmethod
    def optimize_routes(
        depot_coords: Tuple[float, float],
        order_coords: List[Tuple[float, float]],
        distance_matrix: np.ndarray,
        num_vehicles: int,
        order_ids: List[str],
        cluster_labels: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Optimize routes using Integrated VRP with cluster penalty soft constraints.
        
        This is the ONLY routing method. It solves a single Vehicle Routing Problem
        where vehicles can cross cluster boundaries when beneficial, but soft
        penalties (CLUSTER_PENALTY) discourage cross-cluster assignments for
        better geographic route coherence.
        
        Args:
            depot_coords: (latitude, longitude) of the depot - standard format
            order_coords: List of (latitude, longitude) for each order - standard format
            distance_matrix: Distance matrix (seconds) - includes depot at index 0
            num_vehicles: Number of vehicles/drivers available
            order_ids: List of order IDs
            cluster_labels: Optional cluster assignment for each order (for penalties)
            
        Returns:
            Dictionary with:
                - routes: List of route dictionaries
                - total_distance: Total distance in meters
                - total_time: Total time in seconds (assuming avg speed)
                - solver_status: Status string
                - num_vehicles_used: Number of vehicles actually used
                - unassigned: List of unassigned order indices
        """
        num_locations = len(distance_matrix)
        num_orders = num_locations - 1  # Exclude depot
        
        if num_orders == 0:
            return {
                "routes": [],
                "total_distance": 0,
                "total_time": 0,
                "solver_status": "SUCCESS",
                "num_vehicles_used": 0,
                "unassigned": []
            }
        
        # Create the routing index manager
        manager = pywrapcp.RoutingIndexManager(
            num_locations,
            num_vehicles,
            0  # Depot index
        )
        
        # Create routing model
        routing = pywrapcp.RoutingModel(manager)
        
        # Create distance callback with optional cluster penalties
        def distance_callback(from_index, to_index):
            """Returns the distance between two nodes with cluster penalties."""
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            
            base_distance = int(distance_matrix[from_node][to_node])
            
            # Add cluster penalty if crossing cluster boundaries
            if cluster_labels is not None and from_node > 0 and to_node > 0:
                # Only penalize if both are orders (not depot) and in different clusters
                from_cluster = cluster_labels[from_node - 1]
                to_cluster = cluster_labels[to_node - 1]
                
                # Don't penalize noise points (cluster -1) as much
                if from_cluster != to_cluster and from_cluster >= 0 and to_cluster >= 0:
                    base_distance += RouteOptimizationService.CLUSTER_PENALTY
            
            return base_distance
        
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        
        # Define cost of each arc
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Add distance dimension to track total distance
        # Improved: Use more realistic maximum distance based on problem size
        # For urban delivery: ~100-150 km per vehicle per day is reasonable
        max_distance_per_vehicle = 150000  # 150 km in meters (more realistic for full day)
        
        dimension_name = 'Distance'
        routing.AddDimension(
            transit_callback_index,
            0,  # no slack
            max_distance_per_vehicle,  # vehicle maximum travel distance
            True,  # start cumul to zero
            dimension_name
        )
        distance_dimension = routing.GetDimensionOrDie(dimension_name)
        
        # Global span cost coefficient: encourages balanced route lengths
        # Higher value = more emphasis on minimizing longest route (better balance)
        # Lower value = more emphasis on total distance (may create unbalanced routes)
        # 100 is a good balance for most problems
        distance_dimension.SetGlobalSpanCostCoefficient(100)
        
        # Setting first solution heuristic with improved parameters
        # Based on OR-Tools best practices and research findings
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        
        # AUTOMATIC strategy tries multiple heuristics (PATH_CHEAPEST_ARC, SAVINGS, etc.)
        # and automatically selects the best initial solution
        # This is better than hardcoding PATH_CHEAPEST_ARC
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC
        )
        
        # Use Guided Local Search - proven to be effective for VRP problems
        # Alternative: SIMULATED_ANNEALING for better exploration, but slower
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        
        # Time limit: balance between quality and speed
        search_parameters.time_limit.seconds = 30
        search_parameters.log_search = False
        
        # Solution limit: stop after finding good solutions (prevents excessive search)
        # This helps when multiple good solutions exist
        search_parameters.solution_limit = 100
        
        # Guided Local Search parameters for better exploration/exploitation balance
        # Lower lambda = more exploitation (refine current solution)
        # Higher lambda = more exploration (try different solutions)
        search_parameters.guided_local_search_lambda_coefficient = 0.1
        
        # Solve the problem
        solution = routing.SolveWithParameters(search_parameters)
        
        # Extract solution
        if solution:
            return RouteOptimizationService._extract_solution(
                manager, routing, solution, order_ids, distance_matrix, num_vehicles
            )
        else:
            # No solution found
            return {
                "routes": [],
                "total_distance": 0,
                "total_time": 0,
                "solver_status": "FAILED",
                "num_vehicles_used": 0,
                "unassigned": list(range(num_orders))
            }
    
    @staticmethod
    def _extract_solution(
        manager,
        routing,
        solution,
        order_ids: List[str],
        distance_matrix: np.ndarray,
        num_vehicles: int
    ) -> Dict[str, Any]:
        """Extract routes from OR-Tools solution."""
        routes = []
        total_distance = 0
        total_time = 0
        unassigned = []
        num_vehicles_used = 0
        
        # Average speed for time estimation (40 km/h in urban areas)
        avg_speed_kmh = 40
        avg_speed_ms = avg_speed_kmh * 1000 / 3600  # meters per second
        
        # Extract routes for each vehicle
        for vehicle_id in range(num_vehicles):
            index = routing.Start(vehicle_id)
            route_distance = 0
            route_stops = []
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                
                # Only add non-depot stops
                if node_index > 0:
                    order_index = node_index - 1
                    route_stops.append({
                        "order_id": order_ids[order_index],
                        "order_index": order_index,
                        "sequence": len(route_stops)
                    })
                
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                route_distance += routing.GetArcCostForVehicle(
                    previous_index, index, vehicle_id
                )
            
            # Only add route if it has stops
            if route_stops:
                driving_time = route_distance / avg_speed_ms  # seconds
                service_time = len(route_stops) * RouteOptimizationService.SERVICE_TIME_PER_STOP
                route_time = driving_time + service_time  # Total time includes driving + service
                
                routes.append({
                    "vehicle_id": vehicle_id,
                    "stops": route_stops,
                    "total_distance": route_distance,
                    "total_time": route_time,
                    "num_orders": len(route_stops)
                })
                
                total_distance += route_distance
                total_time += route_time
                num_vehicles_used += 1
        
        # Check for unassigned orders
        for order_idx in range(len(order_ids)):
            node_idx = order_idx + 1  # +1 because depot is at 0
            if solution.Value(routing.NextVar(node_idx)) == node_idx:
                unassigned.append(order_idx)
        
        # Determine solver status
        # OR-Tools status codes: 0=NOT_SOLVED, 1=SUCCESS, 2=PARTIAL_SUCCESS, 3=FAIL, 4=FAIL_TIMEOUT, 5=INVALID
        status = routing.status()
        if status == 1:  # ROUTING_SUCCESS
            solver_status = "SUCCESS"
        elif status == 2:  # ROUTING_PARTIAL_SUCCESS_LOCAL_OPTIMUM_NOT_REACHED
            solver_status = "PARTIAL_SUCCESS"
        elif status in [3, 4]:  # ROUTING_FAIL or ROUTING_FAIL_TIMEOUT
            solver_status = "FAILED"
        elif status == 0:  # ROUTING_NOT_SOLVED
            solver_status = "NOT_SOLVED"
        else:
            solver_status = "UNKNOWN"
        
        return {
            "routes": routes,
            "total_distance": total_distance,
            "total_time": total_time,
            "solver_status": solver_status,
            "num_vehicles_used": num_vehicles_used,
            "unassigned": unassigned
        }
    
    @staticmethod
    def optimize_routes_per_cluster(
        depot_coords: Tuple[float, float],
        order_coords: List[Tuple[float, float]],
        distance_matrix: np.ndarray,
        cluster_labels: np.ndarray,
        order_ids: List[str],
        max_orders_per_driver: int = 50,
        allow_multi_driver_per_cluster: bool = False  # Only if absolutely necessary
    ) -> Dict[str, Any]:
        """
        Optimize routes with STRICT neighborhood adherence: one driver per cluster.
        
        This method ensures:
        1. Each cluster/neighborhood gets exactly ONE driver (unless allow_multi_driver_per_cluster=True)
        2. Drivers stay within their assigned neighborhood
        3. Only combines clusters if absolutely necessary (not enough drivers)
        
        Args:
            depot_coords: (latitude, longitude) of depot
            order_coords: List of (latitude, longitude) for orders
            distance_matrix: Full distance matrix (depot + all orders)
            cluster_labels: Cluster assignment for each order
            order_ids: List of order IDs
            max_orders_per_driver: Maximum orders a single driver can handle
            allow_multi_driver_per_cluster: If True, allows multiple drivers per cluster if needed
        
        Returns:
            Dictionary with routes, one per cluster (or multiple if allowed and needed)
        """
        unique_clusters = np.unique(cluster_labels)
        n_clusters = len(unique_clusters)
        
        all_routes = []
        total_distance = 0
        total_time = 0
        all_unassigned = []
        num_vehicles_used = 0
        
        # Optimize each cluster separately
        for cluster_id in unique_clusters:
            # Get orders in this cluster
            cluster_mask = cluster_labels == cluster_id
            cluster_order_indices = np.where(cluster_mask)[0]
            cluster_order_ids = [order_ids[i] for i in cluster_order_indices]
            cluster_order_coords = [order_coords[i] for i in cluster_order_indices]
            
            cluster_size = len(cluster_order_indices)
            
            # Determine number of drivers for this cluster
            if allow_multi_driver_per_cluster and cluster_size > max_orders_per_driver:
                # Multiple drivers needed for large cluster (LAST RESORT)
                num_drivers_for_cluster = int(np.ceil(cluster_size / max_orders_per_driver))
            else:
                # ONE driver per cluster (PREFERRED)
                num_drivers_for_cluster = 1
            
            # Build sub-distance matrix for this cluster
            # Include depot (index 0) + cluster orders
            cluster_matrix_size = 1 + cluster_size  # depot + orders
            cluster_distance_matrix = np.zeros((cluster_matrix_size, cluster_matrix_size))
            
            # Fill depot-to-cluster-orders distances
            for i, order_idx in enumerate(cluster_order_indices):
                # depot (0) to order (i+1 in cluster matrix)
                cluster_distance_matrix[0, i + 1] = distance_matrix[0, order_idx + 1]
                cluster_distance_matrix[i + 1, 0] = distance_matrix[order_idx + 1, 0]
            
            # Fill inter-order distances within cluster
            for i, order_idx_i in enumerate(cluster_order_indices):
                for j, order_idx_j in enumerate(cluster_order_indices):
                    if i != j:
                        cluster_distance_matrix[i + 1, j + 1] = distance_matrix[order_idx_i + 1, order_idx_j + 1]
            
            # Optimize this cluster
            cluster_result = RouteOptimizationService.optimize_routes(
                depot_coords=depot_coords,
                order_coords=cluster_order_coords,
                distance_matrix=cluster_distance_matrix,
                num_vehicles=num_drivers_for_cluster,
                order_ids=cluster_order_ids,
                cluster_labels=None  # No sub-clustering within cluster
            )
            
            # Adjust route vehicle IDs to be unique across all clusters
            for route in cluster_result.get("routes", []):
                # Vehicle ID = cluster_id * 1000 + original_vehicle_id
                # This ensures unique IDs across clusters
                route["vehicle_id"] = int(cluster_id) * 1000 + route["vehicle_id"]
                route["cluster_id"] = int(cluster_id)
                all_routes.append(route)
            
            total_distance += cluster_result.get("total_distance", 0)
            total_time += cluster_result.get("total_time", 0)
            num_vehicles_used += cluster_result.get("num_vehicles_used", 0)
            
            # Track unassigned orders (map back to original indices)
            for unassigned_idx in cluster_result.get("unassigned", []):
                original_order_idx = cluster_order_indices[unassigned_idx]
                all_unassigned.append(original_order_idx)
        
        # Determine overall solver status
        if len(all_unassigned) == 0:
            solver_status = "SUCCESS"
        elif len(all_unassigned) < len(order_ids) * 0.1:  # Less than 10% unassigned
            solver_status = "PARTIAL_SUCCESS"
        else:
            solver_status = "FAILED"
        
        return {
            "routes": all_routes,
            "total_distance": total_distance,
            "total_time": total_time,
            "solver_status": solver_status,
            "num_vehicles_used": num_vehicles_used,
            "unassigned": all_unassigned
        }




