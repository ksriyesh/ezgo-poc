# ezGO POC - Route Optimization & Delivery Management System

A Proof of Concept for a delivery management system with **H3 geospatial indexing**, **HDBSCAN clustering**, and **Google OR-Tools** for Vehicle Routing Problems (VRP).

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and navigate to project
cd ezgo-poc

# Copy environment file and add your Mapbox token
cp .env.example .env
# Edit .env and add: MAPBOX_ACCESS_TOKEN=your_token_here

# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down
```

**Services:**
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Database: localhost:5432

### Option 2: Local Development

#### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+ with PostGIS
- [uv](https://github.com/astral-sh/uv) (Python package manager)

#### Database Setup
```bash
cd database
docker compose up -d
```

#### Backend
```bash
cd backend

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Seed database
uv run python -m app.scripts.seed

# Start server
uv run python main.py
```

#### Frontend
```bash
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Start dev server
npm run dev
```

---

## 📁 Project Structure

```
ezgo-poc/
├── .env                    # Environment variables (single source of truth)
├── docker-compose.yml      # Docker orchestration
│
├── backend/
│   ├── app/
│   │   ├── api/v1/         # API endpoints
│   │   ├── core/           # Config, database
│   │   ├── crud/           # Database operations
│   │   ├── models/         # SQLAlchemy models
│   │   ├── schemas/        # Pydantic schemas
│   │   ├── scripts/        # Seed scripts
│   │   └── services/       # Business logic
│   │       ├── clustering_service.py      # HDBSCAN clustering
│   │       ├── mapbox_service.py          # Distance matrix API
│   │       └── route_optimization_service.py  # OR-Tools VRP
│   ├── alembic/            # Database migrations
│   ├── Dockerfile
│   └── pyproject.toml
│
├── frontend/
│   ├── app/                # Next.js pages
│   ├── components/
│   │   ├── features/       # Map view, orders sidebar
│   │   └── ui/             # shadcn/ui components
│   ├── lib/
│   │   ├── api/            # Backend API client
│   │   ├── hooks/          # React hooks
│   │   └── map/            # H3 utilities
│   ├── Dockerfile
│   └── package.json
│
└── database/
    ├── Dockerfile          # PostGIS image
    └── init-extensions.sh  # PostgreSQL extensions
```

---

## 🔧 Environment Variables

Create a `.env` file at the project root:

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ezgo-poc
POSTGRES_DB=ezgo-poc
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Mapbox (Required for routing)
MAPBOX_ACCESS_TOKEN=pk.your_mapbox_token_here
NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_mapbox_token_here

# Backend
SECRET_KEY=your-secret-key-change-in-production

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 🗄️ Database Models

| Model | Description |
|-------|-------------|
| **ServiceArea** | Large geographical region (e.g., "Greater Ottawa") with H3 coverage |
| **ServiceZone** | Subdivision of Service Area, created via K-means clustering |
| **Depot** | Warehouse/hub where vehicles start routes |
| **Order** | Delivery request with coordinates, status, zone assignment |
| **ZoneDepotAssignment** | Links zones to their serving depot |
| **H3Cover** | Individual H3 cells for spatial lookups |
| **H3Compact** | Compressed H3 coverage for efficient storage |

---

## 🔌 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/service-areas/` | List service areas with H3 coverage |
| `GET /api/v1/service-zones/` | List zones with boundaries |
| `GET /api/v1/depots/` | List depots and assigned zones |
| `GET /api/v1/orders/` | List orders with filtering |
| `POST /api/v1/routes/optimize` | Run route optimization |
| `GET /api/v1/routes/test-connection` | Health check for services |

---

## 🧠 Route Optimization

### Technology Stack
- **OR-Tools**: Google's constraint solver for VRP
- **HDBSCAN**: Density-based clustering for order grouping
- **Mapbox Matrix API**: Real-world driving distances

### Process
1. **Clustering**: HDBSCAN groups nearby orders into clusters
2. **Distance Matrix**: Mapbox calculates travel times between all points
3. **VRP Solver**: OR-Tools optimizes routes with constraints:
   - Vehicle capacity
   - Maximum travel distance
   - Cluster penalties (soft constraint to keep drivers in neighborhoods)
4. **Output**: Ordered stops per driver with estimated times

### Solver Statuses
- `SUCCESS`: All orders assigned
- `PARTIAL_SUCCESS`: Some orders couldn't be assigned
- `FAILED`: No valid routes found
- `NO_ORDERS`: No orders to optimize

---

## 🐳 Docker Commands

```bash
# Build and start all services
docker compose up -d

# Rebuild after code changes
docker compose build
docker compose up -d

# View logs
docker compose logs -f          # All services
docker compose logs -f backend  # Backend only

# Stop services
docker compose down

# Stop and remove data
docker compose down -v

# Rebuild from scratch
docker compose build --no-cache
docker compose up -d
```

---

## 🌱 Seeding

The seed script populates the database with test data:

```bash
# Default: 12 zones, 3 depots, 90 orders
uv run python -m app.scripts.seed

# Custom parameters
uv run python -m app.scripts.seed --zones 15 --depots 4 --orders 120
```

### What it creates:
1. **Service Area**: Ottawa boundary with H3 coverage
2. **Service Zones**: K-means clustered zones from H3 cells
3. **Depots**: Strategically placed based on zone centroids
4. **Orders**: Randomly distributed across zones

---

## 🛠️ Development

### Backend
```bash
cd backend

# Run tests
uv run pytest

# Format code
uv run black .
uv run ruff check --fix .

# Create migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head
```

### Frontend
```bash
cd frontend

# Lint
npm run lint

# Type check
npx tsc --noEmit
```

---

## 📝 License

MIT
