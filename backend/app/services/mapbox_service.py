"""Mapbox API service for geocoding and distance matrix"""
from typing import Optional, Tuple, List
import requests
import numpy as np
from app.core.config import settings


class MapboxService:
    """Service for interacting with Mapbox APIs"""
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.MAPBOX_ACCESS_TOKEN
        if not self.access_token:
            raise ValueError("Mapbox access token is required")
        
        self.geocoding_base_url = "https://api.mapbox.com/geocoding/v5/mapbox.places"
        self.matrix_base_url = "https://api.mapbox.com/directions-matrix/v1/mapbox"
    
    def geocode_address(self, address: str, proximity: Optional[Tuple[float, float]] = None) -> Optional[Tuple[float, float]]:
        """
        Forward geocode an address to lat/lng coordinates using Mapbox Geocoding API.
        
        Args:
            address: The address string to geocode
            proximity: Optional (latitude, longitude) tuple to bias results near a location (e.g., Ottawa center)
        
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        try:
            # Encode address for URL
            encoded_address = requests.utils.quote(address)
            url = f"{self.geocoding_base_url}/{encoded_address}.json"
            
            params = {
                "access_token": self.access_token,
                "limit": 1,
                "types": "address,poi"  # Prioritize addresses and points of interest
            }
            
            # Add proximity bias if provided (helps for Ottawa addresses)
            # Mapbox expects (longitude, latitude) format
            if proximity:
                latitude, longitude = proximity
                params["proximity"] = f"{longitude},{latitude}"
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("features") and len(data["features"]) > 0:
                # Mapbox returns [lng, lat]
                coordinates = data["features"][0]["geometry"]["coordinates"]
                longitude, latitude = coordinates[0], coordinates[1]
                return (latitude, longitude)
            
            return None
            
        except Exception as e:
            print(f"Geocoding error for address '{address}': {e}")
            return None
    
    def get_distance_matrix(
        self,
        coordinates: List[Tuple[float, float]],
        profile: str = "driving"
    ) -> Optional[np.ndarray]:
        """
        Get travel time/distance matrix between coordinates using Mapbox Matrix API.

        Args:
            coordinates: List of (latitude, longitude) tuples - standard format throughout codebase
            profile: Routing profile - "driving", "driving-traffic", "walking", or "cycling"

        Returns:
            Numpy array of travel times in seconds (matrix[i][j] = time from i to j)
            Returns None if API call fails

        Note:
            Mapbox Matrix API has a limit of 25 coordinates per request.
            For larger matrices, this needs to be called multiple times.
            This function converts (lat, lng) to (lng, lat) only for the Mapbox API call.
        """
        try:
            if len(coordinates) > 25:
                raise ValueError(f"Mapbox Matrix API supports maximum 25 coordinates per request, got {len(coordinates)}")

            if len(coordinates) < 2:
                raise ValueError("Need at least 2 coordinates for distance matrix")

            # Validate coordinates (input is latitude, longitude)
            for i, (latitude, longitude) in enumerate(coordinates):
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    print(f"Invalid coordinate at index {i}: (lat={latitude}, lng={longitude})")
                    return None

            print(f"DEBUG: First 3 coordinates: {coordinates[:3]}")
            print(f"DEBUG: Total coordinates: {len(coordinates)}")

            # Convert coordinates to Mapbox format: "lng,lat;lng,lat;..."
            # Mapbox expects longitude,latitude format, so we swap here
            coords_str = ";".join([f"{longitude},{latitude}" for latitude, longitude in coordinates])
            print(f"DEBUG: coords_str length: {len(coords_str)}")
            print(f"DEBUG: coords_str preview: {coords_str[:100]}...")

            url = f"{self.matrix_base_url}/{profile}/{coords_str}"

            params = {
                "access_token": self.access_token,
                "annotations": "duration,distance",  # Get both duration and distance
                "sources": "all",  # All points as sources
                "destinations": "all",  # All points as destinations
                "approaches": ";".join(["unrestricted"] * len(coordinates)),  # Allow any approach
                "fallback_speed": 40  # Fallback speed in km/h for failed routes (urban speed)
                # Removed "exclude": "" as empty exclude can cause issues
            }

            print(f"Calling Mapbox API: {len(coordinates)} coordinates")
            print(f"URL length: {len(url)}")
            print(f"Approaches param length: {len(params['approaches'])}")
            full_url = requests.Request('GET', url, params=params).prepare().url
            print(f"Full URL length: {len(full_url)}")
            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()

            data = response.json()

            if data.get("code") != "Ok":
                print(f"Mapbox Matrix API error: {data.get('message', 'Unknown error')}")
                print(f"Full response: {data}")
                return None

            # Extract duration matrix (in seconds)
            durations = data.get("durations", [])

            if not durations or len(durations) != len(coordinates):
                print(f"Invalid durations response: expected {len(coordinates)}x{len(coordinates)}, got {len(durations) if durations else 0} rows")
                print(f"Response structure: {list(data.keys())}")
                if durations:
                    print(f"First row length: {len(durations[0]) if durations[0] else 0}")
                return None

            # Check if all durations are zero (invalid routing)
            flat_durations = [d for row in durations for d in row if d is not None]
            if all(d == 0 for d in flat_durations):
                print(f"WARNING: All durations are 0 - routing may have failed")
                print(f"Sample coordinates: {coordinates[:3]}")
                # Don't return None - let the caller decide what to do with zeros

            # Convert to numpy array and validate
            matrix = np.array(durations, dtype=float)

            # Check for NaN/inf values
            nan_count = np.isnan(matrix).sum()
            inf_count = np.isinf(matrix).sum()

            if nan_count > 0 or inf_count > 0:
                print(f"Mapbox API returned invalid values: NaN={nan_count}, inf={inf_count}")
                return None

            # Validate matrix shape
            expected_shape = (len(coordinates), len(coordinates))
            if matrix.shape != expected_shape:
                print(f"Invalid matrix shape: expected {expected_shape}, got {matrix.shape}")
                return None

            print(f"✅ Mapbox matrix successful: {matrix.shape}, range=[{matrix.min():.1f}, {matrix.max():.1f}]")
            return matrix

        except requests.exceptions.Timeout:
            print("Mapbox API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Mapbox API request error: {e}")
            return None
        except Exception as e:
            print(f"Distance matrix error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_distance_matrix_chunked(
        self,
        depot_coords: Tuple[float, float],
        order_coords: List[Tuple[float, float]],
        profile: str = "driving"
    ) -> Optional[np.ndarray]:
        """
        Get distance matrix for depot and orders, handling large coordinate sets by chunking.
        
        Mapbox Matrix API has a 25 coordinate limit. This method handles larger sets by:
        1. Making multiple API calls with chunks of coordinates
        2. Assembling the results into a complete distance matrix
        
        Args:
            depot_coords: (latitude, longitude) of the depot - standard format
            order_coords: List of (latitude, longitude) tuples for orders - standard format
            profile: Routing profile (default: "driving")
            
        Returns:
            Distance matrix where [0] is depot and [1:] are orders
            Returns None if any API call fails
        """
        n_orders = len(order_coords)
        n_total = n_orders + 1  # depot + orders
        all_coords = [depot_coords] + order_coords
        
        print(f"📊 [Mapbox] Building distance matrix for {n_orders} orders + depot")
        
        # If total coordinates <= 25, use simple API call
        if n_total <= 25:
            print(f"   Using single API call ({n_total} ≤ 25 coordinates)")
            return self.get_distance_matrix(all_coords, profile)
        
        # For larger sets, use chunked approach
        print(f"   Using chunked approach ({n_total} > 25 coordinates)")
        chunk_size = 24  # Leave room for depot in each chunk
        
        # Initialize full matrix
        full_matrix = np.zeros((n_total, n_total))
        
        # Calculate number of chunks needed
        num_chunks = (n_orders + chunk_size - 1) // chunk_size
        print(f"   Will process {num_chunks} chunks of up to {chunk_size} orders each")
        
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, n_orders)
            
            # Get orders for this chunk (add 1 to indices since depot is at index 0)
            chunk_order_coords = order_coords[start_idx:end_idx]
            chunk_coords = [depot_coords] + chunk_order_coords
            
            print(f"   Chunk {chunk_idx + 1}/{num_chunks}: orders {start_idx} to {end_idx-1} ({len(chunk_order_coords)} orders)")
            
            # Get distance matrix for this chunk
            chunk_matrix = self.get_distance_matrix(chunk_coords, profile)
            
            if chunk_matrix is None:
                print(f"   ❌ Failed to get matrix for chunk {chunk_idx + 1}")
                return None
            
            # Place chunk results into full matrix
            # Depot row/column (index 0)
            full_matrix[0, start_idx+1:end_idx+1] = chunk_matrix[0, 1:]  # depot to chunk orders
            full_matrix[start_idx+1:end_idx+1, 0] = chunk_matrix[1:, 0]  # chunk orders to depot
            
            # Inter-chunk order distances
            for i, chunk_i in enumerate(range(start_idx+1, end_idx+1)):
                for j, chunk_j in enumerate(range(start_idx+1, end_idx+1)):
                    full_matrix[chunk_i, chunk_j] = chunk_matrix[i+1, j+1]
        
        # Handle cross-chunk distances (between orders in different chunks)
        # For orders not in the same chunk, use depot as intermediate point
        for chunk1_idx in range(num_chunks):
            start1 = chunk1_idx * chunk_size + 1  # +1 for depot offset
            end1 = min(start1 + chunk_size, n_total)
            
            for chunk2_idx in range(chunk1_idx + 1, num_chunks):
                start2 = chunk2_idx * chunk_size + 1
                end2 = min(start2 + chunk_size, n_total)
                
                # For cross-chunk distances, use triangular inequality via depot
                # distance(order_i, order_j) ≈ distance(order_i, depot) + distance(depot, order_j)
                for i in range(start1, end1):
                    for j in range(start2, end2):
                        full_matrix[i, j] = full_matrix[i, 0] + full_matrix[0, j]
                        full_matrix[j, i] = full_matrix[j, 0] + full_matrix[0, i]
        
        print(f"   ✅ Complete matrix assembled: {full_matrix.shape}")
        print(f"   📏 Duration range: {full_matrix[full_matrix > 0].min():.0f}s - {full_matrix.max():.0f}s")
        
        return full_matrix










