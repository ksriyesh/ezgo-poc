"""
Unified seeding script for the entire application.
Seeds service areas, zones, depots, and orders in the correct order.

Configuration:
    - TOTAL_ORDERS: Number of orders to generate (default: 100)
    - TARGET_ORDERS_PER_DRIVER: Orders per driver (default: 15)
    - Adjust these constants below to change seeding behavior

Usage:
    cd backend
    .venv\Scripts\Activate.ps1  # Windows
    python -m app.scripts.seed_all
"""
import csv
import json
import sys
import random
from pathlib import Path
from datetime import date
from typing import Dict, List, Set
from sqlalchemy.orm import Session
from geoalchemy2.shape import from_shape
from shapely.geometry import shape, Polygon, MultiPolygon, Point
from shapely.ops import unary_union
import h3

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
from app import models, crud, schemas

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
# PART 1: SERVICE AREAS & ZONES (Base Geographic Data)
# ============================================================================

def get_ottawa_boundary_from_csv() -> Polygon:
    """
    Get Ottawa's boundary from the CSV file.
    Reads the detailed polygon boundary from service_area.csv.
    
    Returns:
        Shapely Polygon representing Ottawa's boundary, or None if not found
    """
    areas_data = read_service_areas_csv()
    
    # Find Ottawa in the CSV
    for area_data in areas_data:
        if area_data.get('name', '').lower() == 'ottawa':
            geom = parse_geometry(area_data['boundary'])
            if geom:
                print(f"  ✓ Found Ottawa boundary in CSV with {len(geom.exterior.coords)} coordinates")
                return geom
    
    print("  ⚠️  Ottawa not found in CSV, returning None")
    return None


def get_ottawa_boundary() -> Polygon:
    """
    Get Ottawa's boundary as a polygon.
    First tries to read from CSV, falls back to approximate bounding box.
    
    Returns:
        Shapely Polygon representing Ottawa's boundary
    """
    # Try to get from CSV first
    ottawa_polygon = get_ottawa_boundary_from_csv()
    
    if ottawa_polygon:
        return ottawa_polygon
    
    # Fallback: approximate bounding box
    print("  ⚠️  Using approximate bounding box (CSV not available)")
    ottawa_bbox = [
        (-76.2, 45.15),  # Southwest corner
        (-75.3, 45.15),  # Southeast corner
        (-75.3, 45.55),  # Northeast corner
        (-76.2, 45.55),  # Northwest corner
        (-76.2, 45.15)   # Close polygon
    ]
    
    return Polygon(ottawa_bbox)


def read_service_areas_csv() -> list:
    """Read service areas from CSV file (legacy - not used if creating Ottawa programmatically)."""
    csv_path = Path(__file__).parent.parent.parent / "misc" / "service_area.csv"
    
    if not csv_path.exists():
        print(f"⚠ Service areas CSV not found at {csv_path}")
        return []
    
    service_areas = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            service_areas.append(row)
    
    return service_areas


def parse_geometry(geom_str: str):
    """Parse geometry from GeoJSON string."""
    try:
        geojson = json.loads(geom_str)
        return shape(geojson)
    except Exception as e:
        print(f"✗ Error parsing geometry: {e}")
        return None


def get_h3_label_cell(geom, resolution: int = 9) -> str:
    """Get a representative H3 cell for labeling from geometry centroid."""
    try:
        centroid = geom.centroid
        # Shapely centroid: (x, y) = (longitude, latitude)
        lng, lat = centroid.x, centroid.y
        # h3.geo_to_h3 expects (lat, lng)
        return h3.geo_to_h3(lat, lng, resolution)
    except Exception as e:
        print(f"  ⚠ Could not generate H3 label cell: {e}")
        return None


def validate_and_fix_geometry(geom):
    """Validate and fix geometry issues."""
    if not geom or geom.is_empty:
        return None
    
    if not geom.is_valid:
        try:
            geom = geom.buffer(0)
        except Exception:
            return None
    
    return geom


