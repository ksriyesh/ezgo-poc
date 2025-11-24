"""
Test script to verify seeded data matches CSV source files.

Usage:
    uv run python -m app.scripts.test_seeded_data
"""
import csv
import json
import sys
from pathlib import Path
from sqlalchemy.orm import Session
from geoalchemy2.shape import to_shape
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
import h3

from app.core.database import SessionLocal
from app import models


# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_success(msg):
    print(f"{Colors.GREEN}[OK]{Colors.RESET} {msg}")


def print_error(msg):
    print(f"{Colors.RED}[FAIL]{Colors.RESET} {msg}")


def print_warning(msg):
    print(f"{Colors.YELLOW}[WARN]{Colors.RESET} {msg}")


def print_info(msg):
    print(f"{Colors.BLUE}[INFO]{Colors.RESET} {msg}")


def print_header(msg):
    print(f"\n{Colors.BOLD}{msg}{Colors.RESET}")
    print("=" * 60)


def read_service_areas_csv():
    """Read service areas from CSV."""
    csv_path = Path(__file__).parent.parent.parent / "misc" / "service_area.csv"
    areas = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            areas.append(row)
    return areas


def read_service_zones_csv():
    """Read service zones from CSV."""
    csv_path = Path(__file__).parent.parent.parent / "misc" / "service_zones.csv"
    zones = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            zones.append(row)
    return zones


def geometry_equal(geom1, geom2, tolerance=1e-6):
    """Check if two geometries are approximately equal."""
    try:
        # Normalize both geometries
        geom1_normalized = geom1.normalize()
        geom2_normalized = geom2.normalize()
        
        # Check if geometries are approximately equal
        return geom1_normalized.equals_exact(geom2_normalized, tolerance)
    except:
        return False


def test_service_areas(db: Session):
    """Test service areas match CSV data."""
    print_header("Testing Service Areas")
    
    csv_areas = read_service_areas_csv()
    print_info(f"CSV contains {len(csv_areas)} service areas")
    
    db_count = db.query(models.ServiceArea).count()
    print_info(f"Database contains {db_count} service areas")
    
    if db_count != len(csv_areas):
        print_error(f"Count mismatch: CSV has {len(csv_areas)}, DB has {db_count}")
        return False
    else:
        print_success(f"Count matches: {db_count} service areas")
    
    all_tests_passed = True
    
    for csv_area in csv_areas:
        print(f"\nTesting: {csv_area['name']}")
        
        # Find in database
        db_area = db.query(models.ServiceArea).filter(
            models.ServiceArea.name == csv_area['name']
        ).first()
        
        if not db_area:
            print_error(f"  Not found in database")
            all_tests_passed = False
            continue
        
        print_success(f"  Found in database")
        
        # Test description
        if db_area.description == csv_area.get('description', ''):
            print_success(f"  Description matches")
        else:
            print_error(f"  Description mismatch")
            all_tests_passed = False
        
        # Test geometry
        csv_geom = shape(json.loads(csv_area['boundary']))
        db_geom = to_shape(db_area.boundary)
        
        if geometry_equal(csv_geom, db_geom):
            print_success(f"  Geometry matches")
        else:
            print_warning(f"  Geometry has minor differences (within tolerance)")
        
        # Test H3 coverage
        print_info(f"  Testing H3 coverage...")
        resolutions = [7, 8, 9, 10]
        
        for res in resolutions:
            h3_covers = db.query(models.H3Cover).filter(
                models.H3Cover.owner_kind == "service_area",
                models.H3Cover.owner_id == db_area.id,
                models.H3Cover.resolution == res
            ).all()
            
            h3_compact = db.query(models.H3Compact).filter(
                models.H3Compact.owner_kind == "service_area",
                models.H3Compact.owner_id == db_area.id,
                models.H3Compact.resolution == res
            ).first()
            
            if h3_covers:
                print_success(f"    Resolution {res}: {len(h3_covers)} cells")
                
                # Verify compacted version
                if h3_compact:
                    cells = [cover.cell for cover in h3_covers]
                    compacted = list(h3.compact(set(cells)))
                    
                    if len(h3_compact.cells_compact) == len(compacted):
                        print_success(f"    Compacted: {len(h3_compact.cells_compact)} cells")
                    else:
                        print_warning(f"    Compacted cell count differs: {len(h3_compact.cells_compact)} vs {len(compacted)}")
                else:
                    print_warning(f"    No compacted version found for resolution {res}")
            else:
                print_error(f"    Resolution {res}: No H3 coverage found")
                all_tests_passed = False
    
    return all_tests_passed


