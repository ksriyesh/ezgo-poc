"""
Script to identify all orders that Mapbox cannot find routes for.
This helps identify problematic order locations that need to be fixed or removed.
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.order import Order
from app.models.depot import Depot
from app.services.mapbox_service import MapboxService
import os
from dotenv import load_dotenv

load_dotenv()

async def check_all_orders():
    """Check all orders for routing issues."""
    db = SessionLocal()
    mapbox_service = MapboxService()
    
    try:
        # Get all orders with their depots
        result = db.execute(
            select(Order, Depot)
            .join(Depot, Order.depot_id == Depot.id)
            .where(Order.status == 'geocoded')
        )
        orders_with_depots = result.all()
        
        print("=" * 80)
        print("🔍 CHECKING ALL ORDERS FOR ROUTING ISSUES")
        print("=" * 80)
        print(f"Total orders to check: {len(orders_with_depots)}\n")
        
        unroutable_orders = []
        routable_orders = []
        
        for i, (order, depot) in enumerate(orders_with_depots, 1):
            order_coord = (order.longitude, order.latitude)
            depot_coord = (depot.longitude, depot.latitude)
            
            print(f"[{i}/{len(orders_with_depots)}] Testing {order.order_number}...", end=" ")
            
            try:
                # Test if this order can be routed to/from depot
                distance_matrix = mapbox_service.get_distance_matrix(
                    [depot_coord, order_coord],
                    profile="driving"
                )
                
                if distance_matrix is not None:
                    routable_orders.append({
                        'order': order,
                        'depot': depot,
                        'distance': distance_matrix[0][1] if distance_matrix.shape == (2, 2) else None
                    })
                    print("✅ OK")
                else:
                    unroutable_orders.append({
                        'order': order,
                        'depot': depot,
                        'reason': 'No route found',
                        'order_location': order_coord,
                        'depot_location': depot_coord
                    })
                    print("❌ NO ROUTE")
                    
            except Exception as e:
                unroutable_orders.append({
                    'order': order,
                    'depot': depot,
                    'reason': str(e),
                    'order_location': order_coord,
                    'depot_location': depot_coord
                })
                print(f"❌ ERROR: {e}")
        
        # Summary
        print("\n" + "=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"Total orders checked: {len(orders_with_depots)}")
        print(f"✅ Routable orders: {len(routable_orders)} ({len(routable_orders)/len(orders_with_depots)*100:.1f}%)")
        print(f"❌ Unroutable orders: {len(unroutable_orders)} ({len(unroutable_orders)/len(orders_with_depots)*100:.1f}%)")
        
        if unroutable_orders:
            print("\n" + "=" * 80)
            print("❌ UNROUTABLE ORDERS DETAILS")
            print("=" * 80)
            
            # Group by depot
            by_depot = {}
            for item in unroutable_orders:
                depot_name = item['depot'].name
                if depot_name not in by_depot:
                    by_depot[depot_name] = []
                by_depot[depot_name].append(item)
            
            for depot_name, items in by_depot.items():
                print(f"\n🏭 {depot_name} ({len(items)} unroutable orders):")
                depot_loc = items[0]['depot_location']
                print(f"   Depot location: {depot_loc}")
                
                for item in items:
                    order = item['order']
                    print(f"\n   • {order.order_number}")
                    print(f"     Customer: {order.customer_name}")
                    print(f"     Address: {order.delivery_address}")
                    print(f"     Location: {item['order_location']}")
                    print(f"     Reason: {item['reason']}")
                    print(f"     Order ID: {order.id}")
            
            # SQL to delete unroutable orders
            print("\n" + "=" * 80)
            print("🗑️  SQL TO DELETE UNROUTABLE ORDERS")
            print("=" * 80)
            order_ids = [str(item['order'].id) for item in unroutable_orders]
            print("\n-- Delete unroutable orders:")
            print("DELETE FROM orders WHERE id IN (")
            for i, order_id in enumerate(order_ids):
                comma = "," if i < len(order_ids) - 1 else ""
                print(f"    '{order_id}'{comma}")
            print(");")
            
            # PowerShell command
            print("\n" + "=" * 80)
            print("🐳 DOCKER COMMAND TO DELETE")
            print("=" * 80)
            order_ids_str = ', '.join([f"'{oid}'" for oid in order_ids])
            sql = f"DELETE FROM orders WHERE id IN ({order_ids_str});"
            print(f'\ndocker exec ezgo-poc-db psql -U postgres -d ezgo-poc -c "{sql}"')
            
        else:
            print("\n✅ All orders are routable! No issues found.")
        
        print("\n" + "=" * 80)
        
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting order routing check...")
    print("This will test each order's connectivity to its depot using Mapbox.\n")
    
    # Check if Mapbox token is set
    if not os.getenv("MAPBOX_ACCESS_TOKEN"):
        print("❌ ERROR: MAPBOX_ACCESS_TOKEN not found in environment")
        print("Please set it in your .env file")
        sys.exit(1)
    
    asyncio.run(check_all_orders())







