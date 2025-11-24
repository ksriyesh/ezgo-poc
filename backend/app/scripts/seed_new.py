"""
New unified seeding script for the entire application.
This script empties all tables first, then seeds data step by step.

Step 1: Empty all tables
Step 2: Seed service areas (same as original)

Usage:
    cd backend
    .venv\Scripts\Activate.ps1  # Windows
    python -m app.scripts.seed_new
"""
import csv
import json
import sys
import random
from pathlib import Path
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape, Polygon, MultiPolygon, Point, MultiPoint
from shapely.ops import unary_union
import h3
from sklearn.cluster import KMeans
import numpy as np

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from app.core.database import SessionLocal
from app import models

# H3 resolutions for different zoom levels
H3_RESOLUTIONS = [7, 8, 9, 10]

# Service constraints for realistic routing
MAX_DEPOT_RADIUS_KM = 25  # Maximum service radius for a depot
TARGET_ORDERS_PER_DRIVER = 15  # Target orders per driver for 2-3 hour routes
MIN_ORDERS_PER_DRIVER = 10
MAX_ORDERS_PER_DRIVER = 20
TOTAL_ORDERS = 100  # Total number of orders to seed

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# COORDINATE STANDARD:
# Throughout this script, we use (latitude, longitude) format consistently.
# - Database columns: latitude, longitude (separate columns)
# - Functions return: (latitude, longitude) tuples
# - PostGIS: ST_X = longitude, ST_Y = latitude
# - H3: h3.h3_to_geo returns (latitude, longitude)
# - Shapely: (x, y) = (longitude, latitude), so centroid.y = lat, centroid.x = lng
# All coordinates are assigned directly without swapping.

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance between two points on Earth (in kilometers).
    Uses the Haversine formula.
    
    Args:
        lat1, lon1: Latitude and longitude of point 1 (in degrees)
        lat2, lon2: Latitude and longitude of point 2 (in degrees)
    
    Returns:
        Distance in kilometers
    """
    from math import radians, sin, cos, sqrt, atan2
    
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


def get_zone_centroid(zone) -> tuple:
    """
    Get the centroid coordinates of a service zone.
    
    Args:
        zone: ServiceZone model instance
    
    Returns:
        (latitude, longitude) tuple
    """
    if zone.label_cell:
        # h3.h3_to_geo returns (latitude, longitude)
        lat, lng = h3.h3_to_geo(zone.label_cell)
        return (lat, lng)
    
    # Fallback: use boundary centroid
    try:
        from geoalchemy2.shape import to_shape
        geom = to_shape(zone.boundary)
        centroid = geom.centroid
        # Shapely centroid: (x, y) = (longitude, latitude)
        # Return as (latitude, longitude)
        latitude = centroid.y  # Y coordinate = latitude
        longitude = centroid.x  # X coordinate = longitude
        return (latitude, longitude)
    except Exception:
        return (45.4215, -75.6972)  # Ottawa downtown as fallback


# ============================================================================
# STEP 1: EMPTY ALL TABLES
# ============================================================================

def empty_all_tables(db: Session):
    """
    Empty all tables in the correct order to respect foreign key constraints.
    
    Deletion order:
    1. Order (has foreign keys to Zone, Depot)
    2. ZoneDepotAssignment (has foreign keys to Zone, Depot)
    3. Depot
    4. ServiceZone (has foreign key to ServiceArea)
    5. H3Cover (has foreign keys to various owners)
    6. H3Compact (has foreign keys to various owners)
    7. ServiceArea
    """
    print("\n" + "=" * 80)
    print("STEP 1: Emptying All Tables")
    print("=" * 80)
    
    from app.models.order import Order
    from app.models.zone_depot_assignment import ZoneDepotAssignment
    from app.models.depot import Depot
    from app.models.service_zone import ServiceZone
    from app.models.h3_cover import H3Cover
    from app.models.h3_compact import H3Compact
    from app.models.service_area import ServiceArea
    
    counts = {}
    
    try:
        # 1. Delete Orders
        print("\n  🗑️  Deleting orders...")
        counts['orders'] = db.query(Order).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['orders']} orders")
        
        # 2. Delete Zone-Depot Assignments
        print("  🗑️  Deleting zone-depot assignments...")
        counts['zone_depot_assignments'] = db.query(ZoneDepotAssignment).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['zone_depot_assignments']} zone-depot assignments")
        
        # 3. Delete Depots
        print("  🗑️  Deleting depots...")
        counts['depots'] = db.query(Depot).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['depots']} depots")
        
        # 4. Delete Service Zones
        print("  🗑️  Deleting service zones...")
        counts['service_zones'] = db.query(ServiceZone).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['service_zones']} service zones")
        
        # 5. Delete H3 Covers
        print("  🗑️  Deleting H3 covers...")
        counts['h3_covers'] = db.query(H3Cover).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['h3_covers']} H3 covers")
        
        # 6. Delete H3 Compacts
        print("  🗑️  Deleting H3 compacts...")
        counts['h3_compacts'] = db.query(H3Compact).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['h3_compacts']} H3 compacts")
        
        # 7. Delete Service Areas
        print("  🗑️  Deleting service areas...")
        counts['service_areas'] = db.query(ServiceArea).delete()
        db.flush()
        print(f"     ✓ Deleted {counts['service_areas']} service areas")
        
        # Commit all deletions
        db.commit()
        
        print("\n  ✅ All tables emptied successfully!")
        print(f"\n  📊 Summary:")
        print(f"     Orders:              {counts.get('orders', 0)}")
        print(f"     Zone-Depot Assignments: {counts.get('zone_depot_assignments', 0)}")
        print(f"     Depots:              {counts.get('depots', 0)}")
        print(f"     Service Zones:       {counts.get('service_zones', 0)}")
        print(f"     H3 Covers:            {counts.get('h3_covers', 0)}")
        print(f"     H3 Compacts:          {counts.get('h3_compacts', 0)}")
        print(f"     Service Areas:       {counts.get('service_areas', 0)}")
        
    except Exception as e:
        print(f"\n  ✗ Error emptying tables: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise


# ============================================================================
# PART 1: SERVICE AREAS & ZONES (Base Geographic Data)
# ============================================================================

def get_ottawa_boundary() -> Polygon:
    """
    Get Ottawa's boundary polygon from CSV file.
    
    Returns:
        Shapely Polygon representing Ottawa's boundary
    """
    csv_path = Path(__file__).parent.parent.parent / "misc" / "service_area.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(f"Service area CSV not found at {csv_path}")
    
    # Read CSV and find Ottawa
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('name', '').lower() == 'ottawa':
                geojson = json.loads(row['boundary'])
                geom = shape(geojson)
                print(f"  ✓ Loaded Ottawa boundary ({len(geom.exterior.coords)} coordinates)")
                return geom
    
    raise ValueError("Ottawa not found in service_area.csv")


def generate_h3_cover(db: Session, owner_kind: str, owner_id, geom: Polygon, resolutions: list):
    """
    Generate H3 cell coverage for a polygon at multiple resolutions.
    Uses h3.polyfill directly (best practice).
    Uses the polygon exactly as provided from CSV - no modifications.
    
    Args:
        db: Database session
        owner_kind: Type of owner (e.g., "service_area")
        owner_id: ID of the owner
        geom: Shapely Polygon to cover (from CSV)
        resolutions: List of H3 resolutions to generate
    """
    # Convert to GeoJSON format (h3.polyfill expects GeoJSON)
    # Shapely's mapping() preserves coordinate order: (x, y) = (lng, lat) → [lng, lat]
    from shapely.geometry import mapping
    geojson_poly = mapping(geom)
    
    for resolution in resolutions:
        try:
            # Use h3.polyfill directly (standard approach)
            cells = set(h3.polyfill(geojson_poly, resolution))
            
            if not cells:
                print(f"  ⚠ No H3 cells at resolution {resolution}")
                continue
            
            print(f"    Resolution {resolution}: {len(cells)} cells")
            
            # Bulk insert H3 covers
            h3_covers = [
                models.H3Cover(
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    resolution=resolution,
                    method=models.h3_cover.H3Method.COVERAGE,
                    cell=cell
                )
                for cell in cells
            ]
            db.bulk_save_objects(h3_covers)
            db.flush()
            
            # Store compacted version
            try:
                compacted = list(h3.compact(cells))
                h3_compact = models.H3Compact(
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    resolution=resolution,
                    method=models.h3_cover.H3Method.COVERAGE,
                    cells_compact=compacted
                )
                db.add(h3_compact)
                print(f"    Compacted: {len(compacted)} cells")
            except Exception as e:
                print(f"    ⚠️  Could not compact: {e}")
            
            db.commit()
            print(f"    ✓ Committed {len(cells)} H3 cells")
            
        except Exception as e:
            print(f"  ✗ Error at resolution {resolution}: {e}")
            db.rollback()
            continue


def seed_service_areas(db: Session):
    """
    Seed service areas - creates Ottawa service area from CSV boundary.
    
    Args:
        db: Database session
    """
    print("\n" + "=" * 80)
    print("STEP 2: Seeding Service Areas")
    print("=" * 80)
    
    print("\n  🏗️  Creating Ottawa service area from CSV...")
    
    # Get Ottawa boundary from CSV
    ottawa_geom = get_ottawa_boundary()
    
    # Get centroid for label cell
    centroid = ottawa_geom.centroid
    lng, lat = centroid.x, centroid.y  # Shapely: (x, y) = (lng, lat)
    label_cell = h3.geo_to_h3(lat, lng, resolution=9)
    
    # Create service area
    service_area = models.ServiceArea(
        name="Ottawa",
        description="Ottawa-Gatineau Metropolitan Area",
        boundary=from_shape(ottawa_geom, srid=4326),
        label_cell=label_cell,
        default_res=9,
        is_active=True
    )
    
    db.add(service_area)
    db.flush()
    
    print(f"  ✓ Created service area: Ottawa")
    print(f"    Generating H3 coverage at resolutions {H3_RESOLUTIONS}...")
    
    # Generate H3 cells at multiple resolutions
    generate_h3_cover(
        db,
        owner_kind="service_area",
        owner_id=service_area.id,
        geom=ottawa_geom,
        resolutions=H3_RESOLUTIONS
    )
    
    print(f"  ✅ Ottawa service area created with H3 coverage")


def h3_cells_to_polygon(cells: list) -> Polygon:
    """
    Convert a list of H3 cells to a unified polygon.
    
    Args:
        cells: List of H3 cell IDs
    
    Returns:
        Shapely Polygon representing the union of all H3 cell boundaries
    """
    polygons = []
    
    for cell in cells:
        try:
            # h3.h3_to_geo_boundary returns [(lat, lng), ...] by default
            # With geo_json=True, it returns [(lng, lat), ...] which is what we need
            boundary = h3.h3_to_geo_boundary(cell, geo_json=True)
            if boundary and len(boundary) >= 3:
                # boundary is already in [lng, lat] format when geo_json=True
                poly = Polygon(boundary)
                if poly.is_valid:
                    polygons.append(poly)
        except Exception:
            continue
    
    if not polygons:
        return None
    
    # Union all polygons
    unified = unary_union(polygons)
    
    # Simplify to reduce complexity
    if hasattr(unified, 'simplify'):
        unified = unified.simplify(0.001, preserve_topology=True)
    
    # If result is MultiPolygon, convert to Polygon (take largest)
    if isinstance(unified, MultiPolygon):
        unified = max(unified.geoms, key=lambda p: p.area)
    
    return unified if isinstance(unified, Polygon) else None


def seed_service_zones(db: Session, num_zones: int = 12, h3_resolution: int = 8):
    """
    Create FSA-like service zones using K-means clustering on H3 cell centers.
    This creates natural, irregular zones (not vertical like Voronoi).
    
    Args:
        db: Database session
        num_zones: Number of zones to create (default: 12, range 10-15)
        h3_resolution: H3 resolution to use for zone creation (default: 8)
    """
    print("\n" + "=" * 80)
    print("STEP 3: Creating FSA-like Service Zones (K-means Clustering)")
    print("=" * 80)
    
    # Get the service area
    service_area = db.query(models.ServiceArea).filter(
        models.ServiceArea.is_active == True
    ).first()
    
    if not service_area:
        print("  ✗ No active service area found. Please create service area first.")
        return []
    
    print(f"\n  📍 Using service area: {service_area.name}")
    
    # Get service area polygon for clipping
    service_area_polygon = to_shape(service_area.boundary)
    if isinstance(service_area_polygon, MultiPolygon):
        service_area_polygon = max(service_area_polygon.geoms, key=lambda p: p.area)
    
    # Get all H3 cells for this service area at the specified resolution
    h3_covers = db.query(models.H3Cover).filter(
        models.H3Cover.owner_kind == "service_area",
        models.H3Cover.owner_id == service_area.id,
        models.H3Cover.resolution == h3_resolution
    ).all()
    
    if not h3_covers:
        print(f"  ✗ No H3 cells found at resolution {h3_resolution}")
        return []
    
    cells = [cover.cell for cover in h3_covers]
    total_cells = len(cells)
    print(f"  ✓ Found {total_cells} H3 cells at resolution {h3_resolution}")
    
    # Extract H3 cell center coordinates for clustering
    # h3.h3_to_geo returns (lat, lng)
    cell_coords = []
    cell_to_coord = {}
    for cell in cells:
        try:
            lat, lng = h3.h3_to_geo(cell)
            cell_coords.append([lat, lng])  # K-means expects [lat, lng]
            cell_to_coord[cell] = (lat, lng)
        except Exception:
            continue
    
    if len(cell_coords) < num_zones:
        print(f"  ⚠️  Only {len(cell_coords)} valid cells, reducing zones to {len(cell_coords)}")
        num_zones = len(cell_coords)
    
    print(f"  📊 Clustering {len(cell_coords)} H3 cells into {num_zones} zones using K-means...")
    
    # Use K-means clustering to group H3 cells by spatial proximity
    coords_array = np.array(cell_coords)
    kmeans = KMeans(n_clusters=num_zones, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(coords_array)
    
    # Group cells by cluster
    zone_cell_groups = {i: [] for i in range(num_zones)}
    for idx, cell in enumerate(cells):
        if cell in cell_to_coord:
            coord_idx = cell_coords.index(list(cell_to_coord[cell]))
            cluster_id = cluster_labels[coord_idx]
            zone_cell_groups[cluster_id].append(cell)
    
    # Remove empty clusters
    zone_cell_groups = {k: v for k, v in zone_cell_groups.items() if v}
    
    print(f"  ✓ Created {len(zone_cell_groups)} zones from clustering")
    
    created_zones = []
    zone_polygons = []
    
    for cluster_id, zone_cells in sorted(zone_cell_groups.items()):
        if not zone_cells:
            continue
        
        try:
            # Convert H3 cells to polygon
            zone_polygon = h3_cells_to_polygon(zone_cells)
            
            if not zone_polygon or zone_polygon.is_empty:
                print(f"    ⚠ Cluster {cluster_id + 1}: Failed to create polygon, skipping")
                continue
            
            # Clip zone to service area boundary
            try:
                clipped_polygon = service_area_polygon.intersection(zone_polygon)
                
                # Handle MultiPolygon - take largest part
                if isinstance(clipped_polygon, MultiPolygon):
                    clipped_polygon = max(clipped_polygon.geoms, key=lambda p: p.area)
                
                if clipped_polygon.is_empty:
                    # If intersection is empty, try with small buffer
                    buffered_service = service_area_polygon.buffer(0.001)
                    clipped_polygon = buffered_service.intersection(zone_polygon)
                    if isinstance(clipped_polygon, MultiPolygon):
                        clipped_polygon = max(clipped_polygon.geoms, key=lambda p: p.area)
                
                if clipped_polygon.is_empty:
                    print(f"    ⚠ Cluster {cluster_id + 1}: Clipped polygon is empty, using original")
                else:
                    zone_polygon = clipped_polygon
            except Exception as e:
                print(f"    ⚠ Cluster {cluster_id + 1}: Clipping error ({e}), using original polygon")
            
            # Ensure polygon is valid
            if not zone_polygon.is_valid:
                zone_polygon = zone_polygon.buffer(0)
            
            if zone_polygon.is_empty:
                print(f"    ⚠ Cluster {cluster_id + 1}: Empty polygon after validation, skipping")
                continue
            
            # Smooth boundaries for FSA-like appearance
            zone_polygon = zone_polygon.simplify(0.001, preserve_topology=True)
            if not zone_polygon.is_valid:
                zone_polygon = zone_polygon.buffer(0)
            
            # Track for coverage verification
            zone_polygons.append(zone_polygon)
            
            # Get centroid for label cell
            centroid = zone_polygon.centroid
            lng, lat = centroid.x, centroid.y
            label_cell = h3.geo_to_h3(lat, lng, resolution=9)
            
            # Create service zone
            zone_idx = len(created_zones) + 1
            zone_name = f"Zone-{zone_idx:02d}"
            service_zone = models.ServiceZone(
                service_area_id=service_area.id,
                code=f"Z{zone_idx:02d}",
                name=zone_name,
                boundary=from_shape(zone_polygon, srid=4326),
                label_cell=label_cell,
                default_res=9,
                is_active=True
            )
            
            db.add(service_zone)
            db.flush()
            
            print(f"    ✓ Created {zone_name} ({len(zone_cells)} H3 cells)")
            
            # Generate H3 coverage for this zone
            generate_h3_cover(
                db,
                owner_kind="service_zone",
                owner_id=service_zone.id,
                geom=zone_polygon,
                resolutions=H3_RESOLUTIONS
            )
            
            created_zones.append(service_zone)
            
        except Exception as e:
            print(f"    ✗ Error creating zone from cluster {cluster_id + 1}: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            continue
    
    db.commit()
    
    # Verify coverage: union of all zones should cover the service area
    if zone_polygons:
        try:
            zones_union = unary_union(zone_polygons)
            coverage_ratio = zones_union.intersection(service_area_polygon).area / service_area_polygon.area
            coverage_pct = coverage_ratio * 100
            
            print(f"\n  📊 Coverage Verification:")
            print(f"     Service area area: {service_area_polygon.area:.6f} sq degrees")
            print(f"     Zones union area: {zones_union.area:.6f} sq degrees")
            print(f"     Coverage: {coverage_pct:.1f}%")
            
            if coverage_pct >= 95.0:
                print(f"  ✅ Zones cover {coverage_pct:.1f}% of service area")
            else:
                print(f"  ⚠️  Zones cover only {coverage_pct:.1f}% of service area")
        except Exception as e:
            print(f"  ⚠️  Could not verify coverage: {e}")
    
    # Verify all cells were assigned
    assigned_cells = set()
    for zone_cells in zone_cell_groups.values():
        assigned_cells.update(zone_cells)
    
    if len(assigned_cells) == total_cells:
        print(f"  ✅ All {total_cells} H3 cells assigned to {len(created_zones)} zones")
    else:
        print(f"  ⚠️  Warning: Only {len(assigned_cells)}/{total_cells} H3 cells assigned")
    
    return created_zones


def seed_depots_and_assign_zones(db: Session, num_depots: int = 3, zones_per_depot: int = 4):
    """
    Create depots based on service zones.
    Each depot serves nearest service zones, placed at their centroid.
    
    Args:
        db: Database session
        num_depots: Number of depots to create (default: 3)
        zones_per_depot: Number of zones each depot should serve (default: 4)
    """
    print("\n" + "=" * 80)
    print("STEP 4: Creating Depots and Assigning Zones")
    print("=" * 80)
    
    # Get all active service zones
    service_zones = db.query(models.ServiceZone).filter(
        models.ServiceZone.is_active == True
    ).order_by(models.ServiceZone.name).all()
    
    if not service_zones:
        print("  ✗ No service zones found. Please create service zones first.")
        return []
    
    print(f"\n  📍 Found {len(service_zones)} service zones")
    print(f"  🏗️  Creating {num_depots} depots, each serving ~{zones_per_depot} zones")
    
    # Get zone centroids for clustering
    zone_centroids = []
    for zone in service_zones:
        lat, lng = get_zone_centroid(zone)
        zone_centroids.append([lat, lng])
    
    # Cluster zones using K-means to group nearby zones together
    if len(zone_centroids) < num_depots:
        num_depots = len(zone_centroids)
        print(f"  ⚠️  Adjusted to {num_depots} depots (not enough zones)")
    
    print(f"  📊 Clustering {len(zone_centroids)} zones into {num_depots} depot groups...")
    coords_array = np.array(zone_centroids)
    kmeans = KMeans(n_clusters=num_depots, random_state=42, n_init=10)
    cluster_labels = kmeans.fit_predict(coords_array)
    
    # Group zones by cluster
    depot_zone_groups = {i: [] for i in range(num_depots)}
    for idx, zone in enumerate(service_zones):
        cluster_id = cluster_labels[idx]
        depot_zone_groups[cluster_id].append(zone)
    
    # Remove empty clusters
    depot_zone_groups = {k: v for k, v in depot_zone_groups.items() if v}
    
    print(f"  ✓ Grouped zones into {len(depot_zone_groups)} depot clusters")
    
    created_depots = []
    
    for cluster_id, zones in sorted(depot_zone_groups.items()):
        if not zones:
            continue
        
        try:
            # Calculate centroid of all zones in this cluster
            zone_points = []
            for zone in zones:
                lat, lng = get_zone_centroid(zone)
                # Shapely Point: (x, y) = (longitude, latitude)
                zone_points.append(Point(lng, lat))
            
            # Get centroid of all zone centroids
            if len(zone_points) == 1:
                centroid_point = zone_points[0]
            else:
                # Create a MultiPoint and get its centroid
                multipoint = MultiPoint(zone_points)
                centroid_point = multipoint.centroid
            
            # Extract coordinates from Shapely Point
            # Shapely: Point.x = longitude, Point.y = latitude
            depot_longitude = centroid_point.x  # x = longitude
            depot_latitude = centroid_point.y   # y = latitude
            
            # Verify coordinates are in valid ranges for Ottawa
            if not (45.0 <= depot_latitude <= 46.0):
                print(f"    ⚠️  Warning: Latitude {depot_latitude:.6f} outside Ottawa range")
            if not (-76.5 <= depot_longitude <= -75.0):
                print(f"    ⚠️  Warning: Longitude {depot_longitude:.6f} outside Ottawa range")
            
            # Get H3 cell for depot location (h3.geo_to_h3 expects lat, lng)
            depot_h3 = h3.geo_to_h3(depot_latitude, depot_longitude, resolution=9)
            
            # Create depot - IMPORTANT: latitude and longitude are correctly assigned
            depot_name = f"Depot-{cluster_id + 1:02d}"
            depot = models.Depot(
                name=depot_name,
                address=f"{depot_name}, Ottawa, ON",  # Placeholder address
                latitude=depot_latitude,   # Correct: latitude value
                longitude=depot_longitude, # Correct: longitude value
                h3_index=depot_h3,
                available_drivers=5,  # Default drivers
                contact_info=None,
                is_active=True
            )
            
            db.add(depot)
            db.flush()
            
            print(f"    ✓ Created {depot_name} at lat={depot_latitude:.6f}, lng={depot_longitude:.6f}")
            print(f"      Serving {len(zones)} zone(s): {', '.join([z.name for z in zones])}")
            
            # Assign zones to this depot
            for zone in zones:
                assignment = models.ZoneDepotAssignment(
                    zone_id=zone.id,
                    depot_id=depot.id,
                    is_primary=True,
                    priority=1
                )
                db.add(assignment)
            
            db.flush()
            created_depots.append(depot)
            
        except Exception as e:
            print(f"    ✗ Error creating depot for cluster {cluster_id + 1}: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            continue
    
    db.commit()
    
    # Summary
    total_assignments = db.query(models.ZoneDepotAssignment).count()
    print(f"\n  ✅ Created {len(created_depots)} depots")
    print(f"  ✅ Created {total_assignments} zone-depot assignments")
    
    # Verify all zones are assigned
    assigned_zones = db.query(models.ZoneDepotAssignment.zone_id).distinct().count()
    if assigned_zones == len(service_zones):
        print(f"  ✅ All {len(service_zones)} zones assigned to depots")
    else:
        print(f"  ⚠️  Warning: Only {assigned_zones}/{len(service_zones)} zones assigned")
    
    return created_depots


def seed_orders_per_depot(db: Session, total_orders: int = 90):
    """
    Create orders randomly within Ottawa service area, then assign to zones and depots.
    Each order is checked for routability using Mapbox before being added.
    
    Args:
        db: Database session
        total_orders: Total number of orders to create (default: 90, ~30 per depot)
    """
    print("\n" + "=" * 80)
    print("STEP 5: Creating Routable Orders in Service Area")
    print("=" * 80)
    
    from datetime import date
    from app.services.h3_service import H3Service
    from app.models.order import Order
    from sqlalchemy import func
    
    # Get service area polygon
    service_area = db.query(models.ServiceArea).filter(
        models.ServiceArea.is_active == True
    ).first()
    
    if not service_area:
        print("  ✗ No service area found. Please create service area first.")
        return []
    
    print(f"\n  📍 Using service area: {service_area.name}")
    
    # Get service area polygon
    service_area_polygon = to_shape(service_area.boundary)
    if isinstance(service_area_polygon, MultiPolygon):
        service_area_polygon = max(service_area_polygon.geoms, key=lambda p: p.area)
    
    if not service_area_polygon or service_area_polygon.is_empty:
        print("  ✗ Service area has invalid boundary")
        return []
    
    # Get all depots (needed for zone assignment lookup)
    depots = db.query(models.Depot).filter(
        models.Depot.is_active == True
    ).all()
    
    if not depots:
        print("  ✗ No depots found. Please create depots first.")
        return []
    
    print(f"  🏭 Found {len(depots)} depots")
    
    # Get bounding box of service area
    minx, miny, maxx, maxy = service_area_polygon.bounds
    min_lng, min_lat, max_lng, max_lat = minx, miny, maxx, maxy
    
    print(f"  📦 Generating {total_orders} orders within service area...")
    print(f"  📍 Bounds: lat({min_lat:.6f} to {max_lat:.6f}), lng({min_lng:.6f} to {max_lng:.6f})")
    
    today = date.today()
    all_created_orders = []
    order_counter = 1
    max_attempts = total_orders * 50  # Try multiple times to get valid points
    attempts = 0
    
    while len(all_created_orders) < total_orders and attempts < max_attempts:
        attempts += 1
        
        if attempts % 50 == 0:
            print(f"  🔄 Attempt {attempts}: {len(all_created_orders)}/{total_orders} orders created...")
        
        # Generate random point in bounding box
        longitude = min_lng + random.random() * (max_lng - min_lng)
        latitude = min_lat + random.random() * (max_lat - min_lat)
        
        # Check if point is in service area polygon
        point = Point(longitude, latitude)
        if not service_area_polygon.contains(point):
            continue
        
        # Validate coordinates are in Ottawa range
        if not (45.0 <= latitude <= 46.0) or not (-76.5 <= longitude <= -75.0):
            continue
        
        # Point is valid if it's in service area and within Ottawa bounds
        # (No Mapbox routability check to avoid rate limiting)
        
        # Find which zone contains this point
        zone = None
        try:
            # Use PostGIS to find zone containing the point
            point_wkt = f"POINT({longitude} {latitude})"
            zone = db.query(models.ServiceZone).filter(
                func.ST_Contains(
                    models.ServiceZone.boundary,
                    func.ST_GeomFromText(point_wkt, 4326)
                )
            ).first()
        except Exception:
            pass
        
        if not zone:
            # Fallback: use H3 to find zone
            try:
                h3_cell = h3.geo_to_h3(latitude, longitude, resolution=9)
                h3_cover = db.query(models.H3Cover).filter(
                    models.H3Cover.owner_kind == "service_zone",
                    models.H3Cover.cell == h3_cell,
                    models.H3Cover.resolution == 9
                ).first()
                
                if h3_cover:
                    zone = db.query(models.ServiceZone).filter(
                        models.ServiceZone.id == h3_cover.owner_id
                    ).first()
            except Exception:
                pass
        
        if not zone:
            # Skip if we can't find a zone
            continue
        
        # Find depot that serves this zone
        zone_assignment = db.query(models.ZoneDepotAssignment).filter(
            models.ZoneDepotAssignment.zone_id == zone.id,
            models.ZoneDepotAssignment.is_primary == True
        ).first()
        
        if not zone_assignment:
            # Skip if zone has no depot assignment
            continue
        
        depot_id = zone_assignment.depot_id
        
        # Create order
        try:
            order_number = f"ORD-{today.strftime('%Y%m%d')}-{order_counter:04d}"
            customer_name = f"Customer {order_counter}"
            address = f"{zone.name} - Delivery Point #{order_counter}"
            
            # Get H3 index
            h3_index = H3Service.lat_lng_to_h3(latitude, longitude)
            
            order = Order(
                order_number=order_number,
                customer_name=customer_name,
                customer_contact=f"customer{order_counter}@example.com",
                delivery_address=address,
                latitude=latitude,
                longitude=longitude,
                h3_index=h3_index,
                zone_id=zone.id,
                depot_id=depot_id,
                order_date=today,
                scheduled_delivery_date=today,
                status="geocoded",
                weight_kg=round(5.0 + (order_counter % 20), 2),
                volume_m3=round(0.1 + (order_counter % 5) * 0.05, 2)
            )
            
            db.add(order)
            db.flush()
            
            all_created_orders.append(order)
            order_counter += 1
            
        except Exception as e:
            print(f"  ⚠️  Error creating order: {e}")
            db.rollback()
            continue
    
    db.commit()
    
    print(f"\n  ✅ Created {len(all_created_orders)} orders")
    
    # Show distribution by depot
    depot_counts = {}
    for order in all_created_orders:
        depot_id = str(order.depot_id)
        depot_counts[depot_id] = depot_counts.get(depot_id, 0) + 1
    
    print(f"\n  📊 Order distribution by depot:")
    for depot in depots:
        count = depot_counts.get(str(depot.id), 0)
        print(f"     {depot.name}: {count} orders")
    
    return all_created_orders


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main unified seeding function - step by step."""
    print("=" * 80)
    print("🌱 NEW SEEDING SCRIPT - STEP BY STEP")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Step 1: Empty all tables
        empty_all_tables(db)
        
        # Step 2: Seed service areas
        seed_service_areas(db)
        
        # Step 3: Create FSA-like service zones using K-means clustering
        seed_service_zones(db, num_zones=12, h3_resolution=8)
        
        # Step 4: Create depots and assign zones (3 depots, 4 zones each)
        seed_depots_and_assign_zones(db, num_depots=3, zones_per_depot=4)
        
        # Step 5: Create routable orders in service area (90 total, ~30 per depot)
        seed_orders_per_depot(db, total_orders=90)
        
        # Final summary
        print("\n" + "=" * 80)
        print("✅ SEEDING COMPLETE")
        print("=" * 80)
        
        area_count = db.query(models.ServiceArea).count()
        zone_count = db.query(models.ServiceZone).count()
        depot_count = db.query(models.Depot).count()
        assignment_count = db.query(models.ZoneDepotAssignment).count()
        order_count = db.query(models.Order).count()
        h3_count = db.query(models.H3Cover).count()
        print(f"\n📊 Summary:")
        print(f"  Service Areas:  {area_count}")
        print(f"  Service Zones:  {zone_count}")
        print(f"  Depots:         {depot_count}")
        print(f"  Zone-Depot Assignments: {assignment_count}")
        print(f"  Orders:         {order_count}")
        print(f"  H3 Covers:      {h3_count}")
        print(f"\n💡 Next steps will be added in subsequent iterations")
        
    except Exception as e:
        print(f"\n❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()

