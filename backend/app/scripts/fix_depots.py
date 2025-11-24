"""
Script to remove depot 2 and increase available drivers for remaining depots.
Run this after seeding to clean up depot 2 and increase driver capacity.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.core.database import SessionLocal
from app.models.depot import Depot
from app.models.order import Order
from sqlalchemy import func

def fix_depots():
    """Remove depot 2 and increase drivers for remaining depots."""
    db = SessionLocal()
    
    try:
        # Find depot 2 (assuming it's named "Ottawa SouthEast Depot #2" or similar)
        depot2 = db.query(Depot).filter(
            Depot.name.ilike('%Depot #2%')
        ).first()
        
        if depot2:
            print(f"🗑️  Found depot 2: {depot2.name} (ID: {depot2.id})")
            
            # Count orders for this depot
            order_count = db.query(Order).filter(Order.depot_id == depot2.id).count()
            print(f"   📦 Deleting {order_count} orders for depot 2...")
            
            # Delete in correct order to avoid foreign key constraints
            from app.models.zone_depot_assignment import ZoneDepotAssignment
            
            # 1. Delete orders first
            db.query(Order).filter(Order.depot_id == depot2.id).delete()
            
            # 2. Delete zone assignments
            assignment_count = db.query(ZoneDepotAssignment).filter(ZoneDepotAssignment.depot_id == depot2.id).delete()
            print(f"   🔗 Deleted {assignment_count} zone assignments for depot 2...")
            
            # 3. Delete depot (now safe - no foreign key references)
            db.delete(depot2)
            db.commit()
            
            print(f"   ✅ Deleted depot 2, {order_count} orders, and {assignment_count} zone assignments")
        else:
            print("   ℹ️  Depot 2 not found (may already be deleted)")
        
        # Increase available drivers for remaining depots
        remaining_depots = db.query(Depot).all()
        print(f"\n👥 Increasing drivers for {len(remaining_depots)} remaining depots...")
        
        for depot in remaining_depots:
            # Increase to at least 5 drivers, or keep current if higher
            new_driver_count = max(5, depot.available_drivers + 2)
            old_count = depot.available_drivers
            depot.available_drivers = new_driver_count
            print(f"   ✓ {depot.name}: {old_count} → {new_driver_count} drivers")
        
        db.commit()
        print(f"\n✅ Successfully updated {len(remaining_depots)} depots")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_depots()