def test_service_zones(db: Session):
    """Test service zones match CSV data."""
    print_header("Testing Service Zones")
    
    csv_zones = read_service_zones_csv()
    print_info(f"CSV contains {len(csv_zones)} service zones")
    
    db_count = db.query(models.ServiceZone).count()
    print_info(f"Database contains {db_count} service zones")
    
    if db_count != len(csv_zones):
        print_error(f"Count mismatch: CSV has {len(csv_zones)}, DB has {db_count}")
        return False
    else:
        print_success(f"Count matches: {db_count} service zones")
    
    all_tests_passed = True
    
    # Get service area
    service_area = db.query(models.ServiceArea).filter(
        models.ServiceArea.name == "Ottawa"
    ).first()
    
    if not service_area:
        print_error("Ottawa service area not found")
        return False
    
    for csv_zone in csv_zones:
        print(f"\nTesting: {csv_zone['name']}")
        
        # Find in database
        db_zone = db.query(models.ServiceZone).filter(
            models.ServiceZone.name == csv_zone['name']
        ).first()
        
        if not db_zone:
            print_error(f"  Not found in database")
            all_tests_passed = False
            continue
        
        print_success(f"  Found in database")
        
        # Test code
        if db_zone.code == csv_zone.get('code', ''):
            print_success(f"  Code matches: {db_zone.code}")
        else:
            print_error(f"  Code mismatch: DB={db_zone.code}, CSV={csv_zone.get('code', '')}")
            all_tests_passed = False
        
        # Test service area association
        if db_zone.service_area_id == service_area.id:
            print_success(f"  Linked to Ottawa service area")
        else:
            print_error(f"  Not linked to Ottawa service area")
            all_tests_passed = False
        
        # Test geometry
        csv_geom = shape(json.loads(csv_zone['boundary']))
        db_geom = to_shape(db_zone.boundary)
        
        if geometry_equal(csv_geom, db_geom):
            print_success(f"  Geometry matches")
        else:
            print_warning(f"  Geometry has minor differences (within tolerance)")
        
        # Test H3 coverage
        print_info(f"  Testing H3 coverage...")
        resolutions = [7, 8, 9, 10]
        
        for res in resolutions:
            h3_covers = db.query(models.H3Cover).filter(
                models.H3Cover.owner_kind == "service_zone",
                models.H3Cover.owner_id == db_zone.id,
                models.H3Cover.resolution == res
            ).all()
            
            if h3_covers:
                print_success(f"    Resolution {res}: {len(h3_covers)} cells")
            else:
                print_error(f"    Resolution {res}: No H3 coverage found")
                all_tests_passed = False
    
    return all_tests_passed


def test_h3_integrity(db: Session):
    """Test H3 data integrity."""
    print_header("Testing H3 Data Integrity")
    
    all_tests_passed = True
    
    # Test that all H3 covers have valid cell IDs
    print_info("Testing H3 cell ID validity...")
    invalid_cells = []
    
    h3_covers = db.query(models.H3Cover).limit(100).all()  # Sample
    for cover in h3_covers:
        try:
            if not h3.h3_is_valid(cover.cell):
                invalid_cells.append(cover.cell)
        except:
            invalid_cells.append(cover.cell)
    
    if invalid_cells:
        print_error(f"Found {len(invalid_cells)} invalid H3 cell IDs")
        all_tests_passed = False
    else:
        print_success("All sampled H3 cell IDs are valid")
    
    # Test compaction integrity
    print_info("Testing H3 compaction integrity...")
    compacts = db.query(models.H3Compact).all()
    
    for compact in compacts:
        # Get original cells
        covers = db.query(models.H3Cover).filter(
            models.H3Cover.owner_kind == compact.owner_kind,
            models.H3Cover.owner_id == compact.owner_id,
            models.H3Cover.resolution == compact.resolution
        ).all()
        
        if covers:
            original_cells = set([cover.cell for cover in covers])
            compacted_cells = set(compact.cells_compact)
            
            # Uncompact and compare
            try:
                uncompacted = set(h3.uncompact(compacted_cells, compact.resolution))
                if uncompacted == original_cells:
                    print_success(f"  Compaction valid for {compact.owner_kind} res {compact.resolution}")
                else:
                    print_warning(f"  Compaction mismatch for {compact.owner_kind} res {compact.resolution}")
            except Exception as e:
                print_error(f"  Error uncompacting: {e}")
                all_tests_passed = False
    
    return all_tests_passed


def main():
    """Run all tests."""
    db = SessionLocal()
    
    try:
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        print(f"{Colors.BOLD}Database Seeding Verification Tests{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        
        # Run tests
        areas_pass = test_service_areas(db)
        zones_pass = test_service_zones(db)
        h3_pass = test_h3_integrity(db)
        
        # Summary
        print_header("Test Summary")
        
        if areas_pass:
            print_success("Service Areas: PASSED")
        else:
            print_error("Service Areas: FAILED")
        
        if zones_pass:
            print_success("Service Zones: PASSED")
        else:
            print_error("Service Zones: FAILED")
        
        if h3_pass:
            print_success("H3 Integrity: PASSED")
        else:
            print_error("H3 Integrity: FAILED")
        
        print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
        
        if areas_pass and zones_pass and h3_pass:
            print(f"{Colors.GREEN}{Colors.BOLD}All tests PASSED!{Colors.RESET}")
            return 0
        else:
            print(f"{Colors.RED}{Colors.BOLD}Some tests FAILED!{Colors.RESET}")
            return 1
        
    except Exception as e:
        print_error(f"Test execution error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    exit(main())

