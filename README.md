# ezGO POC - Route Optimization & Delivery Management System

## 📖 High-Level Overview
This project is a Proof of Concept (POC) for a delivery management system that handles **Service Areas**, **Service Zones**, **Depots**, **Orders**, and **Route Optimization**. It leverages **H3 geospatial indexing** for zone creation and **Google OR-Tools** for solving Vehicle Routing Problems (VRP).

---

## 🗄️ Database Models
The database is designed to represent the hierarchical structure of delivery operations.

### 1. Service Area (`ServiceArea`)
*   **What it is:** A large geographical region (e.g., "Greater Ottawa").
*   **Key Fields:** `name`, `geometry` (Polygon), `h3_resolution` (default 9).
*   **Role:** The top-level container for all operations. It is filled with H3 hexagons to define its coverage.

### 2. Service Zone (`ServiceZone`)
*   **What it is:** A smaller subdivision of a Service Area, mimicking FSAs (Forward Sortation Areas) or neighborhoods.
*   **Key Fields:** `name`, `geometry` (Polygon), `service_area_id`.
*   **Role:** Created by clustering H3 cells. Orders are assigned to these zones to group deliveries geographically.

### 3. Depot (`Depot`)
*   **What it is:** A physical location (warehouse/hub) where vehicles start their routes.
*   **Key Fields:** `name`, `latitude`, `longitude`, `geometry` (Point).
*   **Role:** Serves specific Service Zones. Drivers pick up packages here.

### 4. Order (`Order`)
*   **What it is:** A single delivery request.
*   **Key Fields:** `order_number`, `latitude`, `longitude`, `status` (pending/assigned), `service_zone_id`, `depot_id`.
*   **Role:** The fundamental unit of work. It is automatically assigned to a Zone and Depot upon creation based on its location.

### 5. Zone-Depot Assignment (`ZoneDepotAssignment`)
*   **What it is:** A linking table.
*   **Key Fields:** `zone_id`, `depot_id`.
*   **Role:** Defines which Depot is responsible for serving which Service Zone.

---

## 🌱 Seed Data Generation
The seeding script (`backend/app/scripts/seed_new.py`) intelligently populates the database using geospatial algorithms.

### Step 1: Generate Service Area with H3
*   **Action:** Creates a large polygon (e.g., Ottawa).
*   **Logic:** Fills this polygon with **H3 hexagons** (resolution 9) to create a discrete grid of the city.

### Step 2: Create Service Zones (K-means Clustering)
*   **Action:** Groups the thousands of H3 cells into ~10-15 manageable zones.
*   **Logic:**
    *   Extracts the centroid of every H3 cell.
    *   Uses **K-means clustering** to group these centroids into `k` clusters.
    *   Merges the cells in each cluster to form a single `ServiceZone` polygon.
    *   **Result:** FSA-like zones that fully cover the Service Area without gaps.

### Step 3: Place Depots & Assign Zones
*   **Action:** Creates 3 depots to serve the city.
*   **Logic:**
    *   Calculates the centroid of each Service Zone.
    *   Clusters these zones into 3 groups (one for each depot).
    *   Places a Depot at the center of each group.
    *   Assigns all zones in a group to that Depot.

### Step 4: Generate Orders
*   **Action:** Creates 90 random orders (30 per depot).
*   **Logic:**
    *   Generates random points within the Service Area.
    *   Checks which Service Zone the point falls into.
    *   Assigns the Order to that Zone and its corresponding Depot.
    *   Ensures valid coordinates (no water bodies, etc.) via geometric checks.

---

## 🔌 Backend Methods (API)
The FastAPI backend exposes REST endpoints to manage these entities.

*   **`/service-areas/`**: CRUD operations for service areas. Supports fetching H3 coverage.
*   **`/service-zones/`**: CRUD for zones. Used by the frontend to display zone boundaries.
*   **`/depots/`**: Manage depot locations and retrieve assigned zones.
*   **`/orders/`**: Create and retrieve orders. Supports filtering by status and zone.
*   **`/route-optimization/`**: The core intelligence engine (see below).

---

## 🧠 Route Optimization
The optimization logic (`RouteOptimizationService`) turns a list of orders into efficient delivery routes.

### Core Technology
*   **Engine:** Google OR-Tools (Constraint Solver).
*   **Strategy:** `GUIDED_LOCAL_SEARCH` metaheuristic.
*   **Goal:** Minimize total distance and time while respecting constraints.

### How it Works
1.  **Input:** A Depot location and a list of Order locations.
2.  **Distance Matrix:** Calculates travel times between all points (Depot ↔ Orders, Order ↔ Order).
3.  **Constraints:**
    *   **Vehicle Capacity:** Max orders per driver.
    *   **Max Distance:** Limits total daily travel per vehicle (e.g., 150km).
    *   **Cluster Penalties (Soft Constraint):** Adds a virtual "cost" if a driver crosses from one pre-defined cluster to another. This encourages drivers to stay in their neighborhood but allows crossing if it's significantly more efficient.
4.  **Output:** Ordered list of stops for each driver, including estimated arrival times and total route distance.
5.  **Partial Success:** If not all orders can be assigned (e.g., due to strict constraints), the solver returns a `PARTIAL_SUCCESS` status with the routes it *could* generate.

