# ezGO POC - Route Optimization & Delivery Management System

A Proof of Concept for a delivery management system with **H3 geospatial indexing**, **HDBSCAN clustering**, and **Google OR-Tools** for Vehicle Routing Problems (VRP).

![Map View](https://img.shields.io/badge/Frontend-Next.js%2014-black) ![API](https://img.shields.io/badge/Backend-FastAPI-009688) ![Database](https://img.shields.io/badge/Database-PostGIS-336791)

## ✨ What It Does

- **Visualize** service areas and zones on an interactive map
- **Manage** delivery orders with automatic zone/depot assignment
- **Optimize** delivery routes using AI-powered clustering and VRP solver
- **Track** drivers and route progress in real-time

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone and navigate to project
cd ezgo-poc

# Copy environment file and add your Mapbox token
cp .env.example .env
# Edit .env and add: MAPBOX_ACCESS_TOKEN=your_token_here

# Start all services (auto-runs migrations & seeding)
docker compose up -d

# View logs
docker compose logs -f
```

**Services:**
| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Database | localhost:5433 |

### Option 2: Local Development

#### Prerequisites
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+ with PostGIS extension
- [uv](https://github.com/astral-sh/uv) (Python package manager)

#### Database
Start PostgreSQL with PostGIS locally, or use Docker for just the database:
```bash
docker compose up -d db
```

#### Backend
```bash
cd backend

# Install dependencies
uv sync

# Run migrations
uv run alembic upgrade head

# Seed database (creates Ottawa area, zones, depots, orders)
uv run python -m app.scripts.seed

# Start server
uv run python main.py
```

#### Frontend
```bash
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Start dev server (loads env from root .env)
npm run dev
```

---

## 📁 Project Structure

```
ezgo-poc/
├── .env                    # Environment variables (single source)
├── docker-compose.yml      # Orchestrates all services
│
├── backend/
│   ├── app/
│   │   ├── api/v1/         # REST endpoints
│   │   ├── core/           # Config, database connection
│   │   ├── crud/           # Database operations
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic validation schemas
│   │   ├── scripts/        # Seed & utility scripts
│   │   └── services/       # Business logic
│   │       ├── clustering_service.py      # HDBSCAN clustering
│   │       ├── mapbox_service.py          # Distance matrix API
│   │       └── route_optimization_service.py  # OR-Tools VRP
│   ├── alembic/            # Database migrations
│   └── docker-entrypoint.sh  # Auto migrations + seeding
│
├── frontend/
│   ├── app/                # Next.js app router
│   ├── components/
│   │   ├── features/       # Map view, orders sidebar
│   │   └── ui/             # shadcn/ui components
│   └── lib/
│       ├── api/            # Backend API client
│       └── map/            # H3 utilities
│
└── database/
    ├── Dockerfile          # PostGIS image
    └── init-extensions.sh  # Enable H3, PostGIS extensions
```

---

## 🔧 Environment Variables

Create `.env` at project root (or copy from `.env.example`):

```env
# Database
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ezgo-poc
POSTGRES_DB=ezgo-poc
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Mapbox (Required - get token at https://mapbox.com)
MAPBOX_ACCESS_TOKEN=pk.your_token_here
NEXT_PUBLIC_MAPBOX_TOKEN=pk.your_token_here

# Backend
SECRET_KEY=change-this-in-production

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 🗄️ Database Models

| Model | Description |
|-------|-------------|
| **ServiceArea** | Large region (e.g., "Ottawa") covered by H3 hexagons |
| **ServiceZone** | Subdivision created via K-means clustering of H3 cells |
| **Depot** | Warehouse where drivers start their routes |
| **Order** | Delivery request with coordinates and status |
| **ZoneDepotAssignment** | Links zones to serving depots |
| **H3Cover / H3Compact** | H3 cell storage for fast spatial queries |

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/service-areas/` | List areas with H3 coverage |
| GET | `/api/v1/service-zones/` | List zones with boundaries |
| GET | `/api/v1/depots/` | List depots and assignments |
| GET | `/api/v1/orders/` | List/filter orders |
| POST | `/api/v1/routes/optimize` | Run route optimization |
| GET | `/api/v1/routes/test-connection` | Service health check |

Full API docs: http://localhost:8000/docs

---

## 🧠 Route Optimization

### How It Works

```
Orders → HDBSCAN Clustering → Distance Matrix (Mapbox) → VRP Solver (OR-Tools) → Optimized Routes
```

1. **Clustering**: HDBSCAN groups nearby orders into geographic clusters
2. **Distance Matrix**: Mapbox API calculates real driving times
3. **VRP Solver**: OR-Tools optimizes with constraints:
   - Vehicle capacity limits
   - Maximum travel distance
   - Cluster penalties (keeps drivers in neighborhoods)
4. **Output**: Ordered stops per driver with ETAs

### Solver Statuses
| Status | Meaning |
|--------|---------|
| `SUCCESS` | All orders assigned to routes |
| `PARTIAL_SUCCESS` | Some orders unassignable |
| `FAILED` | No valid routes found |
| `NO_ORDERS` | Nothing to optimize |

---

## 🐳 Docker Commands

```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f           # All
docker compose logs -f backend   # Backend only

# Rebuild after code changes
docker compose build && docker compose up -d

# Stop
docker compose down

# Stop and delete data
docker compose down -v

# Full rebuild
docker compose build --no-cache && docker compose up -d
```

---

## 🌱 Seeding

Docker automatically seeds on first run. For manual seeding:

```bash
cd backend

# Default: 12 zones, 3 depots, 90 orders
uv run python -m app.scripts.seed

# Custom
uv run python -m app.scripts.seed --zones 15 --depots 4 --orders 150
```

**Creates:**
- Ottawa service area with H3 coverage
- K-means clustered service zones  
- Strategically placed depots
- Random orders distributed across zones

---

## 🛠️ Development

### Backend
```bash
cd backend
uv run pytest                              # Run tests
uv run black . && uv run ruff check --fix  # Format
uv run alembic revision --autogenerate -m "msg"  # New migration
uv run alembic upgrade head                # Apply migrations
```

### Frontend
```bash
cd frontend
npm run lint        # Lint
npx tsc --noEmit    # Type check
```

---

## 📝 License

MIT