def process_single_polygon_for_h3(polygon, resolution, verbose=False):
    """Process a single polygon and return H3 cells with fallback strategies."""
    # Strategy 1: Standard polyfill
    try:
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        
        from shapely.geometry import mapping
        geojson_poly = mapping(polygon)
        
        # h3.polyfill expects GeoJSON format with [lng, lat] coordinates
        # Shapely's mapping already returns coordinates in (x, y) = (lng, lat) format
        if geojson_poly['type'] == 'Polygon':
            try:
                cells = h3.polyfill(geojson_poly, resolution)
                if cells and len(cells) > 0:
                    if verbose:
                        print(f"      ✓ Polyfill success: {len(cells)} cells")
                    return set(cells)
                elif verbose:
                    print(f"      ⚠ Polyfill returned empty set")
            except Exception as e:
                if verbose:
                    print(f"      ✗ Polyfill error: {str(e)[:200]}")
    except Exception as e:
        if verbose:
            print(f"      Polyfill failed: {str(e)[:100]}")
    
    # Strategy 2: Boundary sampling
    try:
        cells = set()
        coords = list(polygon.exterior.coords)
        sample_rate = max(1, len(coords) // 30)
        
        for i in range(0, len(coords), sample_rate):
            lng, lat = coords[i]
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                try:
                    cell = h3.geo_to_h3(lat, lng, resolution)
                    if cell:
                        cells.add(cell)
                except Exception:
                    pass
        
        if cells:
            if verbose:
                print(f"      Success with boundary sampling ({len(cells)} cells)")
            return cells
    except Exception as e:
        if verbose:
            print(f"      Boundary sampling failed: {str(e)[:100]}")
    
    # Strategy 3: Centroid fallback
    try:
        centroid = polygon.centroid
        # Shapely centroid: (x, y) = (longitude, latitude)
        lng, lat = centroid.x, centroid.y
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            # h3.geo_to_h3 expects (lat, lng)
            cell = h3.geo_to_h3(lat, lng, resolution)
            if cell:
                if verbose:
                    print(f"      Success with centroid only")
                return {cell}
    except Exception:
        pass
    
    return set()


def verify_h3_coverage(geom: Polygon, h3_cells: set, resolution: int, sample_points: int = 100) -> dict:
    """
    Verify that H3 cells cover the entire polygon boundary.
    Samples random points within the polygon and checks if they fall within H3 cells.
    
    IMPORTANT: h3.polyfill returns cells that INTERSECT the polygon, not just cells
    that are completely inside. So we check if the point's H3 cell is in the set OR
    if the point falls within any of the H3 cell boundaries.
    
    Args:
        geom: The polygon to verify (Shapely Polygon with coordinates as (lng, lat))
        h3_cells: Set of H3 cell IDs
        resolution: H3 resolution
        sample_points: Number of sample points to test
    
    Returns:
        Dictionary with coverage statistics
    """
    from shapely.geometry import Point, Polygon as ShapelyPolygon
    
    if not geom or not h3_cells:
        return {"coverage": 0.0, "tested": 0, "covered": 0}
    
    # Build a union of all H3 cell boundaries for faster checking
    # This is more accurate than just checking if point's cell is in set
    h3_polygons = []
    for cell in list(h3_cells)[:1000]:  # Limit to first 1000 for performance
        try:
            # h3.h3_to_geo_boundary returns [(lat, lng), ...] or [(lng, lat), ...] depending on geo_json flag
            # With geo_json=True, it returns [(lng, lat), ...] which is what we need
            boundary = h3.h3_to_geo_boundary(cell, geo_json=True)
            if boundary and len(boundary) >= 3:
                # boundary is already in [lng, lat] format when geo_json=True
                poly = ShapelyPolygon(boundary)
                if poly.is_valid:
                    h3_polygons.append(poly)
        except Exception:
            continue
    
    # Generate random points within the polygon
    # Shapely bounds: (minx, miny, maxx, maxy) where x=longitude, y=latitude
    minx, miny, maxx, maxy = geom.bounds
    tested = 0
    covered = 0
    
    for _ in range(sample_points):
        # Generate random point within bounding box
        import random
        lng = random.uniform(minx, maxx)  # longitude (x)
        lat = random.uniform(miny, maxy)  # latitude (y)
        point = Point(lng, lat)  # Shapely uses (x, y) = (lng, lat)
        
        # Check if point is within polygon
        if geom.contains(point) or geom.touches(point):
            tested += 1
            is_covered = False
            
            # Method 1: Check if point's H3 cell is in the set (fast)
            try:
                # h3.geo_to_h3 expects (lat, lng) in degrees
                h3_cell = h3.geo_to_h3(lat, lng, resolution)
                if h3_cell in h3_cells:
                    is_covered = True
                    covered += 1
            except Exception:
                pass
            
            # Method 2: If not found, check if point falls within any H3 cell boundary (more accurate)
            if not is_covered and h3_polygons:
                for h3_poly in h3_polygons:
                    if h3_poly.contains(point) or h3_poly.touches(point):
                        is_covered = True
                        covered += 1
                        break
    
    coverage = (covered / tested * 100) if tested > 0 else 0.0
    
    return {
        "coverage": coverage,
        "tested": tested,
        "covered": covered,
        "total_cells": len(h3_cells)
    }


def generate_h3_cover(db: Session, owner_kind: str, owner_id, geom, resolutions: list, verify_coverage: bool = True):
    """
    Generate H3 cell coverage for a geometry at multiple resolutions.
    
    Args:
        db: Database session
        owner_kind: Type of owner (e.g., "service_area")
        owner_id: ID of the owner
        geom: Geometry to cover
        resolutions: List of H3 resolutions to generate
        verify_coverage: If True, verify that H3 cells cover the entire boundary
    """
    if not geom:
        return
    
    geom = validate_and_fix_geometry(geom)
    if not geom:
        print(f"  ✗ Invalid geometry, skipping H3 generation")
        return
    
    for resolution in resolutions:
        try:
            all_cells = set()
            
            if isinstance(geom, MultiPolygon):
                for polygon in geom.geoms:
                    cells = process_single_polygon_for_h3(polygon, resolution)
                    if cells:
                        all_cells.update(cells)
            elif isinstance(geom, Polygon):
                cells = process_single_polygon_for_h3(geom, resolution, verbose=True)
                if cells:
                    all_cells.update(cells)
            
            if not all_cells:
                print(f"  ⚠ No H3 cells generated at resolution {resolution}")
                continue
            
            print(f"    Resolution {resolution}: {len(all_cells)} cells")
            
            # Verify coverage if requested
            if verify_coverage and isinstance(geom, Polygon):
                coverage_stats = verify_h3_coverage(geom, all_cells, resolution)
                print(f"      Coverage verification: {coverage_stats['coverage']:.1f}% "
                      f"({coverage_stats['covered']}/{coverage_stats['tested']} points covered)")
                
                # Debug: Show sample of H3 cells and test a few points
                if coverage_stats['coverage'] == 0.0 and len(all_cells) > 0:
                    print(f"      🔍 Debug: Testing first 3 H3 cells...")
                    sample_cells = list(all_cells)[:3]
                    for cell in sample_cells:
                        try:
                            # Get center of H3 cell
                            lat, lng = h3.h3_to_geo(cell)
                            print(f"        Cell {cell}: center at ({lat:.4f}, {lng:.4f})")
                            # Check if this cell is in our set (should always be True)
                            if cell in all_cells:
                                print(f"          ✓ Cell is in set")
                            else:
                                print(f"          ✗ Cell NOT in set (ERROR!)")
                        except Exception as e:
                            print(f"        Error with cell {cell}: {e}")
                
                if coverage_stats['coverage'] < 95.0:
                    print(f"      ⚠️  Warning: Coverage is below 95% - some areas may not be fully covered")
            
            # Insert H3 cells (batch insert for better performance)
            h3_covers = []
            for cell in all_cells:
                h3_cover = models.H3Cover(
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    resolution=resolution,
                    method=models.h3_cover.H3Method.COVERAGE,
                    cell=cell
                )
                h3_covers.append(h3_cover)
            
            # Bulk insert H3 covers
            db.bulk_save_objects(h3_covers)
            db.flush()  # Flush to get IDs if needed
            
            # Compacted version
            try:
                compacted_cells = list(h3.compact(all_cells))
                h3_compact = models.H3Compact(
                    owner_kind=owner_kind,
                    owner_id=owner_id,
                    resolution=resolution,
                    method=models.h3_cover.H3Method.COVERAGE,
                    cells_compact=compacted_cells
                )
                db.add(h3_compact)
                print(f"    Compacted to {len(compacted_cells)} cells")
            except Exception as e:
                print(f"    ⚠️  Warning: Could not compact H3 cells: {e}")
            
            # Commit H3 cells for this resolution
            db.commit()
            print(f"    ✓ Committed {len(all_cells)} H3 cells to database")
            
        except Exception as e:
            print(f"  ✗ Error generating H3 cover at resolution {resolution}: {e}")
            continue


def seed_service_areas(db: Session, use_ottawa_boundary: bool = True):
    """
    Seed service areas.
    
    Args:
        db: Database session
        use_ottawa_boundary: If True, creates Ottawa service area programmatically.
                           If False, reads from CSV (legacy).
    """
    print("\n📍 Seeding service areas...")
    
    # Check if service areas already exist
    existing_areas = db.query(models.ServiceArea).count()
    if existing_areas > 0:
        print(f"  ℹ️  Found {existing_areas} existing service areas")
        response = input("  Delete existing service areas and recreate? (y/N): ").strip().lower()
        if response == 'y':
            print("  🗑️  Deleting existing service areas and related data...")
            # Delete in order: zones → H3 covers → service areas
            from app.models.service_zone import ServiceZone
            from app.models.h3_cover import H3Cover
            from app.models.h3_compact import H3Compact
            
            zone_count = db.query(ServiceZone).delete()
            h3_cover_count = db.query(H3Cover).delete()
            h3_compact_count = db.query(H3Compact).delete()
            area_count = db.query(models.ServiceArea).delete()
            db.commit()
            print(f"     Deleted {zone_count} zones, {h3_cover_count} H3 covers, {h3_compact_count} H3 compacts, {area_count} service areas")
        else:
            print("  ⏭️  Skipping service area creation")
            return
    
    if use_ottawa_boundary:
        # Create Ottawa service area from CSV boundary
        print("  🏗️  Creating Ottawa service area from CSV boundary...")
        
        try:
            ottawa_geom = get_ottawa_boundary()
            
            if not ottawa_geom:
                print("  ✗ Failed to get Ottawa boundary")
                return
            
            # Get centroid for label cell
            centroid = ottawa_geom.centroid
            # Shapely centroid: (x, y) = (longitude, latitude)
            lng, lat = centroid.x, centroid.y
            # h3.geo_to_h3 expects (lat, lng)
            label_cell = h3.geo_to_h3(lat, lng, resolution=9)
            
            service_area = models.ServiceArea(
                name="Ottawa",
                description="Ottawa-Gatineau Metropolitan Area (from CSV)",
                boundary=from_shape(ottawa_geom, srid=4326),
                label_cell=label_cell,
                default_res=9,
                is_active=True
            )
            
            db.add(service_area)
            db.flush()
            
            print(f"  ✓ Created service area: Ottawa")
            print(f"    Boundary bounds: {ottawa_geom.bounds}")
            print(f"    Boundary area: {ottawa_geom.area:.6f} square degrees")
            print(f"    Label cell: {label_cell}")
            print(f"    Generating H3 coverage at resolutions {H3_RESOLUTIONS}...")
            print(f"    (Verifying coverage for each resolution)")
            
            # Generate H3 cells at multiple resolutions with coverage verification
            generate_h3_cover(
                db,
                owner_kind="service_area",
                owner_id=service_area.id,
                geom=ottawa_geom,
                resolutions=H3_RESOLUTIONS,
                verify_coverage=True
            )
            
            db.commit()
            print(f"  ✅ Ottawa service area created with H3 coverage")
            
        except Exception as e:
            print(f"  ✗ Error creating Ottawa service area: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            raise
    
    else:
        # Legacy: Read from CSV
        areas_data = read_service_areas_csv()
        
        if not areas_data:
            print("⚠ No service areas found in CSV")
            return
        
        for area_data in areas_data:
            try:
                geom = parse_geometry(area_data['boundary'])
                if not geom:
                    print(f"  ✗ Failed to parse geometry for '{area_data['name']}'")
                    continue
                
                service_area = models.ServiceArea(
                    name=area_data['name'],
                    description=area_data.get('description', ''),
                    boundary=from_shape(geom, srid=4326),
                    label_cell=get_h3_label_cell(geom, resolution=9),
                    default_res=9,
                    is_active=area_data.get('is_active', 'True').lower() == 'true'
                )
                
                db.add(service_area)
                db.flush()
                
                print(f"  ✓ Created service area: {area_data['name']}")
                print(f"    Generating H3 coverage at resolutions {H3_RESOLUTIONS}...")
                
                generate_h3_cover(
                    db,
                    owner_kind="service_area",
                    owner_id=service_area.id,
                    geom=geom,
                    resolutions=H3_RESOLUTIONS
                )
                
                db.commit()
                
            except Exception as e:
                print(f"  ✗ Error seeding service area '{area_data.get('name', 'unknown')}': {e}")
                db.rollback()
                continue


def get_geographic_direction(lat: float, lng: float, center_lat: float, center_lng: float) -> str:
    """Determine geographic direction from center point."""
    dlat = lat - center_lat
    dlng = lng - center_lng
    
    lat_threshold = 0.05
    lng_threshold = 0.05
    
    if abs(dlat) < lat_threshold and abs(dlng) < lng_threshold:
        return "Central"
    
    if abs(dlat) > abs(dlng) * 1.5:
        return "North" if dlat > 0 else "South"
    elif abs(dlng) > abs(dlat) * 1.5:
        return "East" if dlng > 0 else "West"
    else:
        ns = "North" if dlat > 0 else "South"
        ew = "East" if dlng > 0 else "West"
        return f"{ns}{ew}"


def h3_distance(cell1: str, cell2: str) -> int:
    """Calculate grid distance between two H3 cells."""
    try:
        return h3.h3_distance(cell1, cell2)
    except:
        lat1, lng1 = h3.h3_to_geo(cell1)
        lat2, lng2 = h3.h3_to_geo(cell2)
        return int(((lat1-lat2)**2 + (lng1-lng2)**2)**0.5 * 1000)


def generate_random_zones_h3(service_area_cells: Set[str], num_zones: int, service_area_polygon: Polygon = None) -> Dict[str, List[str]]:
    """Generate random service zones using H3-based Voronoi tessellation."""
    if not service_area_cells or num_zones < 1:
        return {}
    
    cells_list = list(service_area_cells)
    
    # If service area polygon provided, prefer seed cells that are clearly within the service area
    if service_area_polygon:
        # Filter cells to those with centers within service area for seed selection
        valid_seed_cells = []
        for cell in cells_list:
            try:
                lat, lng = h3.h3_to_geo(cell)
                point = Point(lng, lat)
                if service_area_polygon.contains(point) or service_area_polygon.touches(point):
                    valid_seed_cells.append(cell)
            except Exception:
                continue
        
        # Use valid cells for seeds if we have enough, otherwise use all cells
        if len(valid_seed_cells) >= num_zones:
            seed_pool = valid_seed_cells
        else:
            seed_pool = cells_list
    else:
        seed_pool = cells_list
    
    num_seeds = min(num_zones, len(seed_pool))
    seed_cells = random.sample(seed_pool, num_seeds)
    
    print(f"    Selected {num_seeds} random seed points for Voronoi tessellation")
    
    zone_assignments: Dict[str, List[str]] = {seed: [] for seed in seed_cells}
    
    for cell in cells_list:
        min_dist = float('inf')
        nearest_seed = seed_cells[0]
        
        for seed in seed_cells:
            dist = h3_distance(cell, seed)
            if dist < min_dist:
                min_dist = dist
                nearest_seed = seed
        
        zone_assignments[nearest_seed].append(cell)
    
    zone_assignments = {k: v for k, v in zone_assignments.items() if v}
    
    print(f"    Created {len(zone_assignments)} zones from tessellation")
    return zone_assignments


def h3_cells_to_polygon(cells: List[str]) -> Polygon:
    """Convert a list of H3 cells to a unified polygon geometry."""
    polygons = []
    
    for cell in cells:
        try:
            boundary = h3.h3_to_geo_boundary(cell, geo_json=True)
            poly = Polygon(boundary)
            if poly.is_valid:
                polygons.append(poly)
        except Exception:
            continue
    
    if not polygons:
        return None
    
    unified = unary_union(polygons)
    
    if hasattr(unified, 'simplify'):
        unified = unified.simplify(0.001, preserve_topology=True)
    
    return unified


def create_natural_service_zones_h3(db: Session, service_area_polygon: Polygon, num_zones: int = None) -> Dict[str, models.ServiceZone]:
    """
    Create natural service zones using H3-based Voronoi tessellation with smoothed boundaries.
    Zones are created to look like FSA boundaries (irregular, natural-looking).
    
    Args:
        db: Database session
        service_area_polygon: Service area polygon (Shapely Polygon)
        num_zones: Number of zones to create (auto-determined if None, 8-12 based on area)
    
    Returns:
        Dictionary mapping zone names to ServiceZone objects
    """
    print("\n🗺️  Creating natural service zones using H3 Voronoi tessellation...")
    
    service_areas = db.query(models.ServiceArea).filter(
        models.ServiceArea.is_active == True
    ).all()
    
    if not service_areas:
        print("✗ No service areas found. Please create service areas first.")
        return {}
    
    service_area = service_areas[0]  # Assume single Ottawa service area
    
    # Auto-determine number of zones based on service area size if not provided
    if num_zones is None:
        # Estimate based on area (roughly 1 zone per 0.03-0.04 square degrees for Ottawa)
        area = service_area_polygon.area
        if area < 0.1:
            num_zones = 6
        elif area < 0.2:
            num_zones = 8
        elif area < 0.3:
            num_zones = 10
        else:
            num_zones = 12
        print(f"  📊 Auto-determined {num_zones} zones based on service area size ({area:.3f} sq degrees)")
    else:
        print(f"  📊 Creating {num_zones} zones")
    
    # Get H3 cells covering the service area (use resolution 8 for zone generation)
    h3_resolution = 8
    print(f"  📍 Getting H3 cells at resolution {h3_resolution}...")
    service_area_cells = process_single_polygon_for_h3(service_area_polygon, h3_resolution, verbose=False)
    
    if not service_area_cells or len(service_area_cells) == 0:
        print("  ✗ Failed to get H3 cells for service area")
        return {}
    
    print(f"  ✓ Using {len(service_area_cells)} H3 cells for zone generation")
    
    # Use Voronoi tessellation to create spatially coherent zones
    # This groups nearby cells together, creating natural zone boundaries
    zone_assignments = generate_random_zones_h3(service_area_cells, num_zones, service_area_polygon)
    
    if not zone_assignments:
        print("  ✗ Failed to generate zones")
        return {}
    
    print(f"  ✓ Generated {len(zone_assignments)} zones from Voronoi tessellation")
    
    # Delete existing zones
    from app.models.service_zone import ServiceZone
    existing_zones = db.query(ServiceZone).filter(
        ServiceZone.service_area_id == service_area.id
    ).all()
    if existing_zones:
        print(f"  🗑️  Deleting {len(existing_zones)} existing zones...")
        for zone in existing_zones:
            # Delete H3 covers first
            from app.models.h3_cover import H3Cover
            from app.models.h3_compact import H3Compact
            db.query(H3Cover).filter(
                H3Cover.owner_kind == "service_zone",
                H3Cover.owner_id == zone.id
            ).delete()
            db.query(H3Compact).filter(
                H3Compact.owner_kind == "service_zone",
                H3Compact.owner_id == zone.id
            ).delete()
        db.query(ServiceZone).filter(
            ServiceZone.service_area_id == service_area.id
        ).delete()
        db.commit()
    
    created_zones = {}
    zone_index = 1
    
    # Convert each zone's H3 cells to polygon with smoothing
    for seed_cell, zone_cells in zone_assignments.items():
        try:
            if len(zone_cells) == 0:
                continue
            
            print(f"\n  📍 Creating zone {zone_index} ({len(zone_cells)} H3 cells)")
            
            # Create polygon from H3 cells
            zone_boundary = h3_cells_to_polygon(zone_cells)
            
            if not zone_boundary or zone_boundary.is_empty:
                print(f"    ⚠ Failed to create boundary for zone {zone_index}, skipping")
                continue
            
            # Ensure zone boundary is valid
            if not zone_boundary.is_valid:
                zone_boundary = zone_boundary.buffer(0)
            
            # Clip zone to service area polygon
            # Since cells come from polyfill, they should intersect, but clip to ensure clean boundaries
            if service_area_polygon:
                try:
                    clipped_boundary = service_area_polygon.intersection(zone_boundary)
                    
                    # If intersection is empty, try with small buffer (handles edge cases)
                    if clipped_boundary.is_empty:
                        buffered_service = service_area_polygon.buffer(0.001)
                        clipped_boundary = buffered_service.intersection(zone_boundary)
                        if clipped_boundary.is_empty:
                            # If still empty, use original boundary (cells from polyfill should be valid)
                            print(f"    ⚠ Zone {zone_index} intersection empty, using original boundary")
                            clipped_boundary = zone_boundary
                    
                    # Handle MultiPolygon - take largest part
                    if isinstance(clipped_boundary, MultiPolygon):
                        clipped_boundary = max(clipped_boundary.geoms, key=lambda p: p.area)
                    
                    zone_boundary = clipped_boundary
                except Exception as e:
                    print(f"    ⚠ Zone {zone_index} clipping error: {e}, using original boundary")
                    # Use original boundary if clipping fails
            
            # Smooth boundaries for FSA-like appearance
            zone_boundary = zone_boundary.simplify(0.001, preserve_topology=True)
            if not zone_boundary.is_valid:
                zone_boundary = zone_boundary.buffer(0)
            
            # Final validation - ensure zone has area
            if zone_boundary.is_empty or zone_boundary.area < 1e-10:
                print(f"    ⚠ Zone {zone_index} has no area, skipping")
                continue
            
            # Get centroid for label cell
            centroid = zone_boundary.centroid
            lng, lat = centroid.x, centroid.y
            
            # h3.geo_to_h3 expects (lat, lng)
            label_cell = h3.geo_to_h3(lat, lng, resolution=9)
            
            # Create service zone
            zone_name = f"Zone-{zone_index}"
            service_zone = models.ServiceZone(
                service_area_id=service_area.id,
                code=f"Z{zone_index:02d}",
                name=zone_name,
                boundary=from_shape(zone_boundary, srid=4326),
                label_cell=label_cell,
                default_res=9,
                is_active=True
            )
            
            db.add(service_zone)
            db.flush()
            
            print(f"    ✓ Created service zone: {zone_name}")
            print(f"      Boundary area: {zone_boundary.area:.6f} square degrees")
            print(f"      H3 cells: {len(zone_cells)}")
            print(f"      Generating H3 coverage at resolutions {H3_RESOLUTIONS}...")
            
            # Generate H3 coverage for the filled polygon
            generate_h3_cover(
                db,
                owner_kind="service_zone",
                owner_id=service_zone.id,
                geom=zone_boundary,
                resolutions=H3_RESOLUTIONS,
                verify_coverage=False
            )
            
            db.commit()
            created_zones[zone_name] = service_zone
            zone_index += 1

        except Exception as e:
            print(f"    ✗ Error creating zone {zone_index}: {e}")
            import traceback
            traceback.print_exc()
            db.rollback()
            continue
    
    print(f"\n  ✅ Successfully created {len(created_zones)} natural service zones")
    print(f"  📊 Service area is now divided into {len(created_zones)} zones")
    return created_zones


# ============================================================================
# PART 2: DEPOTS & ORDERS (Routing Data)
# ============================================================================

def select_depots_from_order_density(orders: List[Dict], num_depots: int = None) -> List[Dict]:
    """
    Strategically select depot positions based on order density using k-means clustering.
    Uses order locations (not zone centroids) to place depots where orders are concentrated.
    
    Args:
        orders: List of order dicts with 'latitude', 'longitude' keys
        num_depots: Number of depots to create (auto-determined if None, 3-5 based on order count)
    
    Returns:
        List of depot dicts with 'latitude', 'longitude', 'address' keys
    """
    from sklearn.cluster import KMeans
    import numpy as np
    
    if not orders or len(orders) == 0:
        print("  ⚠️  No orders provided, cannot select depots")
        return []
    
    # Auto-determine number of depots (3-5 based on order count)
    if num_depots is None:
        order_count = len(orders)
        if order_count <= 30:
            num_depots = 2
        elif order_count <= 60:
            num_depots = 3
        elif order_count <= 100:
            num_depots = 4
        else:
            num_depots = 5
    
    print(f"\n📍 Selecting {num_depots} depot positions from {len(orders)} orders...")
    print(f"   Based on order density (k-means clustering)")
    
    # Extract order coordinates
    order_coords = []
    for order in orders:
        lat = float(order['latitude'])
        lng = float(order['longitude'])
        order_coords.append([lat, lng])  # [latitude, longitude] for k-means
    
    if len(order_coords) < num_depots:
        print(f"  ⚠️  Only {len(order_coords)} orders, reducing depot count to {len(order_coords)}")
        num_depots = len(order_coords)
    
    # Run k-means clustering on order locations
    order_coords_array = np.array(order_coords)
    kmeans = KMeans(n_clusters=num_depots, random_state=42, n_init=10)
    kmeans.fit(order_coords_array)
    
    # Get cluster centers (optimal depot positions)
    depot_positions = kmeans.cluster_centers_
    print(f"  📊 Calculated {len(depot_positions)} optimal depot positions based on order density")
    
    # For each cluster center, find nearest actual order location as depot position
    selected_depots = []
    used_positions = set()
    
    for i, depot_pos in enumerate(depot_positions):
        depot_lat, depot_lng = float(depot_pos[0]), float(depot_pos[1])
        
        # Find nearest order location
        min_distance = float('inf')
        nearest_order = None
        
        for order in orders:
            order_lat = float(order['latitude'])
            order_lng = float(order['longitude'])
            
            # Skip if already used as depot
            pos_key = (order_lat, order_lng)
            if pos_key in used_positions:
                continue
            
            distance = haversine_distance(
                depot_lat, depot_lng,
                order_lat, order_lng
            )
            
            if distance < min_distance:
                min_distance = distance
                nearest_order = order
        
        if nearest_order:
            # Create depot dict from order location
            depot_dict = {
                'latitude': float(nearest_order['latitude']),
                'longitude': float(nearest_order['longitude']),
                'address': f"Depot Location #{i+1} - {nearest_order.get('address', 'Ottawa, ON')}"
            }
            selected_depots.append(depot_dict)
            used_positions.add((depot_dict['latitude'], depot_dict['longitude']))
            print(f"  ✓ Depot {i+1}: {depot_dict['address'][:60]}...")
            print(f"    Location: ({depot_dict['latitude']:.4f}, {depot_dict['longitude']:.4f})")
            print(f"    Distance from optimal: {min_distance:.2f} km")
        else:
            print(f"  ⚠️  Could not find order location for depot {i+1}")
    
    print(f"  ✅ Selected {len(selected_depots)} depot positions")
    return selected_depots


def extract_fsa_from_postal_code(postal_code: str) -> str:
    """Extract FSA (Forward Sortation Area) from postal code - first 3 characters."""
    if not postal_code:
        return None
    postal_code = postal_code.strip().upper().replace(' ', '')
    if len(postal_code) >= 3:
        return postal_code[:3]
    return None


def get_ottawa_service_area_polygon(db: Session) -> Polygon:
    """
    Get the Ottawa service area boundary polygon from the database.
    
    Args:
        db: Database session
    
    Returns:
        Shapely Polygon representing Ottawa's boundary, or None if not found
    """
    try:
        service_area = db.query(models.ServiceArea).filter(
            models.ServiceArea.name.ilike('%ottawa%'),
            models.ServiceArea.is_active == True
        ).first()
        
        if service_area and service_area.boundary:
            from geoalchemy2.shape import to_shape
            geom = to_shape(service_area.boundary)
            if geom and isinstance(geom, (Polygon, MultiPolygon)):
                # If MultiPolygon, get the largest polygon
                if isinstance(geom, MultiPolygon):
                    largest = max(geom.geoms, key=lambda p: p.area)
                    return largest
                return geom
    except Exception as e:
        print(f"  ⚠️  Error getting service area polygon: {e}")
    
    # Fallback to approximate bounding box
    print("  ⚠️  Using approximate bounding box (service area not found in DB)")
    ottawa_bbox = [
        (-76.2, 45.15),  # Southwest corner (lng, lat)
        (-75.3, 45.15),  # Southeast corner
        (-75.3, 45.55),  # Northeast corner
        (-76.2, 45.55),  # Northwest corner
        (-76.2, 45.15)   # Close polygon
    ]
    return Polygon(ottawa_bbox)


def is_point_in_service_area(latitude: float, longitude: float, service_area_polygon: Polygon, use_buffer: bool = True) -> bool:
    """
    Check if a point (latitude, longitude) is within the service area polygon.
    Optionally uses a small buffer to include addresses near the boundary.
    
    Args:
        latitude: Point latitude
        longitude: Point longitude
        service_area_polygon: Shapely Polygon (coordinates as (lng, lat))
        use_buffer: If True, uses a small buffer (~1km) to include nearby addresses
    
    Returns:
        True if point is within polygon (or buffer), False otherwise
    """
    if not service_area_polygon:
        return True  # If no polygon, allow all points
    
    # Shapely uses (x, y) = (longitude, latitude)
    point = Point(longitude, latitude)
    
    if use_buffer:
        # Add a small buffer (~1km, approximately 0.01 degrees at Ottawa latitude)
        buffered_polygon = service_area_polygon.buffer(0.01)
        return buffered_polygon.contains(point) or buffered_polygon.touches(point)
    else:
        return service_area_polygon.contains(point) or service_area_polygon.touches(point)


def seed_depots_from_addresses(db: Session, depot_addresses: List[Dict]) -> List:
    """
    Create depot records from selected addresses.
    
    Args:
        db: Database session
        depot_addresses: List of address dicts to use as depots
    
    Returns:
        List of created depot instances
    """
    print("\n🏭 Seeding depots from selected addresses...")
    
    # Check if depots already exist
    existing = crud.depot.get_multi(db=db, limit=100)
    if existing:
        print(f"  ℹ️  Found {len(existing)} existing depots")
        print(f"  🗑️  Deleting existing data...")
        
        # Delete dependencies first to avoid foreign key constraints
        from app.models.zone_depot_assignment import ZoneDepotAssignment
        from app.models.order import Order
        from app.models.depot import Depot
        
        # Delete in order: orders → zone assignments → depots
        order_count = db.query(Order).delete()
        assignment_count = db.query(ZoneDepotAssignment).delete()
        depot_count = db.query(Depot).delete()
        
        db.commit()
        
        print(f"     Deleted {order_count} orders, {assignment_count} zone assignments, {depot_count} depots")
    
    if not depot_addresses:
        print("  ⚠️  No depot addresses provided")
        return []
    
    print(f"\n  🏗️  Creating {len(depot_addresses)} depots from addresses...")
    created_depots = []
    
    for idx, addr in enumerate(depot_addresses, 1):
        try:
            depot_data = {
                "name": f"Ottawa Depot #{idx}",
                "address": addr['address'],
                "latitude": addr['latitude'],
                "longitude": addr['longitude'],
                "available_drivers": 10,  # Will be recalculated later
                "contact_info": f"depot{idx}@ezgo.com"
            }
            
            # DEBUG: Verify coordinates before storing
            print(f"  🔍 DEBUG Depot {idx}: lat={addr['latitude']:.6f}, lng={addr['longitude']:.6f}")
            
            depot_create = schemas.DepotCreate(**depot_data)
            depot = crud.depot.create(db=db, obj_in=depot_create)
            created_depots.append(depot)
            print(f"  ✓ Created: {depot.name}")
            print(f"    📍 {addr['address'][:60]}...")
            print(f"    Location: ({depot.latitude:.4f}, {depot.longitude:.4f})")
            
            # DEBUG: Verify stored coordinates
            if abs(depot.latitude - addr['latitude']) > 0.0001 or abs(depot.longitude - addr['longitude']) > 0.0001:
                print(f"    ⚠️  WARNING: Coordinate mismatch! Stored: ({depot.latitude:.6f}, {depot.longitude:.6f}) vs Expected: ({addr['latitude']:.6f}, {addr['longitude']:.6f})")
    
        except Exception as e:
            print(f"  ✗ Failed to create depot from address: {e}")
            continue
    
    print(f"  ✅ Created {len(created_depots)} depots")
    return created_depots


def assign_zones_to_depots(db: Session, depots: list):
    """
    Assign service zones to nearest depot (strict territories).
    Each zone is assigned to exactly one depot based on proximity.
    Zones farther than MAX_DEPOT_RADIUS_KM are flagged as warnings.
    """
    print("\n🔗 Assigning zones to nearest depot (strict territories)...")
    
    zones = crud.service_zone.get_multi(db=db, limit=100)
    
    if not zones:
        print("  ⚠️  No service zones found.")
        return {}
    
    if not depots:
        print("  ⚠️  No depots found.")
        return {}
    
    from app.models.zone_depot_assignment import ZoneDepotAssignment
    
    # Clear existing assignments for fresh start
    existing_count = db.query(ZoneDepotAssignment).count()
    if existing_count > 0:
        print(f"  🗑️  Deleting {existing_count} existing zone assignments...")
        db.query(ZoneDepotAssignment).delete()
        db.commit()
    
    print(f"  📊 Assigning {len(zones)} zones to {len(depots)} depots...")
    print(f"  📏 Maximum service radius: {MAX_DEPOT_RADIUS_KM} km")
    
    assignments_created = 0
    zones_per_depot = {depot.id: [] for depot in depots}
    out_of_range_zones = []
    
    for zone in zones:
        zone_lat, zone_lng = get_zone_centroid(zone)
        
        # Find nearest depot
        min_distance = float('inf')
        nearest_depot = None
        
        for depot in depots:
            distance = haversine_distance(
                zone_lat, zone_lng,
                depot.latitude, depot.longitude
            )
            
            if distance < min_distance:
                min_distance = distance
                nearest_depot = depot
        
        if nearest_depot:
            # Create assignment to nearest depot
            try:
                assignment = schemas.ZoneDepotAssignmentCreate(
                    zone_id=zone.id,
                    depot_id=nearest_depot.id,
                    is_primary=True,
                    priority=1
                )
                crud.zone_depot_assignment.create(db=db, obj_in=assignment)
                assignments_created += 1
                zones_per_depot[nearest_depot.id].append(zone)
                
                # Flag if distance exceeds recommended radius
                status = "✓" if min_distance <= MAX_DEPOT_RADIUS_KM else "⚠️"
                print(f"  {status} {zone.name:20s} → {nearest_depot.name:25s} ({min_distance:5.1f} km)")
                
                if min_distance > MAX_DEPOT_RADIUS_KM:
                    out_of_range_zones.append({
                        'zone': zone.name,
                        'depot': nearest_depot.name,
                        'distance': min_distance
                    })
                    
            except Exception as e:
                print(f"  ✗ Failed to assign {zone.name}: {e}")
    
    # Print summary
    print(f"\n  📊 Assignment Summary:")
    print(f"  Total assignments: {assignments_created}/{len(zones)}")
    
    for depot in depots:
        zone_count = len(zones_per_depot[depot.id])
        if zone_count > 0:
            zone_names = [z.name for z in zones_per_depot[depot.id][:3]]
            zone_preview = ", ".join(zone_names)
            if zone_count > 3:
                zone_preview += f", ... (+{zone_count - 3} more)"
            print(f"\n  🏭 {depot.name}:")
            print(f"     Zones: {zone_count}")
            print(f"     {zone_preview}")
    
    if out_of_range_zones:
        print(f"\n  ⚠️  {len(out_of_range_zones)} zone(s) exceed {MAX_DEPOT_RADIUS_KM}km radius:")
        for item in out_of_range_zones[:5]:
            print(f"     {item['zone']} → {item['depot']} ({item['distance']:.1f} km)")
        if len(out_of_range_zones) > 5:
            print(f"     ... and {len(out_of_range_zones) - 5} more")
    
    return zones_per_depot


def calculate_orders_per_depot(zones_per_depot: Dict, total_orders: int = 100) -> Dict:
    """
    Calculate how many orders and drivers each depot should have based on zone assignments.
    
    Args:
        zones_per_depot: Dictionary mapping depot_id to list of zones
        total_orders: Target total number of orders (default: 100)
    
    Returns:
        Dictionary with depot_id -> {orders, drivers, zones}
    """
    from math import ceil
    
    print(f"\n📊 Calculating order distribution for {total_orders} total orders...")
    
    depot_config = {}
    total_zones = sum(len(zones) for zones in zones_per_depot.values())
    
    if total_zones == 0:
        print("  ⚠️  No zones assigned, cannot calculate distribution")
        return {}
    
    # Distribute orders proportionally to number of zones
    for depot_id, zones in zones_per_depot.items():
        if len(zones) == 0:
            depot_config[depot_id] = {'orders': 0, 'drivers': 0, 'zones': 0}
            continue
        
        # Proportional order allocation
        zone_ratio = len(zones) / total_zones
        orders_for_depot = int(total_orders * zone_ratio)
        
        # Calculate required drivers (targeting 10-20 orders per driver)
        drivers_needed = max(1, ceil(orders_for_depot / TARGET_ORDERS_PER_DRIVER))
        
        depot_config[depot_id] = {
            'orders': orders_for_depot,
            'drivers': drivers_needed,
            'zones': len(zones),
            'orders_per_driver': orders_for_depot / drivers_needed if drivers_needed > 0 else 0
        }
    
    # Print distribution
    print(f"\n  📋 Depot Configuration:")
    for depot_id, config in depot_config.items():
        if config['orders'] > 0:
            print(f"     Depot {str(depot_id)[:8]}...")
            print(f"       Zones: {config['zones']}")
            print(f"       Orders: {config['orders']}")
            print(f"       Drivers: {config['drivers']}")
            print(f"       Orders/Driver: {config['orders_per_driver']:.1f}")
    
    return depot_config


def generate_orders_in_zones(db: Session, zones: List[models.ServiceZone], total_orders: int = 100, service_area_polygon: Polygon = None) -> List[Dict]:
    """
    Generate orders as random points within zone bounding boxes.
    Points are filtered to be inside zone boundaries and service area polygon.
    
    Args:
        db: Database session
        zones: List of ServiceZone objects
        total_orders: Total number of orders to generate (default: 100)
        service_area_polygon: Service area polygon for validation (optional)
    
    Returns:
        List of order dicts with 'latitude', 'longitude', 'zone_id', 'address' keys
    """
    from sqlalchemy import text
    from geoalchemy2.shape import to_shape
    
    print(f"\n📦 Generating {total_orders} orders within {len(zones)} zones...")
    
    if not zones:
        print("  ⚠️  No zones provided")
        return []
    
    # Distribute orders across zones proportionally by area
    zone_areas = []
    for zone in zones:
        try:
            geom = to_shape(zone.boundary)
            if geom:
                area = geom.area
                zone_areas.append((zone, area))
        except Exception:
            zone_areas.append((zone, 1.0))  # Default area if can't calculate
    
    total_area = sum(area for _, area in zone_areas)
    if total_area == 0:
        # Fallback: distribute evenly
        orders_per_zone = max(1, total_orders // len(zones))
        zone_orders = {zone.id: orders_per_zone for zone, _ in zone_areas}
        remaining = total_orders - sum(zone_orders.values())
        # Distribute remaining
        for i, (zone, _) in enumerate(zone_areas):
            if remaining <= 0:
                break
            zone_orders[zone.id] += 1
            remaining -= 1
    else:
        # Distribute proportionally
        zone_orders = {}
        remaining = total_orders
        for zone, area in zone_areas:
            proportion = area / total_area
            orders_for_zone = max(1, int(total_orders * proportion))
            zone_orders[zone.id] = min(orders_for_zone, remaining)
            remaining -= zone_orders[zone.id]
        # Distribute any remaining orders
        for i, (zone, _) in enumerate(zone_areas):
            if remaining <= 0:
                break
            zone_orders[zone.id] += 1
            remaining -= 1
    
    print(f"  📊 Order distribution:")
    for zone, area in zone_areas:
        print(f"     {zone.name}: {zone_orders.get(zone.id, 0)} orders")
    
    all_orders = []
    order_counter = 1
    
    # Generate orders for each zone
    for zone, _ in zone_areas:
        orders_needed = zone_orders.get(zone.id, 0)
        if orders_needed == 0:
            continue
        
        # Validate zone has a boundary
        if not zone.boundary:
            print(f"    ⚠️  Zone {zone.name} has no boundary, skipping")
            continue
        
        print(f"\n  📍 Generating {orders_needed} orders in {zone.name}...")
        
        # Generate random points within zone using Python + Shapely (more reliable)
        try:
            from geoalchemy2.shape import to_shape
            import random
            from shapely.geometry import Point
            
            # Get zone boundary as Shapely polygon
            zone_polygon = to_shape(zone.boundary)
            if not zone_polygon or zone_polygon.is_empty:
                print(f"    ⚠️  Zone {zone.name} has invalid boundary, skipping")
                continue
            
            # Handle MultiPolygon - take largest part
            if hasattr(zone_polygon, 'geoms'):
                zone_polygon = max(zone_polygon.geoms, key=lambda p: p.area)
            
            # Ensure polygon is valid
            if not zone_polygon.is_valid:
                zone_polygon = zone_polygon.buffer(0)
            
            if zone_polygon.is_empty:
                print(f"    ⚠️  Zone {zone.name} has empty polygon after validation, skipping")
                continue
            
            # Get bounding box
            # Shapely bounds returns (minx, miny, maxx, maxy) = (min_lng, min_lat, max_lng, max_lat)
            # Shapely uses (x, y) = (longitude, latitude)
            minx, miny, maxx, maxy = zone_polygon.bounds
            min_lng, min_lat, max_lng, max_lat = minx, miny, maxx, maxy
            
            # Debug: Check polygon area
            area = zone_polygon.area
            if area < 1e-10:
                print(f"    ⚠️  Zone {zone.name} has very small area ({area:.2e}), skipping")
                continue
            
            # Use representative point (centroid) as fallback if random generation fails
            centroid = zone_polygon.representative_point()
            centroid_lng, centroid_lat = centroid.x, centroid.y
            
            # Generate random points within bounding box and filter to zone
            generated_count = 0
            max_attempts = orders_needed * 500  # Try many more times
            attempts = 0
            contained_count = 0  # Debug: count points that are in polygon
            coord_filtered = 0  # Debug: count filtered by coordinate validation
            service_filtered = 0  # Debug: count filtered by service area
            sample_points = []  # Debug: store first few points for analysis
            
            # Debug: Print zone info
            print(f"    🔍 Debug - Zone bounds: lng({min_lng:.6f} to {max_lng:.6f}), lat({min_lat:.6f} to {max_lat:.6f})")
            print(f"    🔍 Debug - Centroid: ({centroid_lng:.6f}, {centroid_lat:.6f})")
            
            while generated_count < orders_needed and attempts < max_attempts:
                attempts += 1
                
                # Generate random point in bounding box
                # Shapely: x = longitude, y = latitude
                longitude = min_lng + random.random() * (max_lng - min_lng)
                latitude = min_lat + random.random() * (max_lat - min_lat)
                
                # Check if point is in zone polygon
                point = Point(longitude, latitude)
                
                if not zone_polygon.contains(point):
                    # Debug: Store first few points that are NOT in polygon
                    if len(sample_points) < 3 and attempts < 10:
                        sample_points.append((longitude, latitude, "not_in_polygon"))
                    continue
                
                contained_count += 1
                
                # Debug: Store first few points that ARE in polygon
                if len(sample_points) < 5:
                    sample_points.append((longitude, latitude, "in_polygon"))
                
                # Zones are already validated and clipped to service area
                # Points inside zones are valid - no additional coordinate validation needed
                
                # Generate address string
                address = f"{zone.name} - Delivery Point #{order_counter}"
                
                # Validation: Ottawa should have positive latitude (45°N) and negative longitude (-75°W)
                if latitude < 0 or latitude > 90:
                    print(f"    ⚠️  WARNING: Invalid latitude {latitude:.6f} for Ottawa! Expected 40-50°N")
                    print(f"       Point: ({latitude:.6f}, {longitude:.6f})")
                if longitude > 0 or longitude < -90:
                    print(f"    ⚠️  WARNING: Invalid longitude {longitude:.6f} for Ottawa! Expected -80 to -70°W")
                    print(f"       Point: ({latitude:.6f}, {longitude:.6f})")
                
                order_data = {
                    'latitude': latitude,
                    'longitude': longitude,
                    'zone_id': zone.id,
                    'address': address,
                    'order_number': order_counter
                }
                
                all_orders.append(order_data)
                generated_count += 1
                order_counter += 1
                
                # Debug: Print first successful point
                if generated_count == 1:
                    print(f"    🔍 Debug - First order point: lat={latitude:.6f}, lng={longitude:.6f}")
            
            # If we didn't get enough, try using centroid as fallback
            if generated_count < orders_needed:
                remaining = orders_needed - generated_count
                # Use centroid for remaining orders (at least we'll have some orders)
                for i in range(min(remaining, 3)):  # Max 3 fallback orders per zone
                    # Basic sanity check only
                    if 40.0 <= centroid_lat <= 50.0 and -80.0 <= centroid_lng <= -70.0:
                        address = f"{zone.name} - Delivery Point #{order_counter}"
                        order_data = {
                            'latitude': centroid_lat,
                            'longitude': centroid_lng,
                            'zone_id': zone.id,
                            'address': address,
                            'order_number': order_counter
                        }
                        all_orders.append(order_data)
                        generated_count += 1
                        order_counter += 1
            
            if generated_count < orders_needed:
                print(f"    ⚠️  Only generated {generated_count}/{orders_needed} orders")
                print(f"       Attempts: {attempts}, In polygon: {contained_count}, Coord filtered: {coord_filtered}, Service filtered: {service_filtered}")
                print(f"       Bounds: lng({min_lng:.6f} to {max_lng:.6f}), lat({min_lat:.6f} to {max_lat:.6f}), Area: {area:.6f}")
                if sample_points:
                    print(f"       Sample points (first {len(sample_points)}):")
                    for i, (lng, lat, status) in enumerate(sample_points[:5], 1):
                        in_poly = zone_polygon.contains(Point(lng, lat))
                        print(f"         {i}. ({lat:.6f}, {lng:.6f}) - {status}, contains={in_poly}")
                if contained_count > 0 and generated_count == 0:
                    print(f"       ⚠️  {contained_count} points were in polygon but none were accepted - check validation logic!")
            else:
                print(f"    ✓ Generated {generated_count} orders")
        
        except Exception as e:
            print(f"    ✗ Error generating orders for {zone.name}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n  ✅ Generated {len(all_orders)} total orders across {len(zones)} zones")
    return all_orders


def update_depot_driver_counts(db: Session, depots: list, depot_config: Dict):
    """
    Legacy function - kept for compatibility but should use seed_orders_from_addresses instead.
    Create sample orders for a specific date by generating random points within service zones.
    Orders are distributed per depot based on their assigned zones and calculated order counts.
    
    Args:
        db: Database session
        depots: List of depot instances
        zones_per_depot: Mapping of depot_id to zones
        depot_config: Configuration with order counts per depot
        delivery_date: Date for order delivery (defaults to yesterday for testing)
    """
    from app.services.h3_service import H3Service
    from app.models import ServiceZone
    from app.models.order import Order
    from sqlalchemy import func, text
    from datetime import timedelta
    
    # Default to today's date
    if delivery_date is None:
        delivery_date = date.today()
    
    total_orders = sum(config['orders'] for config in depot_config.values())
    print(f"\n📦 Seeding {total_orders} orders for {delivery_date}...")
    
    # Rollback any pending transaction
    try:
        db.rollback()
    except:
        pass
    
    # Delete existing orders
    deleted_count = db.query(Order).delete()
    db.commit()
    if deleted_count > 0:
        print(f"  🗑️  Deleted {deleted_count} existing orders")
    
    all_created_orders = []
    
    # Generate orders for each depot
    for depot in depots:
        depot_id = depot.id
        config = depot_config.get(depot_id, {})
        
        if config.get('orders', 0) == 0:
            print(f"\n  ⏭️  Skipping {depot.name} (no orders allocated)")
            continue
        
        target_orders = config['orders']
        zones = zones_per_depot.get(depot_id, [])
        
        print(f"\n  🏭 {depot.name}")
        print(f"     Target orders: {target_orders}")
        print(f"     Zones: {len(zones)}")
        
        if not zones:
            print(f"     ⚠️  No zones assigned, skipping")
            continue
        
        # Generate points distributed across this depot's zones
        addresses_with_coords = []
        
        # VALIDATION: Verify all zones are assigned to this depot before processing
        from app.models.zone_depot_assignment import ZoneDepotAssignment
        validated_zones = []
        for zone in zones:
            zone_assignment = db.query(ZoneDepotAssignment).filter(
                ZoneDepotAssignment.zone_id == zone.id,
                ZoneDepotAssignment.is_primary == True
            ).first()
            
            if zone_assignment and zone_assignment.depot_id == depot_id:
                validated_zones.append(zone)
            else:
                print(f"     ⚠️  Zone {zone.name} is not assigned to {depot.name}, excluding from order generation")
        
        if not validated_zones:
            print(f"     ⚠️  No valid zones assigned to {depot.name}, skipping")
            continue
        
        print(f"     ✓ Validated {len(validated_zones)} zones assigned to {depot.name}")
        orders_per_zone = max(1, target_orders // len(validated_zones))
        
        for zone in validated_zones:
            
            # Generate random points within this zone's boundary using PostGIS
            points_needed = min(orders_per_zone, target_orders - len(addresses_with_coords))
            
            if points_needed <= 0:
                break
            
            # Generate random points WITHIN the zone boundary (not on the boundary)
            # Try multiple strategies to ensure points are inside
            result = db.execute(
                text("""
                    WITH zone_geom AS (
                        SELECT boundary FROM service_zones WHERE id = :zone_id
                    ),
                    buffered_geom AS (
                        SELECT 
                            CASE 
                                WHEN ST_Area(boundary) > 0.0001 THEN 
                                    ST_Buffer(boundary, -0.0001)  -- Small negative buffer
                                ELSE boundary
                            END as geom
                        FROM zone_geom
                    ),
                    random_points AS (
                        SELECT 
                            ST_GeneratePoints(geom, :num_points * 2) as points
                        FROM buffered_geom
                        WHERE geom IS NOT NULL AND ST_Area(geom) > 0
                    )
                    SELECT
                        ST_X((ST_Dump(points)).geom) as latitude,
                        ST_Y((ST_Dump(points)).geom) as longitude
                    FROM random_points
                    LIMIT :num_points
                """),
                {'zone_id': str(zone.id), 'num_points': points_needed}
            ).fetchall()
            
            # Fallback: If no points generated, use random sampling within bounding box
            if not result or len(result) == 0:
                result = db.execute(
                    text("""
                        WITH zone_geom AS (
                            SELECT boundary FROM service_zones WHERE id = :zone_id
                        ),
                        bbox AS (
                            SELECT 
                                ST_XMin(boundary) as minx,
                                ST_YMin(boundary) as miny,
                                ST_XMax(boundary) as maxx,
                                ST_YMax(boundary) as maxy
                            FROM zone_geom
                        ),
                        random_points AS (
                            SELECT 
                                ST_MakePoint(
                                    minx + random() * (maxx - minx),
                                    miny + random() * (maxy - miny)
                                ) as geom
                            FROM bbox,
                            generate_series(1, :num_points * 10)
                        )
                        SELECT
                            ST_X(geom) as latitude,
                            ST_Y(geom) as longitude
                        FROM random_points, zone_geom
                        WHERE ST_Contains(zone_geom.boundary, geom)
                        LIMIT :num_points
                    """),
                    {'zone_id': str(zone.id), 'num_points': points_needed}
                ).fetchall()
            
            for row in result:
                # PostGIS ST_X returns X coordinate, ST_Y returns Y coordinate
                # However, the geometry appears to be stored with swapped coordinates
                # Based on database inspection: ST_X returns latitude, ST_Y returns longitude
                # So we need to swap: row[0] = latitude, row[1] = longitude
                latitude = float(row[0])   # ST_X = latitude (swapped in geometry)
                longitude = float(row[1])  # ST_Y = longitude (swapped in geometry)
                
                # Validate coordinates are in Ottawa range
                if not (44.0 <= latitude <= 46.0) or not (-77.0 <= longitude <= -75.0):
                    print(f"      ⚠️  Generated point outside Ottawa range: lat={latitude:.4f}, lng={longitude:.4f}")
                    continue
                
                addresses_with_coords.append({
                    'latitude': latitude,
                    'longitude': longitude,
                    'address': f"{zone.name} - Address #{len(addresses_with_coords) + 1}",
                    'zone_id': zone.id,
                    'depot_id': depot_id
                })
        
        print(f"     ✅ Generated {len(addresses_with_coords)} delivery locations")
        
        # Create orders for this depot
        created = 0
        failed = 0
        order_counter = len(all_created_orders) + 1
        
        for addr_data in addresses_with_coords:
            order_number = f"ORD-{delivery_date.strftime('%Y%m%d')}-{order_counter:04d}"
            customer_name = f"Customer {order_counter}"
            
            address = addr_data['address']
            latitude = float(addr_data['latitude'])
            longitude = float(addr_data['longitude'])
            zone_id = addr_data['zone_id']
            depot_id = addr_data['depot_id']
            
            # Final validation before creating order
            if not (44.0 <= latitude <= 46.0) or not (-77.0 <= longitude <= -75.0):
                print(f"     ⚠️  Skipping order with invalid coordinates: lat={latitude}, lng={longitude}")
                continue
            
            try:
                # VALIDATION: Double-check that zone is assigned to this depot (safety check)
                # This should already be validated above, but we check again for safety
                zone_assignment = db.query(ZoneDepotAssignment).filter(
                    ZoneDepotAssignment.zone_id == zone_id,
                    ZoneDepotAssignment.is_primary == True
                ).first()
                
                if not zone_assignment:
                    print(f"     ⚠️  Zone {zone_id} has no depot assignment, skipping order")
                    continue
                
                if zone_assignment.depot_id != depot_id:
                    print(f"     ⚠️  Zone {zone_id} is assigned to different depot ({zone_assignment.depot_id}), correcting to {depot_id}")
                    # Use the correct depot_id from the assignment
                    depot_id = zone_assignment.depot_id
                
                # Get H3 index (H3Service expects lat, lng)
                h3_index = H3Service.lat_lng_to_h3(latitude, longitude)
                
                # DEBUG: Verify coordinates before storing
                if order_counter <= 3:
                    print(f"     🔍 DEBUG Order {order_counter}: lat={latitude:.6f}, lng={longitude:.6f}")
                    print(f"        Address: {address[:50]}")
                
                # Order has zone and depot, so status is "geocoded"
                order_status = "geocoded"
                
                order = Order(
                    order_number=order_number,
                    customer_name=customer_name,
                    customer_contact=f"customer{order_counter}@example.com",
                    delivery_address=address,
                    latitude=latitude,
                    longitude=longitude,
                    h3_index=h3_index,
                    zone_id=zone_id,
                    depot_id=depot_id,  # Ensured to match zone's assigned depot
                    order_date=delivery_date,
                    scheduled_delivery_date=delivery_date,
                    status=order_status,
                    weight_kg=round(5.0 + (order_counter % 20), 2),
                    volume_m3=round(0.1 + (order_counter % 5) * 0.05, 2)
                )
                
                db.add(order)
                db.commit()
                
                all_created_orders.append(order)
                created += 1
                order_counter += 1
                
            except Exception as e:
                failed += 1
                print(f"     ✗ Failed to create order: {e}")
                db.rollback()
        
        print(f"     ✓ Created: {created} orders")
        if failed > 0:
            print(f"     ✗ Failed: {failed} orders")

def validate_depot_configuration(db: Session, depots: list, zones_per_depot: Dict):
    """
    Validate that depot service areas meet realistic constraints.
    
    Args:
        db: Database session
        depots: List of depot instances
        zones_per_depot: Dictionary mapping depot_id to list of zones
    
    Returns:
        True if validation passes, False otherwise
    """
    from app.models.order import Order
    
    print(f"\n✅ Validating depot configuration...")
    
    validation_passed = True
    
    for depot in depots:
        zones = zones_per_depot.get(depot.id, [])
        
        if not zones:
            print(f"\n  ⚠️  {depot.name}: No zones assigned")
            continue
        
        print(f"\n  🏭 {depot.name}:")
        
        # Check zone distances
        max_distance = 0
        avg_distance = 0
        for zone in zones:
            zone_lat, zone_lng = get_zone_centroid(zone)
            distance = haversine_distance(
                depot.latitude, depot.longitude,
                zone_lat, zone_lng
            )
            max_distance = max(max_distance, distance)
            avg_distance += distance
        
        if len(zones) > 0:
            avg_distance /= len(zones)
        
        # Validate service radius
        radius_ok = max_distance <= MAX_DEPOT_RADIUS_KM
        status = "✓" if radius_ok else "⚠️"
        print(f"     {status} Service radius: {max_distance:.1f} km (max), {avg_distance:.1f} km (avg)")
        
        if not radius_ok:
            print(f"        WARNING: Exceeds recommended {MAX_DEPOT_RADIUS_KM} km")
            validation_passed = False
        
        # Check order distribution
        order_count = db.query(Order).filter(Order.depot_id == depot.id).count()
        print(f"     ✓ Orders: {order_count}")
        print(f"     ✓ Drivers: {depot.available_drivers}")
        
        if order_count > 0 and depot.available_drivers > 0:
            orders_per_driver = order_count / depot.available_drivers
            orders_ok = MIN_ORDERS_PER_DRIVER <= orders_per_driver <= MAX_ORDERS_PER_DRIVER
            status = "✓" if orders_ok else "⚠️"
            print(f"     {status} Orders/Driver: {orders_per_driver:.1f} (target: {MIN_ORDERS_PER_DRIVER}-{MAX_ORDERS_PER_DRIVER})")
            
            if not orders_ok:
                print(f"        WARNING: Outside recommended range")
    
    if validation_passed:
        print(f"\n  ✅ All validations passed!")
    else:
        print(f"\n  ⚠️  Some validations failed (see warnings above)")
    
    return validation_passed


def verify_zone_depot_consistency(db: Session):
    """
    Verify that all orders have depot_id matching their zone's assigned depot.
    This ensures strict zone-depot territory enforcement.
    """
    from app.models.order import Order
    from app.models.zone_depot_assignment import ZoneDepotAssignment
    
    print("\n🔍 Verifying zone-depot consistency for all orders...")
    
    # Get all orders with zones
    orders = db.query(Order).filter(Order.zone_id.isnot(None)).all()
    
    if not orders:
        print("  ℹ️  No orders with zones found")
        return
    
    inconsistent_count = 0
    consistent_count = 0
    
    for order in orders:
        if not order.depot_id:
            inconsistent_count += 1
            print(f"  ⚠️  Order {order.order_number} has zone {order.zone_id} but no depot_id")
            continue
        
        # Get zone's assigned depot
        zone_assignment = db.query(ZoneDepotAssignment).filter(
            ZoneDepotAssignment.zone_id == order.zone_id,
            ZoneDepotAssignment.is_primary == True
        ).first()
        
        if not zone_assignment:
            inconsistent_count += 1
            print(f"  ⚠️  Order {order.order_number} has zone {order.zone_id} but zone has no depot assignment")
            continue
        
        if zone_assignment.depot_id != order.depot_id:
            inconsistent_count += 1
            print(f"  ❌ Order {order.order_number}: zone {order.zone_id} assigned to depot {zone_assignment.depot_id}, but order has depot {order.depot_id}")
            # Fix it
            order.depot_id = zone_assignment.depot_id
            db.add(order)
        else:
            consistent_count += 1
    
    if inconsistent_count > 0:
        db.commit()
        print(f"  ✅ Fixed {inconsistent_count} inconsistent orders")
    else:
        print(f"  ✅ All {consistent_count} orders are consistent with zone-depot assignments")


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main unified seeding function using natural H3-based zones and order density-based depots."""
    print("=" * 80)
    print("🌱 NATURAL SERVICE ZONES WITH ORDER-BASED DEPOT PLACEMENT")
    print("=" * 80)
    
    db = SessionLocal()
    
    try:
        # Step 1: Create Ottawa service area first (needed for validation)
        print("\n" + "=" * 80)
        print("STEP 1: Create Ottawa Service Area")
        print("=" * 80)
        
        seed_service_areas(db, use_ottawa_boundary=True)
        
        # Get service area polygon for validation
        service_area_polygon = get_ottawa_service_area_polygon(db)
        if service_area_polygon:
            print(f"  ✓ Using service area polygon for validation")
        else:
            print(f"  ⚠️  Using approximate bounding box for validation")
        
        # Step 2: Create natural service zones using H3 Voronoi tessellation
        print("\n" + "=" * 80)
        print("STEP 2: Create Natural Service Zones (H3 Voronoi Tessellation)")
        print("=" * 80)
        
        zones_dict = create_natural_service_zones_h3(db, service_area_polygon, num_zones=None)
        if not zones_dict:
            print("❌ Failed to create service zones. Exiting.")
            return
        
        # Convert dict to list for easier iteration
        zones = list(zones_dict.values())
        print(f"  ✅ Created {len(zones)} natural service zones")
        
        # Step 3: Generate 100 orders within zone bounding boxes
        print("\n" + "=" * 80)
        print("STEP 3: Generate Orders Within Zones")
        print("=" * 80)
        
        order_data = generate_orders_in_zones(db, zones, total_orders=TOTAL_ORDERS, service_area_polygon=service_area_polygon)
        if not order_data or len(order_data) < 10:
            print("❌ Failed to generate sufficient orders. Exiting.")
            return
        
        print(f"  ✅ Generated {len(order_data)} orders")
        
        # Step 4: Place depots based on order density
        print("\n" + "=" * 80)
        print("STEP 4: Place Depots Based on Order Density")
        print("=" * 80)
        
        depot_data = select_depots_from_order_density(order_data, num_depots=None)
        if not depot_data:
            print("❌ Failed to select depot positions. Exiting.")
            return
        
        print(f"  ✅ Selected {len(depot_data)} depot positions")
        
        # Step 5: Create depots from selected positions
        print("\n" + "=" * 80)
        print("STEP 5: Create Depots")
        print("=" * 80)
        
        depots = seed_depots_from_addresses(db, depot_data)
        if not depots:
            print("❌ Failed to create depots. Exiting.")
            return
        
        # Step 6: Assign zones to nearest depots
        print("\n" + "=" * 80)
        print("STEP 6: Assign Zones to Depots")
        print("=" * 80)
        
        zones_per_depot = assign_zones_to_depots(db, depots)
        
        # Step 7: Create order records with zone and depot assignments
        print("\n" + "=" * 80)
        print("STEP 7: Create Order Records")
        print("=" * 80)
        
        from app.services.h3_service import H3Service
        from app.models.order import Order
        from app.models.zone_depot_assignment import ZoneDepotAssignment
        
        today = date.today()
        
        # Create mapping of zone_id to depot_id
        zone_to_depot = {}
        for depot in depots:
            zones_for_depot = zones_per_depot.get(depot.id, [])
            for zone in zones_for_depot:
                zone_to_depot[zone.id] = depot.id
        
        created_orders = []
        for order_info in order_data:
            try:
                zone_id = order_info['zone_id']
                depot_id = zone_to_depot.get(zone_id)
                
                if not depot_id:
                    # Find nearest depot for this zone
                    zone = next((z for z in zones if z.id == zone_id), None)
                    if zone:
                        zone_lat, zone_lng = get_zone_centroid(zone)
                        min_distance = float('inf')
                        nearest_depot = None
                        for depot in depots:
                            distance = haversine_distance(
                                zone_lat, zone_lng,
                                depot.latitude, depot.longitude
                            )
                            if distance < min_distance:
                                min_distance = distance
                                nearest_depot = depot
                        depot_id = nearest_depot.id if nearest_depot else None
                
                if not depot_id:
                    print(f"  ⚠️  Order {order_info.get('order_number', 'unknown')} has no depot assignment, skipping")
                    continue
                
                order_number = f"ORD-{today.strftime('%Y%m%d')}-{order_info.get('order_number', len(created_orders) + 1):04d}"
                customer_name = f"Customer {order_info.get('order_number', len(created_orders) + 1)}"
                
                latitude = float(order_info['latitude'])
                longitude = float(order_info['longitude'])
                address_text = order_info['address']
                
                # Get H3 index
                h3_index = H3Service.lat_lng_to_h3(latitude, longitude)
                
                order = Order(
                    order_number=order_number,
                    customer_name=customer_name,
                    customer_contact=f"customer{order_info.get('order_number', len(created_orders) + 1)}@example.com",
                    delivery_address=address_text,
                    latitude=latitude,
                    longitude=longitude,
                    h3_index=h3_index,
                    zone_id=zone_id,
                    depot_id=depot_id,
                    order_date=today,
                    scheduled_delivery_date=today,
                    status="geocoded",
                    weight_kg=round(5.0 + (order_info.get('order_number', len(created_orders) + 1) % 20), 2),
                    volume_m3=round(0.1 + (order_info.get('order_number', len(created_orders) + 1) % 5) * 0.05, 2)
                )
                
                db.add(order)
                db.commit()
                
                created_orders.append(order)
                
            except Exception as e:
                print(f"  ✗ Failed to create order: {e}")
                db.rollback()
                continue
        
        print(f"  ✅ Created {len(created_orders)} order records")
        
        # Step 8: Update depot driver counts
        print("\n" + "=" * 80)
        print("STEP 8: Update Depot Driver Counts")
        print("=" * 80)
        
        # Calculate driver needs based on actual orders
        from math import ceil
        for depot in depots:
            order_count = len([o for o in created_orders if o.depot_id == depot.id])
            if order_count > 0:
                drivers_needed = max(1, ceil(order_count / TARGET_ORDERS_PER_DRIVER))
                depot.available_drivers = max(8, drivers_needed + 3)  # Add buffer
                db.add(depot)
                db.commit()
                print(f"  ✓ {depot.name}: {depot.available_drivers} drivers ({order_count} orders)")
        
        # Step 9: Validate configuration
        print("\n" + "=" * 80)
        print("STEP 9: Validation")
        print("=" * 80)
        
        validate_depot_configuration(db, depots, zones_per_depot)
        
        # Step 10: Verify zone-depot consistency
        print("\n" + "=" * 80)
        print("STEP 10: Zone-Depot Consistency Verification")
        print("=" * 80)
        
        verify_zone_depot_consistency(db)
        
        # Final summary
        print("\n" + "=" * 80)
        print("✅ SEEDING COMPLETE!")
        print("=" * 80)
        
        area_count = db.query(models.ServiceArea).count()
        zone_count = db.query(models.ServiceZone).count()
        depot_count = len(depots)
        order_count = len(created_orders)
        
        print(f"\n📊 Summary:")
        print(f"  Service Areas:  {area_count}")
        print(f"  Service Zones:  {zone_count} (H3 Voronoi-based)")
        print(f"  Depots:         {depot_count} (order density-based)")
        print(f"  Orders:         {order_count}")
        print(f"  Delivery Date:  {today}")
        print(f"\n💡 Next steps:")
        print(f"  1. Backend should already be running on http://0.0.0.0:8085")
        print(f"  2. Frontend should be on http://localhost:3000")
        print(f"  3. Open route optimization page and select date: {today}")
        
    except Exception as e:
        print(f"\n❌ Error during seeding: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
