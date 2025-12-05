"""
Database seeding script for ezGO POC.

Seeds the database with:
- Service areas (Ottawa)
- Service zones (FSA-like zones using K-means clustering)
- Depots (strategically placed based on zone clusters)
- Orders (randomly distributed across zones)

Usage:
    cd backend
    uv run python -m app.scripts.seed
    
    # Or with custom parameters
    uv run python -m app.scripts.seed --zones 12 --depots 3 --orders 90
"""
import csv
import json
import sys
import random
import argparse
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from typing import List, Tuple, Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import shape, Polygon, MultiPolygon, Point, MultiPoint, mapping
from shapely.ops import unary_union
import h3
from sklearn.cluster import KMeans
import numpy as np

from app.core.database import SessionLocal
from app import models
from app.services.h3_service import H3Service
from app.models.order import Order

# Windows console UTF-8 support
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


# =============================================================================
# CONFIGURATION
# =============================================================================

class SeedConfig:
    """Configuration for database seeding."""
    
    # H3 resolutions to generate for coverage
    H3_RESOLUTIONS = [7, 8, 9, 10]
    
    # Default seeding parameters
    DEFAULT_NUM_ZONES = 12
    DEFAULT_NUM_DEPOTS = 3
    DEFAULT_NUM_ORDERS = 90
    DEFAULT_DRIVERS_PER_DEPOT = 5
    
    # H3 resolution for zone clustering
    ZONE_CLUSTERING_RESOLUTION = 8
    
    # Ottawa coordinate bounds for validation
    OTTAWA_LAT_MIN = 44.9
    OTTAWA_LAT_MAX = 46.1
    OTTAWA_LNG_MIN = -76.5
    OTTAWA_LNG_MAX = -74.9
    
    # Fallback coordinates (Ottawa downtown)
    FALLBACK_LAT = 45.4215
    FALLBACK_LNG = -75.6972


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calculate great circle distance between two points in kilometers.
    
    Args:
        lat1, lng1: First point coordinates
        lat2, lng2: Second point coordinates
    
    Returns:
        Distance in kilometers
    """
    lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
    
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return 6371.0 * c  # Earth's radius in km


def get_zone_centroid(zone) -> Tuple[float, float]:
    """
    Get centroid coordinates of a service zone.
    
    Args:
        zone: ServiceZone model instance
    
    Returns:
        (latitude, longitude) tuple
    """
    try:
        geom = to_shape(zone.boundary)
        centroid = geom.centroid
        # Shapely: x = longitude, y = latitude
        return (centroid.y, centroid.x)
    except Exception:
        return (SeedConfig.FALLBACK_LAT, SeedConfig.FALLBACK_LNG)


def h3_cells_to_polygon(cells: List[str]) -> Optional[Polygon]:
    """
    Convert H3 cells to a unified Shapely polygon.
    
    Note: h3.h3_to_geo_boundary returns (lat, lng) tuples even with geo_json=True,
    so we swap to (lng, lat) for Shapely compatibility.
    
    Args:
        cells: List of H3 cell IDs
    
    Returns:
        Shapely Polygon or None if conversion fails
    """
    polygons = []
    
    for cell in cells:
        try:
            # h3 returns (lat, lng), Shapely needs (lng, lat)
            boundary = h3.h3_to_geo_boundary(cell, geo_json=True)
            if boundary and len(boundary) >= 3:
                swapped = [(lng, lat) for lat, lng in boundary]
                poly = Polygon(swapped)
                if poly.is_valid:
                    polygons.append(poly)
        except Exception:
            continue
    
    if not polygons:
        return None
    
    unified = unary_union(polygons)
    
    if hasattr(unified, 'simplify'):
        unified = unified.simplify(0.001, preserve_topology=True)
    
    if isinstance(unified, MultiPolygon):
        unified = max(unified.geoms, key=lambda p: p.area)
    
    return unified if isinstance(unified, Polygon) else None


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def clear_database(db: Session) -> dict:
    """
    Clear all seeded data from database.
    
    Deletion order respects foreign key constraints.
    
    Returns:
        Dictionary with deletion counts
    """
    print("\n" + "=" * 70)
    print("Step 1: Clearing Database")
    print("=" * 70)
    
    counts = {}
    tables = [
        ('orders', Order),
        ('zone_depot_assignments', models.ZoneDepotAssignment),
        ('depots', models.Depot),
        ('service_zones', models.ServiceZone),
        ('h3_covers', models.H3Cover),
        ('h3_compacts', models.H3Compact),
        ('service_areas', models.ServiceArea),
    ]
    
    for name, model in tables:
        count = db.query(model).delete()
        counts[name] = count
        print(f"  ✓ Deleted {count} {name.replace('_', ' ')}")
        db.flush()
    
    db.commit()
    print("\n  ✅ Database cleared")
    return counts


def generate_h3_coverage(
    db: Session,
    owner_kind: str,
    owner_id,
    geom: Polygon,
    resolutions: List[int] = None
) -> None:
    """
    Generate H3 cell coverage for a polygon.
    
    Args:
        db: Database session
        owner_kind: Type of owner (service_area, service_zone)
        owner_id: UUID of the owner
        geom: Shapely Polygon
        resolutions: H3 resolutions to generate
    """
    resolutions = resolutions or SeedConfig.H3_RESOLUTIONS
    geojson = mapping(geom)
    
    for resolution in resolutions:
        try:
            cells = set(h3.polyfill(geojson, resolution))
            if not cells:
                continue
            
            # Bulk insert covers
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
            
            # Store compacted version
            compacted = list(h3.compact(cells))
            db.add(models.H3Compact(
                owner_kind=owner_kind,
                owner_id=owner_id,
                resolution=resolution,
                method=models.h3_cover.H3Method.COVERAGE,
                cells_compact=compacted
            ))
            
            db.flush()
            print(f"      Resolution {resolution}: {len(cells)} cells ({len(compacted)} compacted)")
            
        except Exception as e:
            print(f"      ⚠ Resolution {resolution} failed: {e}")
            continue
    
    db.commit()


# =============================================================================
# SEEDING FUNCTIONS
# =============================================================================

def seed_service_area(db: Session) -> models.ServiceArea:
    """
    Create Ottawa service area from CSV boundary data.
    
    Returns:
        Created ServiceArea instance
    """
    print("\n" + "=" * 70)
    print("Step 2: Creating Service Area")
    print("=" * 70)
    
    csv_path = Path(__file__).parent.parent.parent / "misc" / "service_area.csv"
    
    if not csv_path.exists():
        raise FileNotFoundError(f"Service area CSV not found: {csv_path}")
    
    # Load Ottawa boundary from CSV
    with open(csv_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('name', '').lower() == 'ottawa':
                geojson = json.loads(row['boundary'])
                geom = shape(geojson)
                break
        else:
            raise ValueError("Ottawa not found in service_area.csv")
    
    print(f"  ✓ Loaded Ottawa boundary ({len(geom.exterior.coords)} points)")
    
    # Create label cell from centroid
    centroid = geom.centroid
    label_cell = h3.geo_to_h3(centroid.y, centroid.x, resolution=9)
    
    # Create service area
    service_area = models.ServiceArea(
        name="Ottawa",
        description="Ottawa-Gatineau Metropolitan Area",
        boundary=from_shape(geom, srid=4326),
        label_cell=label_cell,
        default_res=9,
        is_active=True
    )
    
    db.add(service_area)
    db.flush()
    
    print(f"  ✓ Created service area: Ottawa")
    print(f"    Generating H3 coverage...")
    generate_h3_coverage(db, "service_area", service_area.id, geom)
    
    print("\n  ✅ Service area created")
    return service_area


def seed_service_zones(db: Session, num_zones: int = None) -> List[models.ServiceZone]:
    """
    Create service zones using K-means clustering on H3 cells.
    
    Args:
        db: Database session
        num_zones: Number of zones to create
    
    Returns:
        List of created ServiceZone instances
    """
    num_zones = num_zones or SeedConfig.DEFAULT_NUM_ZONES
    
    print("\n" + "=" * 70)
    print("Step 3: Creating Service Zones")
    print("=" * 70)
    
    # Get service area
    service_area = db.query(models.ServiceArea).filter(
        models.ServiceArea.is_active == True
    ).first()
    
    if not service_area:
        raise ValueError("No active service area found")
    
    service_area_polygon = to_shape(service_area.boundary)
    if isinstance(service_area_polygon, MultiPolygon):
        service_area_polygon = max(service_area_polygon.geoms, key=lambda p: p.area)
    
    # Get H3 cells for clustering
    h3_covers = db.query(models.H3Cover).filter(
        models.H3Cover.owner_kind == "service_area",
        models.H3Cover.owner_id == service_area.id,
        models.H3Cover.resolution == SeedConfig.ZONE_CLUSTERING_RESOLUTION
    ).all()
    
    cells = [cover.cell for cover in h3_covers]
    print(f"  ✓ Found {len(cells)} H3 cells for clustering")
    
    # Extract coordinates for K-means
    cell_coords = []
    cell_map = {}
    for cell in cells:
        try:
            lat, lng = h3.h3_to_geo(cell)
            cell_coords.append([lat, lng])
            cell_map[cell] = (lat, lng)
        except Exception:
            continue
    
    # K-means clustering
    print(f"  📊 Clustering into {num_zones} zones...")
    kmeans = KMeans(n_clusters=num_zones, random_state=42, n_init=10)
    labels = kmeans.fit_predict(np.array(cell_coords))
    
    # Group cells by cluster
    clusters = {i: [] for i in range(num_zones)}
    for idx, cell in enumerate(cells):
        if cell in cell_map:
            coord_idx = cell_coords.index(list(cell_map[cell]))
            clusters[labels[coord_idx]].append(cell)
    
    clusters = {k: v for k, v in clusters.items() if v}
    
    # Create zones
    created_zones = []
    
    for cluster_id, zone_cells in sorted(clusters.items()):
        zone_polygon = h3_cells_to_polygon(zone_cells)
        
        if not zone_polygon or zone_polygon.is_empty:
            continue
        
        # Clip to service area
        try:
            clipped = service_area_polygon.intersection(zone_polygon)
            if isinstance(clipped, MultiPolygon):
                clipped = max(clipped.geoms, key=lambda p: p.area)
            if not clipped.is_empty:
                zone_polygon = clipped
        except Exception:
            pass
        
        # Ensure validity
        if not zone_polygon.is_valid:
            zone_polygon = zone_polygon.buffer(0)
        
        zone_polygon = zone_polygon.simplify(0.001, preserve_topology=True)
        
        # Create zone
        centroid = zone_polygon.centroid
        zone_idx = len(created_zones) + 1
        
        zone = models.ServiceZone(
            service_area_id=service_area.id,
            code=f"Z{zone_idx:02d}",
            name=f"Zone-{zone_idx:02d}",
            boundary=from_shape(zone_polygon, srid=4326),
            label_cell=h3.geo_to_h3(centroid.y, centroid.x, resolution=9),
            default_res=9,
            is_active=True
        )
        
        db.add(zone)
        db.flush()
        
        print(f"    ✓ Zone-{zone_idx:02d} ({len(zone_cells)} cells)")
        generate_h3_coverage(db, "service_zone", zone.id, zone_polygon)
        
        created_zones.append(zone)
    
    db.commit()
    print(f"\n  ✅ Created {len(created_zones)} zones")
    return created_zones


def seed_depots(db: Session, num_depots: int = None) -> List[models.Depot]:
    """
    Create depots and assign zones using K-means clustering.
    
    Args:
        db: Database session
        num_depots: Number of depots to create
    
    Returns:
        List of created Depot instances
    """
    num_depots = num_depots or SeedConfig.DEFAULT_NUM_DEPOTS
    
    print("\n" + "=" * 70)
    print("Step 4: Creating Depots")
    print("=" * 70)
    
    zones = db.query(models.ServiceZone).filter(
        models.ServiceZone.is_active == True
    ).all()
    
    if not zones:
        raise ValueError("No service zones found")
    
    # Get zone centroids
    zone_centroids = [get_zone_centroid(z) for z in zones]
    
    # Cluster zones into depot groups
    print(f"  📊 Clustering {len(zones)} zones into {num_depots} depot groups...")
    kmeans = KMeans(n_clusters=num_depots, random_state=42, n_init=10)
    labels = kmeans.fit_predict(np.array(zone_centroids))
    
    # Group zones
    depot_groups = {i: [] for i in range(num_depots)}
    for idx, zone in enumerate(zones):
        depot_groups[labels[idx]].append(zone)
    
    depot_groups = {k: v for k, v in depot_groups.items() if v}
    
    # Create depots
    created_depots = []
    
    for cluster_id, cluster_zones in sorted(depot_groups.items()):
        # Calculate depot location as centroid of zone centroids
        zone_points = [Point(get_zone_centroid(z)[1], get_zone_centroid(z)[0]) 
                       for z in cluster_zones]
        
        if len(zone_points) == 1:
            centroid = zone_points[0]
        else:
            centroid = MultiPoint(zone_points).centroid
        
        depot_lng, depot_lat = centroid.x, centroid.y
        
        # Create depot
        depot_num = len(created_depots) + 1
        depot = models.Depot(
            name=f"Depot-{depot_num:02d}",
            address=f"Depot-{depot_num:02d}, Ottawa, ON",
            latitude=depot_lat,
            longitude=depot_lng,
            h3_index=h3.geo_to_h3(depot_lat, depot_lng, resolution=9),
            available_drivers=SeedConfig.DEFAULT_DRIVERS_PER_DEPOT,
            is_active=True
        )
        
        db.add(depot)
        db.flush()
        
        # Assign zones
        zone_names = []
        for zone in cluster_zones:
            db.add(models.ZoneDepotAssignment(
                zone_id=zone.id,
                depot_id=depot.id,
                is_primary=True,
                priority=1
            ))
            zone_names.append(zone.name)
        
        print(f"    ✓ Depot-{depot_num:02d} at ({depot_lat:.4f}, {depot_lng:.4f})")
        print(f"      Zones: {', '.join(zone_names)}")
        
        created_depots.append(depot)
    
    db.commit()
    print(f"\n  ✅ Created {len(created_depots)} depots")
    return created_depots


def seed_orders(db: Session, num_orders: int = None) -> List[Order]:
    """
    Create random orders within service area.
    
    Args:
        db: Database session
        num_orders: Number of orders to create
    
    Returns:
        List of created Order instances
    """
    from datetime import date
    
    num_orders = num_orders or SeedConfig.DEFAULT_NUM_ORDERS
    
    print("\n" + "=" * 70)
    print("Step 5: Creating Orders")
    print("=" * 70)
    
    # Get service area
    service_area = db.query(models.ServiceArea).filter(
        models.ServiceArea.is_active == True
    ).first()
    
    service_area_polygon = to_shape(service_area.boundary)
    if isinstance(service_area_polygon, MultiPolygon):
        service_area_polygon = max(service_area_polygon.geoms, key=lambda p: p.area)
    
    depots = db.query(models.Depot).filter(models.Depot.is_active == True).all()
    
    # Get bounds
    minx, miny, maxx, maxy = service_area_polygon.bounds
    
    print(f"  📦 Generating {num_orders} orders...")
    
    today = date.today()
    created_orders = []
    order_num = 1
    max_attempts = num_orders * 50
    
    for attempt in range(max_attempts):
        if len(created_orders) >= num_orders:
            break
        
        if attempt > 0 and attempt % 100 == 0:
            print(f"    Progress: {len(created_orders)}/{num_orders}")
        
        # Random point in bounds
        lng = minx + random.random() * (maxx - minx)
        lat = miny + random.random() * (maxy - miny)
        
        # Validate
        if not service_area_polygon.contains(Point(lng, lat)):
            continue
        
        if not (SeedConfig.OTTAWA_LAT_MIN <= lat <= SeedConfig.OTTAWA_LAT_MAX):
            continue
        if not (SeedConfig.OTTAWA_LNG_MIN <= lng <= SeedConfig.OTTAWA_LNG_MAX):
            continue
        
        # Find zone
        zone = db.query(models.ServiceZone).filter(
            func.ST_Contains(
                models.ServiceZone.boundary,
                func.ST_GeomFromText(f"POINT({lng} {lat})", 4326)
            )
        ).first()
        
        if not zone:
            continue
        
        # Find depot
        assignment = db.query(models.ZoneDepotAssignment).filter(
            models.ZoneDepotAssignment.zone_id == zone.id,
            models.ZoneDepotAssignment.is_primary == True
        ).first()
        
        if not assignment:
            continue
        
        # Create order
        order = Order(
            order_number=f"ORD-{today.strftime('%Y%m%d')}-{order_num:04d}",
            customer_name=f"Customer {order_num}",
            customer_contact=f"customer{order_num}@example.com",
            delivery_address=f"{zone.name} - Delivery #{order_num}",
            latitude=lat,
            longitude=lng,
            h3_index=H3Service.lat_lng_to_h3(lat, lng),
            zone_id=zone.id,
            depot_id=assignment.depot_id,
            order_date=today,
            scheduled_delivery_date=today,
            status="geocoded",
            weight_kg=round(5.0 + (order_num % 20), 2),
            volume_m3=round(0.1 + (order_num % 5) * 0.05, 2)
        )
        
        db.add(order)
        created_orders.append(order)
        order_num += 1
    
    db.commit()
    
    # Print distribution
    print(f"\n  📊 Order distribution:")
    for depot in depots:
        count = sum(1 for o in created_orders if o.depot_id == depot.id)
        print(f"      {depot.name}: {count} orders")
    
    print(f"\n  ✅ Created {len(created_orders)} orders")
    return created_orders


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main entry point for database seeding."""
    parser = argparse.ArgumentParser(description="Seed ezGO database")
    parser.add_argument("--zones", type=int, default=SeedConfig.DEFAULT_NUM_ZONES,
                        help=f"Number of zones (default: {SeedConfig.DEFAULT_NUM_ZONES})")
    parser.add_argument("--depots", type=int, default=SeedConfig.DEFAULT_NUM_DEPOTS,
                        help=f"Number of depots (default: {SeedConfig.DEFAULT_NUM_DEPOTS})")
    parser.add_argument("--orders", type=int, default=SeedConfig.DEFAULT_NUM_ORDERS,
                        help=f"Number of orders (default: {SeedConfig.DEFAULT_NUM_ORDERS})")
    parser.add_argument("--skip-clear", action="store_true",
                        help="Skip clearing existing data")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("🌱 ezGO Database Seeding")
    print("=" * 70)
    print(f"  Zones: {args.zones}, Depots: {args.depots}, Orders: {args.orders}")
    
    db = SessionLocal()
    
    try:
        if not args.skip_clear:
            clear_database(db)
        
        seed_service_area(db)
        seed_service_zones(db, args.zones)
        seed_depots(db, args.depots)
        seed_orders(db, args.orders)
        
        # Summary
        print("\n" + "=" * 70)
        print("✅ Seeding Complete")
        print("=" * 70)
        print(f"  Service Areas:  {db.query(models.ServiceArea).count()}")
        print(f"  Service Zones:  {db.query(models.ServiceZone).count()}")
        print(f"  Depots:         {db.query(models.Depot).count()}")
        print(f"  Orders:         {db.query(Order).count()}")
        print(f"  H3 Cells:       {db.query(models.H3Cover).count()}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

