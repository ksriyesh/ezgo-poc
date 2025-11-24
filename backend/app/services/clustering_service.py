"""HDBSCAN clustering service for grouping delivery orders"""
from typing import List, Tuple, Dict, Optional
import numpy as np
from scipy.spatial.distance import cdist
from math import radians, sin, cos, sqrt, atan2
try:
    import hdbscan
    HDBSCAN_AVAILABLE = True
except ImportError:
    HDBSCAN_AVAILABLE = False
    print("Warning: hdbscan not installed. Clustering will not be available.")


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth (in kilometers).
    Uses the Haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of point 1 (in degrees)
        lat2, lon2: Latitude and longitude of point 2 (in degrees)
    
    Returns:
        Distance in kilometers
    """
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    # Earth's radius in kilometers
    radius = 6371.0
    
    return radius * c


class ClusteringService:
    """Service for clustering delivery orders using HDBSCAN"""
    
    @staticmethod
    def cluster_orders(
        coordinates: List[Tuple[float, float]],
        min_cluster_size: int = 3,  # Reduced default - let natural clusters form
        min_samples: Optional[int] = None,
        cluster_selection_epsilon: float = 0.0,
        adaptive_clustering: bool = True,  # New: enable adaptive clustering
        merge_small_clusters: bool = True,  # Merge nearby small clusters
        max_cluster_size_for_merge: int = 5,  # Clusters smaller than this can be merged
        max_merge_distance_km: float = 1.0  # Maximum distance to merge clusters (km)
    ) -> Dict:
        """
        Cluster delivery order coordinates using HDBSCAN.
        Outliers (label=-1) are assigned to the nearest cluster centroid.
        
        Args:
            coordinates: List of (latitude, longitude) tuples - standard format
            min_cluster_size: Minimum size of a cluster
            min_samples: Minimum samples in a neighborhood (defaults to min_cluster_size)
            cluster_selection_epsilon: Distance threshold for cluster selection
        
        Returns:
            Dictionary containing:
                - labels: Array of cluster labels for each point (outliers assigned to nearest cluster)
                - original_labels: Original HDBSCAN labels (with -1 for outliers)
                - n_clusters: Number of clusters found
                - centroids: Dict mapping cluster_id -> (latitude, longitude) centroid
                - outlier_count: Number of outliers that were reassigned
        """
        if not HDBSCAN_AVAILABLE:
            raise RuntimeError("hdbscan package is not installed")
        
        if len(coordinates) < min_cluster_size:
            # Not enough points for clustering, assign all to cluster 0
            # coordinates are (lat, lng), centroids should be (lat, lng)
            return {
                "labels": np.zeros(len(coordinates), dtype=int),
                "original_labels": np.zeros(len(coordinates), dtype=int),
                "n_clusters": 1,
                "centroids": {0: (np.mean([c[0] for c in coordinates]), np.mean([c[1] for c in coordinates]))},
                "outlier_count": 0
            }
        
        # Convert to numpy array
        # coordinates are (latitude, longitude), HDBSCAN haversine expects (lat, lng) - no swap needed
        coords_array = np.array(coordinates)
        
        # Use coordinates directly for HDBSCAN haversine metric (already in lat, lng format)
        coords_for_clustering = coords_array  # No swap needed: [lat, lng] -> [lat, lng]
        
        # Adaptive clustering: Let natural clusters form
        if adaptive_clustering:
            # Use smaller min_cluster_size to allow natural neighborhoods
            # cluster_selection_epsilon helps merge nearby clusters naturally
            effective_min_cluster_size = max(2, min(min_cluster_size, len(coordinates) // 20))
            # Use epsilon to merge nearby clusters (in km, converted to radians)
            # 0.5 km = ~0.0045 radians at equator
            effective_epsilon = 0.0045 if cluster_selection_epsilon == 0.0 else cluster_selection_epsilon
        else:
            effective_min_cluster_size = min_cluster_size
            effective_epsilon = cluster_selection_epsilon
        
        # Run HDBSCAN
        if min_samples is None:
            min_samples = effective_min_cluster_size
        
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=effective_min_cluster_size,
            min_samples=min_samples,
            cluster_selection_epsilon=effective_epsilon,
            metric='haversine',  # Use haversine for lat/lng
            gen_min_span_tree=True
        )
        
        # Convert lat/lng to radians for haversine distance
        coords_radians = np.radians(coords_for_clustering)
        
        # Fit and predict
        cluster_labels = clusterer.fit_predict(coords_radians)
        original_labels = cluster_labels.copy()
        
        # Count outliers
        outlier_mask = cluster_labels == -1
        outlier_count = np.sum(outlier_mask)
        
        # Get unique cluster IDs (excluding outliers)
        unique_clusters = np.unique(cluster_labels[cluster_labels != -1])
        n_clusters = len(unique_clusters)
        
        if n_clusters == 0:
            # All points are outliers, assign to a single cluster
            return {
                "labels": np.zeros(len(coordinates), dtype=int),
                "original_labels": original_labels,
                "n_clusters": 1,
                "centroids": {0: (np.mean([c[0] for c in coordinates]), np.mean([c[1] for c in coordinates]))},
                "outlier_count": len(coordinates)
            }
        
        # Calculate centroids for each cluster
        # coords_array is (latitude, longitude), so centroids will be (latitude, longitude)
        centroids = {}
        for cluster_id in unique_clusters:
            cluster_mask = cluster_labels == cluster_id
            cluster_coords = coords_array[cluster_mask]  # (lat, lng) format
            centroid = (np.mean(cluster_coords[:, 0]), np.mean(cluster_coords[:, 1]))  # (lat, lng)
            centroids[int(cluster_id)] = centroid
        
        # Assign outliers to nearest cluster centroid
        if outlier_count > 0 and n_clusters > 0:
            outlier_indices = np.where(outlier_mask)[0]
            outlier_coords = coords_array[outlier_mask]
            
            # Get centroid coordinates as array
            centroid_coords = np.array([centroids[cid] for cid in unique_clusters])
            
            # Calculate distances from each outlier to each centroid
            # Use haversine-like distance (simplified for small areas)
            distances = cdist(outlier_coords, centroid_coords, metric='euclidean')
            
            # Assign each outlier to nearest centroid
            nearest_cluster_indices = np.argmin(distances, axis=1)
            nearest_clusters = unique_clusters[nearest_cluster_indices]
            
            # Update labels
            cluster_labels[outlier_indices] = nearest_clusters
        
        # Merge nearby small clusters if enabled
        if merge_small_clusters and n_clusters > 1:
            cluster_labels, centroids = ClusteringService.merge_nearby_small_clusters(
                coordinates=coordinates,
                labels=cluster_labels,
                centroids=centroids,
                max_cluster_size=max_cluster_size_for_merge,
                max_distance_km=max_merge_distance_km
            )
            
            # Recalculate cluster count after merging
            unique_clusters_after_merge = np.unique(cluster_labels[cluster_labels >= 0])
            n_clusters = len(unique_clusters_after_merge)
        
        return {
            "labels": cluster_labels,
            "original_labels": original_labels,
            "n_clusters": int(n_clusters),
            "centroids": centroids,
            "outlier_count": int(outlier_count)
        }
    
    @staticmethod
    def merge_nearby_small_clusters(
        coordinates: List[Tuple[float, float]],
        labels: np.ndarray,
        centroids: Dict[int, Tuple[float, float]],
        max_cluster_size: int = 5,
        max_distance_km: float = 1.0
    ) -> Tuple[np.ndarray, Dict[int, Tuple[float, float]]]:
        """
        Merge nearby small clusters that are below size threshold.
        
        If two clusters are:
        - Both smaller than max_cluster_size
        - Within max_distance_km of each other
        Then merge them into one cluster.
        
        This prevents having too many tiny clusters that should be served by one driver.
        
        Args:
            coordinates: List of (latitude, longitude) tuples - standard format
            labels: Current cluster labels from HDBSCAN
            centroids: Dict mapping cluster_id -> (latitude, longitude) centroid
            max_cluster_size: Maximum size for clusters to be considered for merging (default: 5)
            max_distance_km: Maximum distance between centroids to merge (default: 1.0 km)
        
        Returns:
            Tuple of (updated_labels, updated_centroids)
        """
        coords_array = np.array(coordinates)
        updated_labels = labels.copy()
        updated_centroids = centroids.copy()
        
        # Calculate cluster sizes
        unique_clusters = np.unique(labels[labels >= 0])  # Exclude outliers (-1)
        cluster_sizes = {}
        for cluster_id in unique_clusters:
            cluster_sizes[int(cluster_id)] = np.sum(labels == cluster_id)
        
        # Find clusters to merge
        clusters_to_merge = {}  # Maps target_cluster -> [source_clusters]
        merged_clusters = set()
        
        for cluster_id_1 in unique_clusters:
            if cluster_id_1 in merged_clusters:
                continue
            
            cluster_id_1_int = int(cluster_id_1)
            size_1 = cluster_sizes[cluster_id_1_int]
            
            # Only consider small clusters
            if size_1 >= max_cluster_size:
                continue
            
            # Find nearby small clusters
            centroid_1 = centroids[cluster_id_1_int]
            candidates = []
            
            for cluster_id_2 in unique_clusters:
                if cluster_id_2 == cluster_id_1 or cluster_id_2 in merged_clusters:
                    continue
                
                cluster_id_2_int = int(cluster_id_2)
                size_2 = cluster_sizes[cluster_id_2_int]
                
                # Both must be small
                if size_2 >= max_cluster_size:
                    continue
                
                # Check distance
                centroid_2 = centroids[cluster_id_2_int]
                distance = haversine_distance_km(
                    centroid_1[0], centroid_1[1],  # lat1, lon1
                    centroid_2[0], centroid_2[1]   # lat2, lon2
                )
                
                if distance <= max_distance_km:
                    # Merge cluster_2 into cluster_1
                    candidates.append((cluster_id_2_int, distance, size_2))
            
            # Sort by distance (merge closest first)
            candidates.sort(key=lambda x: x[1])
            
            # Merge all nearby small clusters into cluster_1
            for cluster_id_2_int, distance, size_2 in candidates:
                if cluster_id_2_int not in merged_clusters:
                    # Update labels: change all cluster_id_2 to cluster_id_1
                    updated_labels[updated_labels == cluster_id_2_int] = cluster_id_1_int
                    merged_clusters.add(cluster_id_2_int)
                    
                    # Remove merged cluster from centroids
                    if cluster_id_2_int in updated_centroids:
                        del updated_centroids[cluster_id_2_int]
        
        # Recalculate centroids for merged clusters
        final_unique_clusters = np.unique(updated_labels[updated_labels >= 0])
        final_centroids = {}
        
        for cluster_id in final_unique_clusters:
            cluster_id_int = int(cluster_id)
            cluster_mask = updated_labels == cluster_id
            cluster_coords = coords_array[cluster_mask]
            centroid = (np.mean(cluster_coords[:, 0]), np.mean(cluster_coords[:, 1]))
            final_centroids[cluster_id_int] = centroid
        
        return updated_labels, final_centroids
    
    @staticmethod
    def split_large_clusters(
        coordinates: List[Tuple[float, float]],
        labels: np.ndarray,
        max_cluster_size: int = 30
    ) -> np.ndarray:
        """
        Split clusters that exceed max_cluster_size using K-means subdivision.

        Args:
            coordinates: List of (latitude, longitude) tuples - standard format
            labels: Current cluster labels
            max_cluster_size: Maximum allowed cluster size

        Returns:
            Updated labels with large clusters split
        """
        from sklearn.cluster import KMeans

        coords_array = np.array(coordinates)
        unique_labels = sorted(set(labels))
        max_label = max(unique_labels) if unique_labels else 0
        updated_labels = labels.copy()

        for label in unique_labels:
            if label == -1:
                continue

            cluster_indices = np.where(updated_labels == label)[0]
            cluster_size = len(cluster_indices)

            if cluster_size > max_cluster_size:
                # Split this cluster using K-means
                n_subclusters = int(np.ceil(cluster_size / max_cluster_size))
                cluster_coords = coords_array[cluster_indices]

                print(f"Splitting cluster {label} ({cluster_size} points) into {n_subclusters} subclusters")

                # Use K-means to split the cluster
                kmeans = KMeans(
                    n_clusters=n_subclusters,
                    random_state=42,
                    n_init=10
                )
                sub_labels = kmeans.fit_predict(cluster_coords)

                # Assign new cluster labels
                for i, sub_label in enumerate(sub_labels):
                    new_label = max_label + 1 + sub_label
                    updated_labels[cluster_indices[i]] = new_label

                max_label += n_subclusters

        return updated_labels

    @staticmethod
    def get_cluster_statistics(
        coordinates: List[Tuple[float, float]],
        labels: np.ndarray
    ) -> Dict:
        """
        Calculate statistics for each cluster.

        Args:
            coordinates: List of (latitude, longitude) tuples - standard format
            labels: Cluster labels array

        Returns:
            Dictionary with cluster statistics
        """
        coords_array = np.array(coordinates)
        unique_labels = np.unique(labels)

        stats = {}
        for label in unique_labels:
            mask = labels == label
            cluster_coords = coords_array[mask]  # coords_array is (lat, lng)

            stats[int(label)] = {
                "size": int(np.sum(mask)),
                "centroid": (float(np.mean(cluster_coords[:, 0])), float(np.mean(cluster_coords[:, 1]))),  # (lat, lng)
                "bbox": {
                    "min_lat": float(np.min(cluster_coords[:, 0])),  # latitude
                    "max_lat": float(np.max(cluster_coords[:, 0])),   # latitude
                    "min_lng": float(np.min(cluster_coords[:, 1])),  # longitude
                    "max_lng": float(np.max(cluster_coords[:, 1]))    # longitude
                }
            }

        return stats






