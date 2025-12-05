"""Mapbox API service for geocoding and distance matrix"""
from typing import Optional, Tuple, List
import logging
import requests
import numpy as np
from app.core.config import settings

logger = logging.getLogger(__name__)


class MapboxService:
    """Service for interacting with Mapbox APIs"""
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or settings.MAPBOX_ACCESS_TOKEN
        if not self.access_token:
            raise ValueError("Mapbox access token is required")
        
        self.geocoding_base_url = "https://api.mapbox.com/geocoding/v5/mapbox.places"
        self.matrix_base_url = "https://api.mapbox.com/directions-matrix/v1/mapbox"
    
    def geocode_address(
        self, 
        address: str, 
        proximity: Optional[Tuple[float, float]] = None
    ) -> Optional[Tuple[float, float]]:
        """
        Forward geocode an address to lat/lng coordinates using Mapbox Geocoding API.
        
        Args:
            address: The address string to geocode
            proximity: Optional (latitude, longitude) tuple to bias results
        
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        try:
            encoded_address = requests.utils.quote(address)
            url = f"{self.geocoding_base_url}/{encoded_address}.json"
            
            params = {
                "access_token": self.access_token,
                "limit": 1,
                "types": "address,poi"
            }
            
            if proximity:
                latitude, longitude = proximity
                params["proximity"] = f"{longitude},{latitude}"
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get("features") and len(data["features"]) > 0:
                coordinates = data["features"][0]["geometry"]["coordinates"]
                longitude, latitude = coordinates[0], coordinates[1]
                return (latitude, longitude)
            
            return None
            
        except Exception as e:
            logger.error(f"Geocoding error for address '{address}': {e}")
            return None
    
    def get_distance_matrix(
        self,
        coordinates: List[Tuple[float, float]],
        profile: str = "driving"
    ) -> Optional[np.ndarray]:
        """
        Get travel time matrix between coordinates using Mapbox Matrix API.

        Args:
            coordinates: List of (latitude, longitude) tuples
            profile: Routing profile - "driving", "driving-traffic", "walking", or "cycling"

        Returns:
            Numpy array of travel times in seconds (matrix[i][j] = time from i to j)
            Returns None if API call fails

        Note:
            Mapbox Matrix API has a limit of 25 coordinates per request.
        """
        try:
            if len(coordinates) > 25:
                raise ValueError(f"Mapbox Matrix API supports maximum 25 coordinates, got {len(coordinates)}")

            if len(coordinates) < 2:
                raise ValueError("Need at least 2 coordinates for distance matrix")

            # Validate coordinates
            for i, (latitude, longitude) in enumerate(coordinates):
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    logger.warning(f"Invalid coordinate at index {i}: (lat={latitude}, lng={longitude})")
                    return None

            # Convert to Mapbox format: "lng,lat;lng,lat;..."
            coords_str = ";".join([f"{longitude},{latitude}" for latitude, longitude in coordinates])

            url = f"{self.matrix_base_url}/{profile}/{coords_str}"

            params = {
                "access_token": self.access_token,
                "annotations": "duration,distance",
                "sources": "all",
                "destinations": "all",
                "approaches": ";".join(["unrestricted"] * len(coordinates)),
                "fallback_speed": 40
            }

            response = requests.get(url, params=params, timeout=60)
            response.raise_for_status()

            data = response.json()

            if data.get("code") != "Ok":
                logger.error(f"Mapbox Matrix API error: {data.get('message', 'Unknown error')}")
                return None

            durations = data.get("durations", [])

            if not durations or len(durations) != len(coordinates):
                logger.error(f"Invalid durations response: expected {len(coordinates)}x{len(coordinates)}")
                return None

            # Check if all durations are zero
            flat_durations = [d for row in durations for d in row if d is not None]
            if all(d == 0 for d in flat_durations):
                logger.warning("All durations are 0 - routing may have failed")

            matrix = np.array(durations, dtype=float)

            # Check for NaN/inf values
            if np.isnan(matrix).any() or np.isinf(matrix).any():
                logger.error("Mapbox API returned invalid values (NaN or inf)")
                return None

            if matrix.shape != (len(coordinates), len(coordinates)):
                logger.error(f"Invalid matrix shape: {matrix.shape}")
                return None

            return matrix

        except requests.exceptions.Timeout:
            logger.error("Mapbox API request timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Mapbox API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Distance matrix error: {e}")
            return None
    
    def get_distance_matrix_chunked(
        self,
        depot_coords: Tuple[float, float],
        order_coords: List[Tuple[float, float]],
        profile: str = "driving"
    ) -> Optional[np.ndarray]:
        """
        Get distance matrix for depot and orders, handling large coordinate sets by chunking.
        
        Args:
            depot_coords: (latitude, longitude) of the depot
            order_coords: List of (latitude, longitude) tuples for orders
            profile: Routing profile (default: "driving")
            
        Returns:
            Distance matrix where [0] is depot and [1:] are orders
            Returns None if any API call fails
        """
        n_orders = len(order_coords)
        n_total = n_orders + 1
        all_coords = [depot_coords] + order_coords
        
        # If total coordinates <= 25, use simple API call
        if n_total <= 25:
            return self.get_distance_matrix(all_coords, profile)
        
        # For larger sets, use chunked approach
        logger.info(f"Using chunked matrix approach for {n_total} coordinates")
        chunk_size = 24
        
        full_matrix = np.zeros((n_total, n_total))
        num_chunks = (n_orders + chunk_size - 1) // chunk_size
        
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, n_orders)
            
            chunk_order_coords = order_coords[start_idx:end_idx]
            chunk_coords = [depot_coords] + chunk_order_coords
            
            chunk_matrix = self.get_distance_matrix(chunk_coords, profile)
            
            if chunk_matrix is None:
                logger.error(f"Failed to get matrix for chunk {chunk_idx + 1}")
                return None
            
            # Place chunk results into full matrix
            full_matrix[0, start_idx+1:end_idx+1] = chunk_matrix[0, 1:]
            full_matrix[start_idx+1:end_idx+1, 0] = chunk_matrix[1:, 0]
            
            for i, chunk_i in enumerate(range(start_idx+1, end_idx+1)):
                for j, chunk_j in enumerate(range(start_idx+1, end_idx+1)):
                    full_matrix[chunk_i, chunk_j] = chunk_matrix[i+1, j+1]
        
        # Handle cross-chunk distances via depot
        for chunk1_idx in range(num_chunks):
            start1 = chunk1_idx * chunk_size + 1
            end1 = min(start1 + chunk_size, n_total)
            
            for chunk2_idx in range(chunk1_idx + 1, num_chunks):
                start2 = chunk2_idx * chunk_size + 1
                end2 = min(start2 + chunk_size, n_total)
                
                for i in range(start1, end1):
                    for j in range(start2, end2):
                        full_matrix[i, j] = full_matrix[i, 0] + full_matrix[0, j]
                        full_matrix[j, i] = full_matrix[j, 0] + full_matrix[0, i]
        
        logger.info(f"Complete matrix assembled: {full_matrix.shape}")
        return full_matrix
